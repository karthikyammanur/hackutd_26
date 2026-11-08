"""Compile the individually written eval set (sessions.txt) into one EvalCase JSON per session in data/eval/.

Every session is validated against contracts.events.EvalCase; a malformed block aborts the build.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from contracts.events import EvalCase  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
SENDERS = {"bank": "bank_shortcode", "other": "other_shortcode", "long": "longcode"}


def parse_block(lines: list[str]) -> dict:
    head = lines[0].removeprefix("## ").split()
    sid, type_, cls = head[0], head[1], head[2]
    ask = next((float(h.split("=", 1)[1]) for h in head[3:] if h.startswith("ask=")), None)
    if cls not in {"scam", "hard", "easy"}:
        raise ValueError(f"{sid}: bad class {cls}")
    if (cls == "scam") != (ask is not None):
        raise ValueError(f"{sid}: scams need ask=, benign sessions must not have it")

    call = lines[1].split(maxsplit=4)
    direction = {"in": "inbound", "out": "outbound"}[call[0]]
    verified = call[4].split("=", 1)[1] if len(call) > 4 else None
    base = {"session_id": sid}
    events: list[dict] = [
        {
            **base,
            "t": 0,
            "source": "network",
            "kind": "call_start",
            "direction": direction,
            "number": call[1],
            "carrier_label": "none",
            "attestation": call[2],
            "first_seen": call[3] == "first",
            "verified_org": verified,
        }
    ]
    for raw in lines[2:]:
        t_str, tag, *rest = raw.split(maxsplit=2)
        t = float(t_str)
        body = rest[0] if rest else ""
        row = {**base, "t": t, "source": "network"}
        if tag in {"C", "U"}:
            row |= {"kind": "turn", "speaker": "caller" if tag == "C" else "customer", "text": body}
        elif tag == "OTP":
            sender, _, org = body.partition(" ")
            row |= {"kind": "sms_otp", "sender_type": SENDERS[sender], "org": org or None}
        elif tag == "APP":
            row |= {"kind": "bank_app_traffic", "org": body or None}
        elif tag == "ACC":
            action, status = body.split()
            row |= {"kind": "account_change", "action": action, "status": status}
            if status == "held":
                row["source"] = "system"
        elif tag == "END":
            row |= {"kind": "call_end"}
        else:
            raise ValueError(f"{sid}: unknown tag {tag}")
        events.append(row)

    return {
        "session_id": sid,
        "label": {
            "scam": cls == "scam",
            "type": type_,
            "hard_negative": cls == "hard",
            "first_scam_t": ask,
        },
        "events": events,
    }


def parse(text: str) -> list[dict]:
    blocks: list[list[str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or (line.startswith("#") and not line.startswith("## ")):
            continue
        if line.startswith("## "):
            blocks.append([])
        blocks[-1].append(line)
    return [parse_block(b) for b in blocks]


def main() -> int:
    rows = parse((HERE / "sessions.txt").read_text(encoding="utf-8"))
    ids = [r["session_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate session ids")
    for old in OUT.glob("*.json"):
        old.unlink()
    for row in rows:
        case = EvalCase.model_validate(row)
        ts = [e.t for e in case.events]
        if ts != sorted(ts) or case.events[-1].kind != "call_end":
            raise ValueError(f"{case.session_id}: events out of order or no call_end")
        (OUT / f"{case.session_id}.json").write_text(case.model_dump_json(indent=1) + "\n", encoding="utf-8")
    scams = sum(r["label"]["scam"] for r in rows)
    hard = sum(r["label"]["hard_negative"] for r in rows)
    print(
        f"{len(rows)} sessions: {scams} scam, {len(rows) - scams} benign, {hard} hard negatives ({100 * hard / len(rows):.0f}%)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
