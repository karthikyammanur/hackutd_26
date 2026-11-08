"""Run the sandbox end to end.

    python -m sandbox.run --per-type 20

Writes sandbox/runs/<run_id>/ (scoreboard, per-call results, frame scores, recommendations) and appends to
sandbox/logs/ (failure history and lessons, which later runs and the main agent can read).
Only scores, flags and ids reach the disk: transcript text and agent notes stay in memory (R8).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from sandbox import review as reviewer
from sandbox import scoring
from sandbox.data import load_sample
from sandbox.graph import CallResult, NemotronBriefAgent, build_graph, run_call
from sandbox.jev import Jev
from sandbox.llm import Nemotron
from sandbox.settings import ROOT, Settings

log = logging.getLogger("sandbox")


def append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_outputs(
    run_id: str,
    out_dir: Path,
    log_dir: Path,
    results: list[CallResult],
    rows: list[scoring.Row],
    board: dict,
    review: reviewer.Review,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat()

    (out_dir / "scoreboard.json").write_text(json.dumps(board, indent=1))
    (out_dir / "scoreboard.md").write_text(scoring.scoreboard_markdown(run_id, board))
    with (out_dir / "calls.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(scoring.row_dict(rows[0])))
        writer.writeheader()
        writer.writerows(scoring.row_dict(row) for row in rows)
    append_jsonl(
        out_dir / "frames.jsonl",
        [{"session_id": r.session.session_id, **asdict(frame)} for r in results for frame in r.frames],
    )

    append_jsonl(
        log_dir / "failure_log.jsonl",
        [
            {
                "run_id": run_id,
                "ts": now,
                "type": t["type"],
                "n": t["n"],
                "error_rate": t["error_rate"],
                "outcomes": t["outcomes"],
            }
            for t in board["by_type"]
        ],
    )
    history = read_jsonl(log_dir / "failure_log.jsonl")
    consistent = reviewer.consistent_failures(history)
    lessons = [
        {"run_id": run_id, "ts": now, "status": "proposed", **rec.model_dump()}
        for rec in review.recommendations
    ]
    append_jsonl(log_dir / "lessons.jsonl", lessons)
    (log_dir / "consistent_failures.json").write_text(json.dumps(consistent, indent=1))
    (out_dir / "recommendations.json").write_text(review.model_dump_json(indent=1))
    runs_seen = len({row["run_id"] for row in history})
    (out_dir / "recommendations.md").write_text(
        reviewer.recommendations_markdown(run_id, review, consistent, runs_seen)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "sessions.jsonl")
    parser.add_argument("--per-type", type=int, default=20, help="calls per call type; 0 means all of them")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20261108)
    parser.add_argument("--run-id", default=datetime.now(UTC).strftime("run-%Y%m%d-%H%M%S"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    settings = Settings.from_env()
    jev = Jev(settings.jev_api_key, settings.jev_model)
    fast = Nemotron(settings.fast_url, settings.nemotron_api_key, settings.fast_model)
    deep = Nemotron(settings.deep_url, settings.nemotron_api_key, settings.deep_model, timeout_s=300)
    jev.ping()
    fast.ping()
    deep.ping()
    log.info("preflight ok: Jev, %s and %s are reachable", settings.fast_model, settings.deep_model)

    sessions = load_sample(args.input, args.per_type, args.seed)
    log.info("replaying %d calls (%d frames)", len(sessions), sum(len(s.frames) for s in sessions))

    graph = build_graph(NemotronBriefAgent(fast), jev)
    results: list[CallResult] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for done, result in enumerate(pool.map(lambda s: run_call(graph, s), sessions), 1):
            results.append(result)
            if done % 25 == 0 or done == len(sessions):
                log.info("%d/%d calls done", done, len(sessions))

    rows = [scoring.score_call(result) for result in results]
    board = scoring.build_scoreboard(results, rows)
    buckets = reviewer.failure_buckets(results, rows)
    log.info("scored; asking the review agent about %d failure groups", len(buckets))
    try:
        review = reviewer.run_review(deep, buckets)
    except Exception as exc:  # the scoreboard is still valid without the review
        log.error("review agent failed: %s", exc)
        review = reviewer.Review(
            overall=f"The review agent failed ({type(exc).__name__}). See the scoreboard."
        )

    out_dir = ROOT / "runs" / args.run_id
    write_outputs(args.run_id, out_dir, ROOT / "logs", results, rows, board, review)
    print(scoring.scoreboard_markdown(args.run_id, board))
    print((out_dir / "recommendations.md").read_text())
    log.info("wrote %s", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
