"""Choose decision thresholds on TRAINING data. Refuses to read data/eval, so eval numbers stay honest.

For each level it prints the score cut that catches the most scams while keeping false positives within
the budget. Results are advisory: a person copies them to services/agents/decision/config.py.

  python evals/tune.py --cases data/train
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts.events import EvalCase  # noqa: E402
from evals.replay import Flagger, load_eval_cases, no_flags, replay_case  # noqa: E402
from evals.stand_in_guardian import flag_turn  # noqa: E402

BUDGETS = {"nudge": 0.30, "whisper": 0.10, "alert": 0.05}


def session_scores(cases: list[EvalCase], flagger: Flagger) -> list[tuple[float, EvalCase]]:
    rows = []
    for case in cases:
        risk = replay_case(case, flagger=flagger).state.risk
        rows.append((risk.score if risk else 0.0, case))
    return rows


def rate(scores: list[float], cut: float) -> float:
    return sum(s >= cut for s in scores) / len(scores) if scores else 0.0


def best_cut(scam: list[float], benign: list[float], budget: float) -> float:
    """Highest-recall cut within the false-positive budget; ties go to the middle of the feasible band."""
    feasible = [c / 100 for c in range(5, 100) if rate(benign, c / 100) <= budget]
    if not feasible:
        return 1.0
    top = max(rate(scam, c) for c in feasible)
    band = [c for c in feasible if rate(scam, c) == top]
    return band[len(band) // 2]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, required=True)
    ap.add_argument("--flags", choices=["none", "keyword"], default="keyword")
    args = ap.parse_args()
    if "eval" in args.cases.resolve().parts:
        print("Refusing to tune on data/eval (see evals/README.md).", file=sys.stderr)
        return 2

    flagger = flag_turn if args.flags == "keyword" else no_flags
    rows = session_scores(load_eval_cases(args.cases), flagger)
    scam = [s for s, c in rows if c.label.scam]
    benign = [s for s, c in rows if not c.label.scam]
    hard = [s for s, c in rows if c.label.hard_negative]
    print(f"{len(rows)} sessions: {len(scam)} scam, {len(benign)} benign, {len(hard)} hard negatives\n")
    print("level    cut   catch  false(benign)  false(hard)")
    for level, budget in BUDGETS.items():
        cut = best_cut(scam, benign, budget)
        print(
            f"{level:8} {cut:.2f}  {rate(scam, cut):.3f}  {rate(benign, cut):.3f}          {rate(hard, cut):.3f}"
        )

    print("\nmissed at the configured alert threshold, by type:")
    from services.agents.decision import config

    by_type: dict[str, list[float]] = {}
    for s, c in rows:
        if c.label.scam:
            by_type.setdefault(c.label.type, []).append(s)
    for t, ss in sorted(by_type.items()):
        print(f"  {t:26} {sum(s < config.ALERT for s in ss)}/{len(ss)}")
    print("\nfalse alerts at the configured alert threshold, by type:")
    fp: dict[str, list[float]] = {}
    for s, c in rows:
        if not c.label.scam:
            fp.setdefault(c.label.type, []).append(s)
    for t, ss in sorted(fp.items()):
        print(f"  {t:26} {sum(s >= config.ALERT for s in ss)}/{len(ss)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
