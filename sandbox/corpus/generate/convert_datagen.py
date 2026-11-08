"""Convert the team's generated data (test/datagen, test/proto) to Case format.

    python3 sandbox/corpus/generate/convert_datagen.py

Writes out/datagen_calls.jsonl and out/datagen_sms.jsonl. Leaky fields (caller, number, carrier labels,
campaign ids, customer data) and pre-call DNS events are dropped.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path

from common import OUT, load_taxonomy, make_case, write_jsonl

TEST = Path("/Users/berny/Desktop/code/test")
KEEP_CALL_EVENTS = {"turn", "sms_otp", "bank_app_open", "bank_transfer", "account"}
HARD_CALL_TYPES = {"benign_real_bank_alert", "benign_real_carrier_care", "benign_bank", "benign_otp"}
HARD_SMS_CATEGORIES = {"otp", "bank_alert", "carrier_notice", "appointment"}
DATES = ["Nov 12", "Nov 14", "Nov 18", "Nov 21", "Dec 2", "Dec 5", "Monday", "Thursday", "next Tuesday"]
TIMES = ["9:15 AM", "10:30 AM", "11:45 AM", "1:20 PM", "2:40 PM", "3:50 PM", "4:30 PM"]


def fill_placeholders(text: str, key: str) -> str:
    if "{" not in text:
        return text
    rng = random.Random(hashlib.sha256(key.encode()).hexdigest())
    return text.replace("{date}", rng.choice(DATES)).replace("{time}", rng.choice(TIMES))


def clean_event(event: dict) -> dict:
    if event["kind"] == "turn":
        return {"t": event["t"], "kind": "turn", "who": event.get("who"), "text": event.get("text", "")}
    return {k: v for k, v in event.items() if k not in {"number", "caller", "label"}}


def convert_calls(taxonomy, unmapped: Counter):
    for path, prefix in (
        (TEST / "datagen/out/sessions.jsonl", "dg-call"),
        (TEST / "proto/data/synthetic.jsonl", "proto-call"),
    ):
        with path.open() as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                label = row["label"]
                scam = bool(label["scam"])
                method = taxonomy.method_for(label["type"], scam)
                if method not in taxonomy.METHODS:
                    unmapped[label["type"]] += 1
                    continue
                start = next((e for e in row["events"] if e["kind"] == "call_start"), {})
                yield make_case(
                    case_id=f"{prefix}-{row['session_id']}",
                    channel="call",
                    source="datagen",
                    scam=scam,
                    method=method,
                    family=taxonomy.METHODS[method][0],
                    hard_negative=(not scam) and label["type"] in HARD_CALL_TYPES,
                    money_moment_t=label.get("money_moment_t"),
                    direction=start.get("direction", "unknown"),
                    events=[clean_event(e) for e in row["events"] if e["kind"] in KEEP_CALL_EVENTS],
                )


def from_type(sender: str) -> str:
    if re.fullmatch(r"\d{5,6}", sender or ""):
        return "shortcode"
    if (sender or "").startswith("+"):
        return "longcode"
    return "alphanumeric"


def convert_sms(taxonomy, unmapped: Counter) -> tuple[list[dict], dict]:
    scams: dict[str, dict] = {}
    benign: dict[str, list[dict]] = {}
    seen: set[str] = set()
    stats = Counter()
    with (TEST / "datagen/out/sms.jsonl").open() as handle:
        for line in handle:
            row = json.loads(line)
            text = fill_placeholders(row["text"], row["sms_id"])
            stats["rows"] += 1
            if text in seen:
                continue
            seen.add(text)
            scam = bool(row["scam"])
            call_type = row.get("smish_type") if scam else "benign_sms"
            method = taxonomy.method_for(call_type, scam)
            if method not in taxonomy.METHODS:
                unmapped[call_type] += 1
                continue
            case = make_case(
                case_id=f"dg-sms-{row['sms_id']}",
                channel="sms",
                source="datagen",
                scam=scam,
                method=method,
                family=taxonomy.METHODS[method][0],
                hard_negative=(not scam) and row["category"] in HARD_SMS_CATEGORIES,
                money_moment_t=None,
                direction="inbound",
                events=[
                    {
                        "t": 0,
                        "kind": "sms",
                        "from_type": from_type(row.get("from", "")),
                        "text": text,
                        "domain": row.get("domain"),
                        "domain_age_days": row.get("domain_age_days"),
                    }
                ],
            )
            if scam:
                scams[text] = case
            else:
                benign.setdefault(row["category"], []).append(case)

    # OTP texts differ only by their digits, so cap them to bring benign volume level with scams, not above.
    otp = benign.pop("otp", [])
    others = [case for group in benign.values() for case in group]
    room = max(0, len(scams) - len(others))
    random.Random(20261108).shuffle(otp)
    kept_otp = otp[:room]
    stats["otp_unique"] = len(otp)
    stats["otp_kept"] = len(kept_otp)
    return [*scams.values(), *others, *kept_otp], dict(stats)


def main() -> None:
    taxonomy = load_taxonomy()
    unmapped: Counter = Counter()
    calls = write_jsonl(OUT / "datagen_calls.jsonl", convert_calls(taxonomy, unmapped))
    sms_rows, stats = convert_sms(taxonomy, unmapped)
    sms = write_jsonl(OUT / "datagen_sms.jsonl", sms_rows)
    print(f"calls {calls}, sms {sms}, sms stats {stats}, unmapped {dict(unmapped)}")


if __name__ == "__main__":
    main()
