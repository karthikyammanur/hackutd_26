"""Compare Jev's tiers against the labels. All numbers come from here, never from an LLM."""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass

from sandbox.graph import CallResult

# (is scam, tier reached) -> (outcome, points). "uncertain" earns half: it isn't a clean result either way.
OUTCOMES: dict[tuple[bool, str], tuple[str, float]] = {
    (True, "dangerous"): ("caught", 1.0),
    (True, "uncertain"): ("soft_miss", 0.5),
    (True, "safe"): ("missed", 0.0),
    (False, "safe"): ("clear", 1.0),
    (False, "uncertain"): ("soft_false_alarm", 0.5),
    (False, "dangerous"): ("false_alarm", 0.0),
}
FAILURES = frozenset({"soft_miss", "missed", "soft_false_alarm", "false_alarm", "no_verdict"})


@dataclass(frozen=True)
class Row:
    session_id: str
    scam_type: str
    scam: bool
    hard_negative: bool
    expected: str
    tier: str | None
    outcome: str
    points: float
    max_p_dangerous: float
    first_dangerous_t: float | None
    money_moment_t: float | None
    caught_before_money: bool | None
    frames: int
    frames_answered: int


def score_call(result: CallResult) -> Row:
    session, tier = result.session, result.tier
    outcome, points = OUTCOMES[(session.scam, tier)] if tier is not None else ("no_verdict", 0.0)
    first, money = result.first_dangerous_t, session.money_moment_t
    return Row(
        session_id=session.session_id,
        scam_type=session.scam_type,
        scam=session.scam,
        hard_negative=session.hard_negative,
        expected="dangerous" if session.scam else "safe",
        tier=tier,
        outcome=outcome,
        points=points,
        max_p_dangerous=round(result.max_p_dangerous, 4),
        first_dangerous_t=first,
        money_moment_t=money,
        caught_before_money=None if money is None else (first is not None and first <= money),
        frames=len(result.frames),
        frames_answered=len(result.answered),
    )


