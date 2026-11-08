"""Generate labeled synthetic calls and texts for every scam method, each with a legitimate twin.

    python3 sandbox/corpus/generate/generate.py [--per-method 500] [--seed 20261108]

Writes out/generated_calls.jsonl, out/generated_sms.jsonl and out/generated_report.json. The report includes
duplicate rates and a label-leakage audit (length, turn counts, single-token separability).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import statistics
from collections import Counter, defaultdict

from banks import (
    BANKS,
    BENIGN_SMS_BRIDGES,
    CUSTOMER_LINES,
    EVERYDAY_CALLS,
    EVERYDAY_SMS,
    GENERIC,
    HANDOFF,
    LEGIT_DOMAIN_WORDS,
    LEGIT_SUFFIX,
    LEGIT_TLDS,
    NEUTRAL_CALLER,
    SCAM_DOMAIN_WORDS,
    SCAM_TLDS,
    SHARED_CALL_LINES,
    SHARED_SMS_TAILS,
    SLOTS,
)
from common import OUT, load_taxonomy, make_case, write_jsonl

OTP_HEAVY = {"bank_fraud_department", "otp_interception", "carrier_impersonation", "sim_swap_port_out", "account_verification_phish", "marketplace_rental"}
OUTBOUND_CALLBACK = {"subscription_callback", "tech_support", "refund_overpayment", "carrier_impersonation"}
THREADED = {"wrong_number_romance", "job_task_scam", "investment_crypto", "marketplace_rental", "family_emergency_voice_clone"}
# Scam calls cut off before any ask reach this share: labeled scams that give the detector little to go on.
EARLY_END_SHARE = 0.1
MULTI_STAGE_SHARE = 0.15


class Filler(dict):
    """Slots for one conversation, so a name or org stays consistent across its turns."""

    def __init__(self, rng: random.Random):
        super().__init__({key: rng.choice(values) for key, values in SLOTS.items()})
        self["agent"], self["agent2"] = (f"{rng.choice(SLOTS['first'])}", f"{rng.choice(SLOTS['first'])} {rng.choice(SLOTS['last'])}")
        self["tiny"] = f"${rng.choice([1.99, 2.49, 3.75, 4.20, 6.50, 11.70, 12.95])}"
        self["small"] = f"${rng.randrange(25, 900, 5)}"
        self["big"] = f"${rng.randrange(1200, 48000, 100):,}"
        self["last4"] = f"{rng.randrange(1000, 9999)}"
        self["digits"] = f"{rng.randrange(100000, 999999)}"
        self["phone"] = f"({rng.randrange(201, 989)}) 555-01{rng.randrange(10, 99)}"
        self["domain"], self["domain_age"] = _scam_domain(rng)
        self["t_domain"], self["t_domain_age"] = _legit_domain(rng)
        self["link"] = self["domain"]
        self["t_link"] = self["t_domain"]


def _scam_domain(rng: random.Random) -> tuple[str, int]:
    name = f"{rng.choice(SCAM_DOMAIN_WORDS)}-{rng.choice(SCAM_DOMAIN_WORDS)}{rng.randrange(1, 99)}.{rng.choice(SCAM_TLDS)}"
    return name, rng.randrange(180, 1400) if rng.random() < 0.1 else rng.randrange(1, 45)


def _legit_domain(rng: random.Random) -> tuple[str, int]:
    suffix = rng.choice(LEGIT_SUFFIX)
    name = f"{rng.choice(LEGIT_DOMAIN_WORDS)}{'-' + suffix if suffix else ''}.{rng.choice(LEGIT_TLDS)}"
    return name, rng.randrange(25, 120) if rng.random() < 0.08 else rng.randrange(400, 6000)


def fill(template: str, slots: Filler) -> str:
    return template.format_map(slots)


def add_times(rng: random.Random, lines: list[tuple[str, str]]) -> list[dict]:
    t = rng.randrange(3, 14)
    events = []
    for who, text in lines:
        events.append({"t": t, "kind": "turn", "who": who, "text": text})
        t += rng.randrange(5, 18)
    return events


def weave_customer(rng: random.Random, caller_lines: list[str]) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    for line in caller_lines:
        lines.append(("caller", line))
        if rng.random() < 0.75:
            lines.append(("customer", rng.choice(CUSTOMER_LINES)))
    return lines


def caller_script(rng: random.Random, sections: list[list[str]], slots: Filler, target: int, handoff: bool) -> list[str]:
    """Draws one line per section, then pads with neutral lines to a target shared by scams and twins."""
    lines = [fill(rng.choice(section), slots) for section in sections]
    if handoff:
        lines.insert(rng.randrange(1, max(2, len(lines))), fill(rng.choice(HANDOFF), slots))
    while len(lines) < target:
        filler = rng.choice(SHARED_CALL_LINES) if rng.random() < 0.5 else rng.choice(NEUTRAL_CALLER)
        lines.insert(rng.randrange(1, len(lines) + 1), fill(filler, slots))
    return lines


def add_signals(rng: random.Random, events: list[dict], method: str, scam: bool, slots: Filler) -> float | None:
    """Phone signals appear on both sides, so they are evidence and not a label."""
    money_t = None
    if not events:
        return None
    last_t = events[-1]["t"]
    otp_p = (0.6 if scam else 0.4) if method in OTP_HEAVY else (0.2 if scam else 0.12)
    if rng.random() < otp_p:
        events.append({"t": rng.randrange(max(1, last_t // 3), last_t + 2), "kind": "sms_otp", "sender": slots["bank"]})
    if rng.random() < (0.25 if scam else 0.18):
        events.append({"t": rng.randrange(max(1, last_t // 2), last_t + 2), "kind": "bank_app_open"})
    if rng.random() < (0.2 if scam else 0.1):
        t = rng.randrange(max(1, last_t // 2), last_t + 3)
        amount = rng.randrange(150, 9000, 50) if scam else rng.randrange(25, 400, 5)
        events.append({"t": t, "kind": "bank_transfer", "amount": amount, "payee": f"{rng.choice(SLOTS['first'])} {rng.choice(SLOTS['last'])}", "newPayee": scam or rng.random() < 0.2})
        if scam:
            money_t = t
    if method == "sim_swap_port_out" and rng.random() < (0.6 if scam else 0.3):
        events.append({"t": rng.randrange(max(1, last_t // 2), last_t + 2), "kind": "account", "action": rng.choice(["sim_change_attempt", "port_out_attempt"])})
    return money_t


def scam_call(rng, bank, method, slots):
    target = rng.randint(4, 8)
    early = rng.random() < EARLY_END_SHARE
    sections = [bank["open"], bank["hook"]] if early else [bank["open"], bank["hook"], bank["ask"]]
    if not early and rng.random() < 0.7:
        sections.append(bank["press"])
    if method == "phantom_hacker" and not early:
        sections.insert(2, bank["hook"])
    handoff = (not early) and (method == "phantom_hacker" or rng.random() < MULTI_STAGE_SHARE)
    return caller_script(rng, sections, slots, target, handoff)


def twin_call(rng, bank, slots):
    target = rng.randint(4, 8)
    sections = [bank["t_open"], bank["t_body"], bank["t_body"], bank["t_close"]] if rng.random() < 0.7 else [bank["t_open"], bank["t_body"], bank["t_close"]]
    return caller_script(rng, sections, slots, target, rng.random() < MULTI_STAGE_SHARE)


def from_type(rng: random.Random, scam: bool) -> str:
    weights = (0.7, 0.15, 0.15) if scam else (0.2, 0.45, 0.35)
    return rng.choices(["longcode", "shortcode", "alphanumeric"], weights)[0]


def sms_event(rng, template, slots, sender, t, scam: bool) -> dict:
    text = fill(template, slots)
    if rng.random() < 0.45:
        text = f"{text} {fill(rng.choice(SHARED_SMS_TAILS), slots)}"
    if not scam and rng.random() < 0.3:
        text = f"{text} {fill(rng.choice(BENIGN_SMS_BRIDGES), slots)}"
    domain, age = None, None
    if slots["domain"] in text:
        domain, age = slots["domain"], slots["domain_age"]
    elif slots["t_domain"] in text:
        domain, age = slots["t_domain"], slots["t_domain_age"]
    return {"t": t, "kind": "sms", "from_type": sender, "text": text, "domain": domain, "domain_age_days": age}


def build_sms(rng, pool, method, scam: bool, slots) -> list[dict]:
    sender = from_type(rng, scam)
    count = rng.choices([1, 2, 3], (0.45, 0.35, 0.2))[0] if method in THREADED else rng.choices([1, 2], (0.8, 0.2))[0]
    templates = rng.sample(pool, min(count, len(pool)))
    t, events = 0, []
    for template in templates:
        events.append(sms_event(rng, template, slots, sender, t, scam))
        t += rng.randrange(600, 172800)
    return events


def unique_sms(rng, pool, method, scam: bool, seen: set[str]) -> list[dict]:
    """Retries so exact duplicate texts are rare. A fill can still repeat when a template has few slots."""
    events: list[dict] = []
    for _ in range(12):
        events = build_sms(rng, pool, method, scam, Filler(rng))
        key = "|".join(e["text"] for e in events)
        if key not in seen:
            seen.add(key)
            break
    return events


def generate(per_method: int, seed: int):
    taxonomy = load_taxonomy()
    rng = random.Random(seed)
    calls, sms, fallback = [], [], []
    methods = sorted(m for m in taxonomy.METHODS if m != "legitimate")
    counters = {"call": 0, "sms": 0}
    seen_sms: set[str] = set()

    def next_id(channel):
        counters[channel] += 1
        return f"gen-{channel}-{counters[channel]:06d}"

    def add_call(scam, method, family, hard, caller_lines, direction, signal_method, slots):
        events = add_times(rng, weave_customer(rng, caller_lines))
        money = add_signals(rng, events, signal_method, scam, slots)
        events.sort(key=lambda e: e["t"])
        calls.append(make_case(next_id("call"), "call", "generated", scam, method, family, hard, money, direction, events))

    for method in methods:
        family = taxonomy.METHODS[method][0]
        bank = BANKS.get(method)
        if bank is None:
            bank = GENERIC
            fallback.append(method)
        outbound_share = 0.3 if method in OUTBOUND_CALLBACK else 0.05
        for _ in range(per_method):
            direction = "outbound" if rng.random() < outbound_share else "inbound"
            slots = Filler(rng)
            add_call(True, method, family, False, scam_call(rng, bank, method, slots), direction, method, slots)
            slots = Filler(rng)
            add_call(False, "legitimate", "none", True, twin_call(rng, bank, slots), direction, method, slots)

            sms.append(make_case(next_id("sms"), "sms", "generated", True, method, family, False, None, "inbound", unique_sms(rng, bank["sms"], method, True, seen_sms)))
            sms.append(make_case(next_id("sms"), "sms", "generated", False, "legitimate", "none", True, None, "inbound", unique_sms(rng, bank["t_sms"], method, False, seen_sms)))

    # Ordinary everyday traffic: benign but not designed to look like a scam.
    for _ in range(max(1, per_method * len(methods) // 10)):
        slots = Filler(rng)
        target = rng.randint(4, 8)
        script = [fill(line, slots) for line in rng.choice(EVERYDAY_CALLS)]
        while len(script) < target:
            script.insert(rng.randrange(1, len(script) + 1), rng.choice(NEUTRAL_CALLER))
        add_call(False, "legitimate", "none", False, script, "inbound", "everyday", slots)
        slots = Filler(rng)
        sms.append(make_case(next_id("sms"), "sms", "generated", False, "legitimate", "none", False, None, "inbound", [sms_event(rng, rng.choice(EVERYDAY_SMS), slots, rng.choice(["longcode", "shortcode"]), 0, False)]))
    return calls, sms, fallback


def case_text(case) -> str:
    return " ".join(e.get("text", "") for e in case["events"])


def normalize(text: str) -> str:
    text = re.sub(r"\$[\d,.]+", "$", text.lower())
    text = re.sub(r"\d+", "#", text)
    for pool in ("first", "last", "bank", "store", "courier", "tollway", "utility", "tech", "insurer", "clinic", "charity", "company", "city"):
        for value in SLOTS[pool]:
            text = text.replace(value.lower(), "@")
    return re.sub(r"[a-z-]+#?\.(click|top|buzz|site|club|info|com|net|org)", "<url>", text)


def duplicate_rates(cases) -> dict:
    exact, norm = Counter(), Counter()
    for case in cases:
        text = case_text(case)
        exact[hashlib.sha256(text.encode()).hexdigest()] += 1
        norm[hashlib.sha256(normalize(text).encode()).hexdigest()] += 1
    return {
        "cases": len(cases),
        "exact_duplicate_rate": round(1 - len(exact) / max(1, len(cases)), 4),
        "normalized_duplicate_rate": round(1 - len(norm) / max(1, len(cases)), 4),
        "note": "normalized collapses names, orgs, digits, amounts and URLs, so it measures template reuse",
    }


def leakage_audit(cases, name: str) -> dict:
    groups = {True: [c for c in cases if c["scam"]], False: [c for c in cases if not c["scam"]]}
    stats = {}
    for label, group in groups.items():
        chars = [len(case_text(c)) for c in group]
        events = [len(c["events"]) for c in group]
        stats["scam" if label else "benign"] = {
            "n": len(group),
            "mean_chars": round(statistics.mean(chars), 1),
            "mean_events": round(statistics.mean(events), 2),
        }
    doc_freq = {True: Counter(), False: Counter()}
    for label, group in groups.items():
        for case in group:
            doc_freq[label].update(set(re.findall(r"[a-z]+", case_text(case).lower())))
    gap = []
    n_scam, n_benign = max(1, len(groups[True])), max(1, len(groups[False]))
    for token in set(doc_freq[True]) | set(doc_freq[False]):
        p_scam, p_benign = doc_freq[True][token] / n_scam, doc_freq[False][token] / n_benign
        gap.append((abs(p_scam - p_benign), token, round(p_scam, 3), round(p_benign, 3)))
    gap.sort(reverse=True)
    best = gap[0][0] if gap else 0
    return {
        "name": name,
        **stats,
        "best_single_token_accuracy": round(0.5 + best / 2, 4),
        "top_separating_tokens": [{"token": t, "p_scam": s, "p_benign": b} for _, t, s, b in gap[:12]],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-method", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20261108)
    args = parser.parse_args()
    calls, sms, fallback = generate(args.per_method, args.seed)
    write_jsonl(OUT / "generated_calls.jsonl", calls)
    write_jsonl(OUT / "generated_sms.jsonl", sms)
    counts = defaultdict(Counter)
    for case in [*calls, *sms]:
        counts[case["channel"]][case["method"]] += 1
    report = {
        "seed": args.seed,
        "per_method": args.per_method,
        "methods_using_generic_fallback": fallback,
        "counts": {k: dict(v) for k, v in counts.items()},
        "duplicates": {"calls": duplicate_rates(calls), "sms": duplicate_rates(sms)},
        "leakage": [leakage_audit(calls, "calls"), leakage_audit(sms, "sms")],
    }
    (OUT / "generated_report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: report[k] for k in ("methods_using_generic_fallback", "duplicates", "leakage")}, indent=1))


if __name__ == "__main__":
    main()
