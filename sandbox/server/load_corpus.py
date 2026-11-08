"""Load every corpus file into local SQLite: python load_corpus.py <corpus dir> <database>.

Reads <corpus dir>/out/*.jsonl and external/*.jsonl with no subset. Safe to re-run. `rand` is a hash of the case id,
so the order is the same on every load.
"""

import hashlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
  case_id TEXT PRIMARY KEY, channel TEXT NOT NULL, source TEXT NOT NULL, label_quality TEXT NOT NULL,
  scam INTEGER, method TEXT NOT NULL, family TEXT NOT NULL, hard_negative INTEGER NOT NULL,
  rand REAL NOT NULL, payload TEXT NOT NULL
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_cases_rand ON cases (rand, case_id);
CREATE INDEX IF NOT EXISTS idx_cases_source ON cases (source, method, rand);
CREATE INDEX IF NOT EXISTS idx_cases_channel ON cases (channel, rand);
CREATE INDEX IF NOT EXISTS idx_cases_method ON cases (method, rand);
"""


def rand_for(case_id: str) -> float:
    return int(hashlib.sha256(case_id.encode()).hexdigest()[:13], 16) / 16**13


def rows(path: Path):
    with path.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            case = json.loads(line)
            scam = case.get("scam")
            yield (
                case["case_id"],
                case["channel"],
                case["source"],
                case["label_quality"],
                None if scam is None else int(scam),
                case["method"],
                case["family"],
                int(bool(case.get("hard_negative"))),
                rand_for(case["case_id"]),
                json.dumps(case, separators=(",", ":")),
            )


def main() -> None:
    corpus, database = Path(sys.argv[1]), sys.argv[2]
    connection = sqlite3.connect(database, isolation_level=None)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=OFF")
    connection.executescript(SCHEMA)
    counts: Counter = Counter()
    files = [*corpus.glob("out/*.jsonl"), *corpus.glob("external/*.jsonl")]
    for path in sorted(f for f in files if not f.name.startswith(".")):
        connection.execute("BEGIN")
        before = connection.total_changes
        connection.executemany("INSERT OR REPLACE INTO cases VALUES (?,?,?,?,?,?,?,?,?,?)", rows(path))
        connection.execute("COMMIT")
        counts[path.name] = connection.total_changes - before
    connection.execute("ANALYZE")
    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    total = connection.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    print(dict(counts), "total", total)
    connection.close()


if __name__ == "__main__":
    main()