def _rate(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _percentile(values: list[int], q: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def build_scoreboard(results: list[CallResult], rows: list[Row]) -> dict:
    by_type: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        by_type[row.scam_type].append(row)

    types = []
    for scam_type, group in sorted(by_type.items()):
        outcomes = defaultdict(int)
        for row in group:
            outcomes[row.outcome] += 1
        points = sum(r.points for r in group)
        times = [r.first_dangerous_t for r in group if r.first_dangerous_t is not None]
        types.append(
            {
                "type": scam_type,
                "scam": group[0].scam,
                "hard_negative": group[0].hard_negative,
                "n": len(group),
                "points_pct": _rate(points, len(group)),
                "error_rate": _rate(len(group) - points, len(group)),
                "outcomes": dict(outcomes),
                "mean_max_p_dangerous": round(statistics.mean(r.max_p_dangerous for r in group), 4),
                "median_first_dangerous_t": statistics.median(times) if times else None,
            }
        )

    scams = [r for r in rows if r.scam]
    benign = [r for r in rows if not r.scam]
    hard = [r for r in benign if r.hard_negative]
    money = [r for r in scams if r.caught_before_money is not None]
    frames = [f for result in results for f in result.frames]
    jev_ms = [f.jev_ms for f in frames if f.jev_ms is not None]
    brief_ms = [f.brief_ms for f in frames if f.brief_ms is not None]
    confusion = {
        "scam": {t: sum(r.tier == t for r in scams) for t in ("dangerous", "uncertain", "safe", None)},
        "benign": {t: sum(r.tier == t for r in benign) for t in ("dangerous", "uncertain", "safe", None)},
    }
    return {
        "sessions": len(rows),
        "scams": len(scams),
        "benign": len(benign),
        "hard_negatives": len(hard),
        "overall_points_pct": _rate(sum(r.points for r in rows), len(rows)),
        "catch_rate": _rate(sum(r.outcome == "caught" for r in scams), len(scams)),
        "false_alarm_rate": _rate(sum(r.outcome == "false_alarm" for r in benign), len(benign)),
        "hard_negative_false_alarm_rate": _rate(sum(r.outcome == "false_alarm" for r in hard), len(hard)),
        "caught_before_money": _rate(sum(bool(r.caught_before_money) for r in money), len(money)),
        "caught_before_money_n": len(money),
        "confusion": {k: {str(t): n for t, n in v.items()} for k, v in confusion.items()},
        "by_type": types,
        "delivery": {
            "frames": len(frames),
            "delivered": sum(f.delivered for f in frames),
            "delivered_rate": _rate(sum(f.delivered for f in frames), len(frames)),
            "agent_failures": sum(not f.agent_ok for f in frames),
            "jev_failures": sum(f.tier is None for f in frames),
            "jev_ms_p50": _percentile(jev_ms, 0.5),
            "jev_ms_p95": _percentile(jev_ms, 0.95),
            "agent_ms_p50": _percentile(brief_ms, 0.5),
            "agent_ms_p95": _percentile(brief_ms, 0.95),
            "jev_input_tokens": sum(f.input_tokens for f in frames),
            "jev_output_tokens": sum(f.output_tokens for f in frames),
        },
    }


def row_dict(row: Row) -> dict:
    return asdict(row)


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"


def scoreboard_markdown(run_id: str, board: dict) -> str:
    delivery = board["delivery"]
    lines = [
        f"# Sandbox scoreboard: {run_id}",
        "",
        f"{board['sessions']} calls: {board['scams']} scams, {board['benign']} benign "
        f"({board['hard_negatives']} hard negatives).",
        "",
        "| Metric | Result |",
        "| --- | --- |",
        f"| Overall score | {_pct(board['overall_points_pct'])} |",
        f"| Scams reaching `dangerous` | {_pct(board['catch_rate'])} |",
        f"| Benign calls reaching `dangerous` | {_pct(board['false_alarm_rate'])} |",
        f"| Hard negatives reaching `dangerous` | {_pct(board['hard_negative_false_alarm_rate'])} |",
        f"| Flagged before the money moved (n={board['caught_before_money_n']}) "
        f"| {_pct(board['caught_before_money'])} |",
        "",
        "## By call type",
        "",
        "| Type | Kind | n | Score | Outcomes | Mean peak P(dangerous) | Median first flag (s) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in sorted(board["by_type"], key=lambda x: (x["points_pct"], x["type"])):
        kind = "scam" if item["scam"] else ("hard negative" if item["hard_negative"] else "benign")
        outcomes = ", ".join(f"{k} {v}" for k, v in sorted(item["outcomes"].items()))
        median = item["median_first_dangerous_t"]
        lines.append(
            f"| {item['type']} | {kind} | {item['n']} | {_pct(item['points_pct'])} | {outcomes} "
            f"| {item['mean_max_p_dangerous']:.2f} | {'-' if median is None else f'{median:g}'} |"
        )
    lines += [
        "",
        "Scoring: right tier 1 point, `uncertain` half, wrong tier 0. A call's tier is the highest any frame reached.",
        "",
        "## Pipeline health",
        "",
        f"- Frames delivered to Jev with a valid answer: {delivery['delivered']}/{delivery['frames']} "
        f"({_pct(delivery['delivered_rate'])})",
        f"- Nemotron agent failures: {delivery['agent_failures']}. Jev failures: {delivery['jev_failures']}.",
        f"- Latency: Jev p50 {delivery['jev_ms_p50']} ms, p95 {delivery['jev_ms_p95']} ms. "
        f"Agent p50 {delivery['agent_ms_p50']} ms, p95 {delivery['agent_ms_p95']} ms.",
        f"- Jev tokens: {delivery['jev_input_tokens']} in, {delivery['jev_output_tokens']} out.",
    ]
    return "\n".join(lines) + "\n"
