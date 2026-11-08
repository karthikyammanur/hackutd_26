"""Score Safe Signal predictions against labeled sessions.

Inputs
  --cases  a folder of EvalCase JSON files, or a .jsonl file with one EvalCase per line
  --preds  a .jsonl file, one line per session:
           {"session_id": "...", "alerts": [{"t": 101.5, "level": "alert", "score": 0.91}],
            "latency_ms": [42, 51]}   # latency_ms optional
Output
  A Markdown report on stdout. With --gate, exits 1 if a threshold fails.

Metrics
  catch rate           scam sessions that reach the level (any time in the call)
  false interventions  benign sessions that reach the level (hard negatives reported separately)
  time to detect       first t at >= whisper minus label.first_scam_t (negative = caught before the ask)
  calibration          per-session max score vs label, 5 bins, expected calibration error (ECE)
  latency              p50 / p95 of latency_ms across all checks
Standard library only, so it runs anywhere.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

LEVELS = {"none": 0, "nudge": 1, "whisper": 2, "alert": 3}


def load_cases(path: Path) -> dict[str, dict]:
    if path.is_dir():
        rows = [json.loads(p.read_text()) for p in sorted(path.glob("*.json"))]
    else:
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {r["session_id"]: r for r in rows}


def load_preds(path: Path) -> dict[str, dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {r["session_id"]: r for r in rows}


def first_t_at(alerts: list[dict], min_level: int) -> float | None:
    hits = [a["t"] for a in alerts if LEVELS[a["level"]] >= min_level]
    return min(hits) if hits else None


def max_level(alerts: list[dict]) -> int:
    return max((LEVELS[a["level"]] for a in alerts), default=0)


def max_score(alerts: list[dict]) -> float:
    return max((float(a.get("score", 0.0)) for a in alerts), default=0.0)


def pct(n: int, d: int) -> str:
    return "n/a" if d == 0 else f"{100 * n / d:.1f}% ({n}/{d})"


def percentile(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, round(q * (len(xs) - 1))))
    return xs[k]


def calibration(
    pairs: list[tuple[float, bool]], bins: int = 5
) -> tuple[float, list[tuple[str, int, float, float]]]:
    table, ece, n = [], 0.0, len(pairs)
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        inbin = [(s, y) for s, y in pairs if (lo <= s < hi) or (b == bins - 1 and s == 1.0)]
        if not inbin:
            continue
        conf = statistics.mean(s for s, _ in inbin)
        acc = statistics.mean(1.0 if y else 0.0 for _, y in inbin)
        ece += len(inbin) / n * abs(conf - acc)
        table.append((f"{lo:.1f}-{hi:.1f}", len(inbin), conf, acc))
    return ece, table


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, required=True)
    ap.add_argument("--preds", type=Path, required=True)
    ap.add_argument("--gate", action="store_true", help="fail on threshold misses")
    ap.add_argument("--min-catch-alert", type=float, default=0.80)
    ap.add_argument("--max-false-alert", type=float, default=0.05)
    args = ap.parse_args()

    cases, preds = load_cases(args.cases), load_preds(args.preds)
    missing = [sid for sid in cases if sid not in preds]
    scam = [c for c in cases.values() if c["label"]["scam"]]
    benign = [c for c in cases.values() if not c["label"]["scam"]]
    hard = [c for c in benign if c["label"].get("hard_negative")]

    def alerts(c: dict) -> list[dict]:
        return preds.get(c["session_id"], {}).get("alerts", [])

    out = ["# Safe Signal eval report", ""]
    out.append(
        f"Sessions: {len(cases)} ({len(scam)} scam, {len(benign)} benign, {len(hard)} hard negatives). Missing predictions: {len(missing)}."
    )
    out += [
        "",
        "## Catch rate and false interventions",
        "",
        "| Level reached | Catch rate (scam) | False rate (benign) | False rate (hard negatives) |",
        "| --- | --- | --- | --- |",
    ]
    rates = {}
    for name in ("nudge", "whisper", "alert"):
        lv = LEVELS[name]
        caught = sum(max_level(alerts(c)) >= lv for c in scam)
        false_b = sum(max_level(alerts(c)) >= lv for c in benign)
        false_h = sum(max_level(alerts(c)) >= lv for c in hard)
        rates[name] = (caught / len(scam) if scam else 0.0, false_b / len(benign) if benign else 0.0)
        out.append(
            f"| {name} | {pct(caught, len(scam))} | {pct(false_b, len(benign))} | {pct(false_h, len(hard))} |"
        )

    by_type: dict[str, list[dict]] = defaultdict(list)
    for c in scam:
        by_type[c["label"]["type"]].append(c)
    out += ["", "## Catch rate at alert, by scam type", "", "| Type | Catch rate |", "| --- | --- |"]
    for t, cs in sorted(by_type.items()):
        out.append(f"| {t} | {pct(sum(max_level(alerts(c)) >= LEVELS['alert'] for c in cs), len(cs))} |")

    deltas = []
    for c in scam:
        ft, ask = first_t_at(alerts(c), LEVELS["whisper"]), c["label"].get("first_scam_t")
        if ft is not None and ask is not None:
            deltas.append(ft - ask)
    out += ["", "## Time to detect (first whisper or higher, seconds after the scam ask)", ""]
    if deltas:
        out.append(
            f"Median {statistics.median(deltas):+.1f} s, p90 {percentile(deltas, 0.9):+.1f} s, n={len(deltas)}. Negative means caught before the ask."
        )
    else:
        out.append("No detections with a labeled ask time.")

    ece, table = calibration([(max_score(alerts(c)), c["label"]["scam"]) for c in cases.values()])
    out += [
        "",
        f"## Calibration (ECE {ece:.3f}, lower is better)",
        "",
        "| Score bin | Sessions | Mean score | Share actually scam |",
        "| --- | --- | --- | --- |",
    ]
    out += [f"| {b} | {n} | {conf:.2f} | {acc:.2f} |" for b, n, conf, acc in table]

    lat = [float(x) for p in preds.values() for x in p.get("latency_ms", [])]
    out += ["", "## Latency", ""]
    out.append(
        f"p50 {percentile(lat, 0.5):.0f} ms, p95 {percentile(lat, 0.95):.0f} ms, n={len(lat)}."
        if lat
        else "No latency recorded."
    )
    print("\n".join(out))

    if args.gate:
        catch, false = rates["alert"]
        fails = []
        if missing:
            fails.append(f"{len(missing)} sessions have no prediction")
        if catch < args.min_catch_alert:
            fails.append(f"catch at alert {catch:.2f} < {args.min_catch_alert}")
        if false > args.max_false_alert:
            fails.append(f"false alerts {false:.2f} > {args.max_false_alert}")
        if fails:
            print("\nGATE FAILED: " + "; ".join(fails), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
