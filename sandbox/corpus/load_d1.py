"""Load every out/*.jsonl and external/*.jsonl Case file into the D1 database safe-signal-corpus.

    python3 sandbox/corpus/load_d1.py [--batch-size 2000] [--workers 4] [--max-cases N] [--time-limit 540]

Safe to re-run: existing case_ids are skipped, so it picks up new files and resumes after a limit is reached.
Cases are loaded in stratified order (round-robin over source, channel, method and label), so if a quota or the
size limit stops the load early, what's in the database is still a balanced subset. Run from anywhere.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CORPUS = Path(__file__).resolve().parent
DATABASE = "safe-signal-corpus"
MAX_DB_MB = 450  # the D1 free-plan database limit is 500 MB; override with --max-db-mb
SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
  case_id TEXT PRIMARY KEY, channel TEXT NOT NULL, source TEXT NOT NULL, label_quality TEXT NOT NULL,
  scam INTEGER NOT NULL, method TEXT NOT NULL, family TEXT NOT NULL, hard_negative INTEGER NOT NULL,
  rand REAL NOT NULL, payload TEXT NOT NULL
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_cases_source_method_rand ON cases(source, method, rand);
CREATE INDEX IF NOT EXISTS idx_cases_channel_rand ON cases(channel, rand);
"""
LIMIT_MARKERS = ("exceeded", "limit", "quota", "too many", "storage")


def wrangler(args: list[str], timeout: int = 180) -> tuple[int, str]:
    result = subprocess.run(
        ["npx", "--yes", "wrangler", *args], cwd=CORPUS, capture_output=True, text=True, timeout=timeout
    )
    return result.returncode, result.stdout + result.stderr


def d1_query(sql: str) -> list[dict]:
    code, output = wrangler(["d1", "execute", DATABASE, "--remote", "--yes", "--json", "--command", sql])
    if code != 0:
        raise RuntimeError(output[-800:])
    return json.loads(output[output.index("[") :])[0]["results"]


def ensure_database() -> str:
    code, output = wrangler(["d1", "list", "--json"])
    if code != 0:
        raise RuntimeError(output[-500:])
    databases = json.loads(output[output.index("[") :])
    match = next((d for d in databases if d["name"] == DATABASE), None)
    if match is None:
        code, output = wrangler(["d1", "create", DATABASE])
        if code != 0:
            raise RuntimeError(output[-500:])
        code, output = wrangler(["d1", "list", "--json"])
        match = next(d for d in json.loads(output[output.index("[") :]) if d["name"] == DATABASE)
    return match["uuid"]


def execute_file(sql_text: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".sql", dir=CORPUS / "out", delete=False) as handle:
        handle.write(sql_text)
        path = Path(handle.name)
    try:
        for attempt in range(3):
            code, output = wrangler(["d1", "execute", DATABASE, "--remote", "--yes", "--file", str(path)], timeout=280)
            if code == 0:
                return True, output
            if any(marker in output.lower() for marker in LIMIT_MARKERS):
                return False, output
            time.sleep(3 * (attempt + 1))
        return False, output
    finally:
        path.unlink(missing_ok=True)


def existing_ids() -> set[str]:
    ids: set[str] = set()
    last = ""
    while True:
        escaped = last.replace("'", "''")
        rows = d1_query(f"SELECT case_id FROM cases WHERE case_id > '{escaped}' ORDER BY case_id LIMIT 20000")
        if not rows:
            return ids
        ids.update(r["case_id"] for r in rows)
        last = rows[-1]["case_id"]


def stable_rand(case_id: str) -> float:
    return int(hashlib.sha256(case_id.encode()).hexdigest()[:13], 16) / 16**13


def load_cases(skip: set[str]) -> tuple[list[dict], Counter]:
    strata: dict[tuple, list[dict]] = defaultdict(list)
    seen = Counter()
    for path in sorted([*CORPUS.glob("out/*.jsonl"), *CORPUS.glob("external/*.jsonl")]):
        with path.open() as handle:
            for line in handle:
                if line.strip():
                    case = json.loads(line)
                    seen[path.name] += 1
                    if case["case_id"] not in skip:
                        strata[(case["source"], case["channel"], case["method"], case["scam"])].append(case)
    ordered: list[dict] = []
    groups = [sorted(group, key=lambda c: stable_rand(c["case_id"])) for group in strata.values()]
    index = 0
    while groups:
        groups = [g for g in groups if index < len(g)]
        ordered.extend(g[index] for g in groups)
        index += 1
    return ordered, seen


def quote(value: str) -> str:
    return "'" + value.replace("'", "''").replace("\x00", "") + "'"


def insert_statement(case: dict) -> str:
    payload = quote(json.dumps(case, separators=(",", ":")))
    values = [
        quote(case["case_id"]),
        quote(case["channel"]),
        quote(case["source"]),
        quote(case["label_quality"]),
        str(int(bool(case["scam"]))),
        quote(case["method"]),
        quote(case["family"]),
        str(int(bool(case["hard_negative"]))),
        repr(stable_rand(case["case_id"])),
        payload,
    ]
    return f"INSERT OR IGNORE INTO cases VALUES ({','.join(values)});"


def database_mb() -> float | None:
    code, output = wrangler(["d1", "info", DATABASE, "--json"])
    if code != 0:
        return None
    try:
        return json.loads(output[output.index("{") :])["database_size"] / 1_000_000
    except (ValueError, KeyError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument("--time-limit", type=int, default=540)
    parser.add_argument("--max-db-mb", type=float, default=MAX_DB_MB)
    parser.add_argument("--only-source", default="", help="load just this source, e.g. generated")
    args = parser.parse_args()

    started = time.time()
    database_id = ensure_database()
    print(f"database_id {database_id}", flush=True)
    ok, output = execute_file(SCHEMA)
    if not ok:
        print(output[-800:])
        return 1

    present = existing_ids()
    cases, seen = load_cases(present)
    if args.only_source:
        cases = [c for c in cases if c["source"] == args.only_source]
    print(f"files {dict(seen)}; already loaded {len(present)}; to load {len(cases)}", flush=True)
    if args.max_cases:
        cases = cases[: args.max_cases]
    batches = [cases[i : i + args.batch_size] for i in range(0, len(cases), args.batch_size)]

    loaded = 0
    stop_reason = ""

    def send(batch: list[dict]) -> tuple[bool, str, int]:
        ok, message = execute_file("\n".join(insert_statement(c) for c in batch))
        return ok, message, len(batch)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for start in range(0, len(batches), args.workers):
            if time.time() - started > args.time_limit:
                stop_reason = "time limit (re-run to continue)"
                break
            mb = database_mb()
            if mb is not None and mb > args.max_db_mb:
                stop_reason = f"database at {mb:.0f} MB, near the 500 MB limit"
                break
            results = list(pool.map(send, batches[start : start + args.workers]))
            failed = [message for ok, message, _ in results if not ok]
            loaded += sum(n for ok, _, n in results if ok)
            print(f"loaded {loaded}/{len(cases)} in {time.time() - started:.0f}s, db {mb}", flush=True)
            if failed:
                stop_reason = f"D1 refused a batch: {failed[0][-500:]}"
                break

    print(f"finished: loaded {loaded} new cases. {stop_reason or 'all files loaded.'}")
    rows = d1_query("SELECT source, channel, scam, COUNT(*) AS n FROM cases GROUP BY source, channel, scam ORDER BY 1, 2, 3")
    print(json.dumps(rows))
    print(f"database_size_mb {database_mb()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
