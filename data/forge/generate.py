"""Synthetic training-session generator. Writes contracts.events.EvalCase rows to data/train/shard_NN.jsonl.

Two writers, same structure (who dialed, attestation, when codes arrive, labels):
  --writer template   offline and seeded, so it's reproducible. The default.
  --writer nemotron   rewrites every spoken line through services.agents.llm (R13), with template lines as the
                      fallback when a reply is invalid (R11). Needs Lane 1's llm.py and a live endpoint.

Training data only. The eval set is written separately, session by session, in data/eval/source/ (F12).
All numbers are in the reserved fictional 555-01xx range, and all organizations are invented (R10).

  python data/forge/generate.py --n 640 --seed 7 --out data/train
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from contracts.events import EvalCase  # noqa: E402

SHARD_SIZE = 250  # keeps each file under the repo's 800 KB pre-commit limit

BANKS = (
    "Cedar Creek Bank",
    "Hill Country Credit Union",
    "Gulf Coast Federal",
    "Panhandle Savings",
    "Lone Star Bank",
)
CARRIER = ("T-Mobile",)
CLINICS = ("Willow Park Clinic", "Eastside Family Medicine", "Harbor Dental", "Sunrise Pediatrics")
EMPLOYERS = ("Brightline Staffing", "Meridian Careers", "Ironwood Group")
AREA_CODES = (
    "214",
    "469",
    "972",
    "817",
    "682",
    "512",
    "737",
    "713",
    "281",
    "832",
    "210",
    "903",
    "940",
    "915",
)
TOLL_FREE = ("800", "888", "877", "866", "855")
FIRST_NAMES = ("Alex", "Sam", "Nina", "Omar", "Leah", "Victor", "Grace", "Paul", "Irene", "Caleb")
AMOUNTS = ("640", "1,150", "2,480", "3,900", "875", "5,200")
SENDERS = {"bank": "bank_shortcode", "other": "other_shortcode", "long": "longcode"}


@dataclass(frozen=True)
class Beat:
    alternatives: tuple[str, ...]
    p: float = 1.0


def b(*alternatives: str, p: float = 1.0) -> Beat:
    return Beat(alternatives, p)


@dataclass(frozen=True)
class Family:
    type: str
    cls: str  # scam, hard or easy
    share: float
    beats: tuple[Beat, ...]
    direction: str = "inbound"
    verified: bool = False
    attestation: tuple[str, ...] = ("B", "C", "none")
    first_seen: float = 1.0
    orgs: tuple[str, ...] = BANKS


SCAMS = (
    Family(
        "bank_safe_account",
        "scam",
        0.13,
        (
            b(
                "C:This is {name} from the {org} fraud team, is this the account holder?",
                "C:Hello, {org} security here, we blocked a suspicious payment on your card.",
                "C:I'm {name}, a fraud specialist with {org}. We need to talk about your checking account.",
            ),
            b("U:Yes, what's wrong?", "U:Oh no, is my money okay?", "U:Who is this again?"),
            b(
                "C:A transfer of {amount} dollars is pending and we need to stop it now.",
                "C:Someone in another state just tried to take {amount} dollars from you.",
            ),
            b(
                "C:Please stay on the line and don't tell anyone at your branch.",
                "C:Keep this confidential, this is an internal investigation.",
                p=0.6,
            ),
            b("@OTP bank", p=0.8),
            b("@APP", p=0.3),
            b(
                "!C:Read me the code we just texted so I can cancel the transfer.",
                "!C:Tell me the six digit passcode you received, I have to verify you.",
                "!C:Move your balance to this safe account until we finish the investigation.",
                "!C:Send your savings to our protected account right now, I'll give you the details.",
                "!C:What is the verification code on your screen? I need it to stop the payment.",
            ),
            b(
                "C:Hurry please, we only have a few minutes.",
                "C:If you hang up now the money is gone.",
                p=0.5,
            ),
        ),
    ),
    Family(
        "fake_support_outbound",
        "scam",
        0.07,
        (
            b(
                "C:Support desk for {org}, this is {name}.",
                "C:Thanks for calling {org} customer care, how can I help?",
            ),
            b(
                "U:I found this number online, I need a refund.",
                "U:I was overcharged and want my money back.",
            ),
            b(
                "C:I see the charge. Our refund system is offline at the moment.",
                "C:Okay, that refund needs a release.",
            ),
            b(
                "!C:We issue refunds through gift cards now, buy one and read me the number on the back.",
                "!C:Pick up a prepaid card for {amount} and give me the code so I can apply your refund.",
                "!C:Install AnyDesk so I can reach your screen and process the refund.",
            ),
            b(
                "C:It's the only way, the system is down all week.",
                "C:We do this for all customers now.",
                p=0.5,
            ),
        ),
        direction="outbound",
        attestation=("C", "none", "B"),
        orgs=CARRIER + BANKS,
    ),
    Family(
        "tech_support_remote",
        "scam",
        0.07,
        (
            b(
                "C:This is computer security support, your PC is infected.",
                "C:We detected a virus on your laptop.",
            ),
            b("U:How do you know that?", "U:What should I do?"),
            b("C:Your files are being stolen as we speak.", "C:Hackers are inside your network right now."),
            b(
                "!C:Download TeamViewer so I can get control of your computer.",
                "!C:Go to our site and install the remote access tool, then give me the session code.",
                "!C:I need remote access to your PC to clean it.",
            ),
            b(
                "C:Please don't hang up or you'll lose everything.",
                "C:It costs {amount} for the cleanup.",
                p=0.6,
            ),
            b("@APP", p=0.2),
        ),
    ),
    Family(
        "gov_impersonation",
        "scam",
        0.06,
        (
            b(
                "C:This is Agent {name} with the tax authority.",
                "C:I'm calling from the county sheriff's office.",
            ),
            b("U:What is this about?", "U:Am I in trouble?"),
            b(
                "C:There is a warrant for your arrest over unpaid fines.",
                "C:You face arrest today for a missed summons.",
            ),
            b(
                "!C:Pay {amount} in gift cards today to clear the warrant.",
                "!C:You must settle this with prepaid cards and read me the numbers.",
                "!C:Move your funds to the government secure account I'll give you.",
            ),
            b(
                "C:Stay on the line and do not tell anyone.",
                "C:Don't call a lawyer, it makes this worse.",
                p=0.7,
            ),
        ),
    ),
    Family(
        "carrier_sim_swap",
        "scam",
        0.07,
        (
            b(
                "C:T-Mobile security calling, your line is at risk.",
                "C:Hi, T-Mobile retention, you've won an upgrade.",
            ),
            b("U:Okay, what do you need?", "U:Is something wrong?"),
            b("C:I'm sending a code to your phone.", "C:You will get a message from us in a moment."),
            b("@OTP other", "@OTP bank", "@OTP long"),
            b(
                "!C:Read me that code so I can secure your SIM.",
                "!C:Tell me the PIN you just got and we'll finish the upgrade.",
                "!C:What's the code you received? I'll enter it on my side.",
            ),
            b(
                "@ACC sim_change attempted",
                "@ACC port_out attempted",
                "@ACC call_forwarding_on attempted",
                p=0.85,
            ),
        ),
        orgs=CARRIER,
    ),
    Family(
        "family_emergency_scam",
        "scam",
        0.04,
        (
            b("C:Grandpa, it's me, I got in an accident.", "C:Mom, I'm in trouble and my phone is broken."),
            b("U:What happened? Are you hurt?", "U:Oh no, where are you?"),
            b("C:I'm at the police station and I need help.", "C:They're holding me until I pay."),
            b(
                "!C:I need {amount} in gift cards right now for bail.",
                "!C:Please send {amount} by wire, a lawyer will pick it up, buy prepaid cards if you can't.",
            ),
            b("C:Don't tell Mom or Dad, please.", "C:Please keep this between us.", p=0.8),
        ),
    ),
    Family(
        "utility_shutoff",
        "scam",
        0.03,
        (
            b(
                "C:This is the electric company, your power gets shut off today.",
                "C:City utilities here, shutoff is scheduled.",
            ),
            b("U:But I paid my bill.", "U:Why is that?"),
            b(
                "!C:Pay {amount} with a prepaid card right now to stop the crew.",
                "!C:Buy a gift card and read me the numbers to stop the disconnect.",
            ),
            b("C:Stay on the line while you go to the store.", p=0.7),
        ),
    ),
    Family(
        "refund_overpayment",
        "scam",
        0.03,
        (
            b("C:We owe you a refund for your subscription.", "C:You're due money back on a warranty."),
            b("U:Oh, okay.", "U:How much?"),
            b("C:Log in to your bank and I'll send it over.", "C:I'll deposit it while we talk."),
            b("@APP"),
            b(
                "!C:I sent too much by mistake, send back {amount} in gift cards.",
                "!C:Install this remote access app so I can fix the extra deposit.",
                "!C:You have to send the extra {amount} to our holding account.",
            ),
        ),
    ),
    Family(
        "signal_only_quiet",
        "scam",
        0.02,
        (
            b("C:Hi, one moment please, I'm checking your file.", "C:Hello, I'm calling about your account."),
            b("U:Okay.", "U:Sure."),
            b("!@OTP bank"),
            b("@ACC sim_change attempted", "@ACC call_forwarding_on attempted", "@APP"),
            b("C:Thanks, that's all I needed.", "C:All done, have a nice day."),
        ),
    ),
)

HARD_NEGATIVES = (
    Family(
        "benign_bank_callback",
        "hard",
        0.08,
        (
            b(
                "C:Thank you for calling {org}, how can I help?",
                "C:{org}, this is {name}. What can I do for you?",
            ),
            b(
                "U:My card was declined and I want to know why.",
                "U:I need to reset my online banking password.",
            ),
            b(
                "C:I'll send a code, enter it in your app, please don't read it to me.",
                "C:You'll get a code by text.",
            ),
            b("@OTP bank"),
            b("@APP", p=0.6),
            b(
                "C:Thanks, you're verified and all set.",
                "C:That's done, I can transfer you if you need anything else.",
            ),
        ),
        direction="outbound",
        verified=True,
        attestation=("A",),
        first_seen=0.1,
    ),
    Family(
        "benign_carrier_care",
        "hard",
        0.06,
        (
            b("C:T-Mobile, this is {name}, how can I help?", "C:Thanks for calling T-Mobile."),
            b("U:I got a new phone and need to move my SIM.", "U:I'm leaving and need my port out PIN."),
            b("C:You'll get a code, type it into T-Life.", "C:I'll text you a PIN, keep that private."),
            b("@OTP other"),
            b("@ACC sim_change attempted", "@ACC port_out attempted", p=0.7),
            b("C:All set, anything else?", "C:You're good to go."),
        ),
        direction="outbound",
        verified=True,
        attestation=("A",),
        first_seen=0.1,
        orgs=CARRIER,
    ),
    Family(
        "benign_bank_inbound",
        "hard",
        0.03,
        (
            b(
                "C:This is {org} checking on a charge you made today.",
                "C:Hi, {org} calling about your new card.",
            ),
            b("U:Yes, that was me.", "U:Okay, thanks."),
            b("C:Great, we will never ask for your code or PIN by phone.", "C:Thanks, no action is needed."),
            b("@OTP bank", p=0.3),
        ),
        verified=True,
        attestation=("A",),
        first_seen=0.3,
    ),
    Family(
        "benign_doctor_office",
        "hard",
        0.06,
        (
            b(
                "C:Hi, it's {name} at {org}, calling about your appointment.",
                "C:This is the billing office at {org}.",
            ),
            b("U:Oh yes, thanks for calling.", "U:Is everything okay?"),
            b(
                "C:The insurance needs a new billing code, so I'll transfer you to billing.",
                "C:Please hold, don't hang up, I'm getting the nurse.",
                "C:We need your zip code to look up the claim.",
            ),
            b("@OTP other", p=0.3),
            b(
                "C:You can pay the balance on the portal when you get a chance.",
                "C:We'll see you on Tuesday.",
            ),
        ),
        attestation=("A", "B", "C"),
        orgs=CLINICS,
    ),
    Family(
        "benign_recruiter",
        "hard",
        0.04,
        (
            b("C:Hi, it's {name} from {org} about your application.", "C:This is {org}, I saw your resume."),
            b("U:Hi, thanks.", "U:Yes, I'm interested."),
            b(
                "C:We'll send an assessment link with a login code.",
                "C:I'll transfer you to the hiring manager, hold on.",
            ),
            b("@OTP other", p=0.3),
            b("C:Please don't share your bank details by phone, HR will send a secure form.", "C:Talk soon."),
        ),
        attestation=("A", "B"),
        orgs=EMPLOYERS,
    ),
    Family(
        "benign_family_emergency",
        "hard",
        0.03,
        (
            b(
                "C:It's the nurse at Mercy Hospital, your father fell.",
                "C:Dad, it's me on a friend's phone, I lost mine.",
            ),
            b("U:Oh no, is everything alright?", "U:What happened?"),
            b("C:It's urgent, you should come soon.", "C:Can you pick me up, don't tell Mom yet."),
            b("C:I'll text you the address.", "C:Bring the insurance card."),
        ),
        attestation=("A", "B"),
    ),
    Family(
        "benign_otp_coincidence",
        "hard",
        0.04,
        (
            b(
                "C:Hey, it's the contractor, running late today.",
                "C:Hi, I'm calling about the sofa you listed.",
            ),
            b(
                "U:No problem, I'm paying a bill online right now.",
                "U:Sure, just signing in to my bank, one sec.",
            ),
            b("@APP", p=0.6),
            b("@OTP bank"),
            b("C:No rush, I'll see you then.", "C:Sounds good, thanks."),
        ),
        attestation=("A", "B"),
    ),
    Family(
        "benign_it_helpdesk",
        "hard",
        0.02,
        (
            b("C:IT help desk, I'm following up on your ticket.", "C:Hi, this is your company's IT team."),
            b("U:Yes, my laptop is acting up.", "U:Thanks for calling back."),
            b("C:I'm going to connect to your laptop now.", "C:You'll get a prompt, go ahead and accept it."),
            b("C:Okay, it's fixed.", "C:Closing the ticket now."),
        ),
        attestation=("A", "B"),
    ),
)

EASY_NEGATIVES = (
    Family(
        "benign_personal",
        "easy",
        0.06,
        (
            b(
                "C:Hey, are you free this weekend?",
                "C:Hi, just checking on you.",
                "C:Did you see the game last night?",
            ),
            b("U:Yeah, sounds good.", "U:I'm doing fine, thanks."),
            b("C:Great, talk soon.", "C:Okay, bye."),
        ),
        attestation=("A", "B"),
        first_seen=0.1,
    ),
    Family(
        "benign_service",
        "easy",
        0.06,
        (
            b(
                "C:Thanks for calling the garden center.",
                "C:Hi, your order is ready for pickup.",
                "C:Reminder from the salon.",
            ),
            b("U:What time do you close?", "U:Thanks, I'll come by."),
            b("C:We're open until six.", "C:See you soon."),
        ),
        attestation=("A", "B"),
    ),
)

FAMILIES = SCAMS + HARD_NEGATIVES + EASY_NEGATIVES


def phone_number(rng: random.Random, toll_free: bool) -> str:
    area = rng.choice(TOLL_FREE if toll_free else AREA_CODES)
    return f"+1{area}55501{rng.randint(0, 99):02d}"


def build_events(
    sid: str, rng: random.Random, family: Family, slots: dict[str, str]
) -> tuple[list[dict], float | None]:
    events: list[dict] = []
    base = {"session_id": sid}
    t = 0.0
    ask: float | None = None
    for beat in family.beats:
        if rng.random() > beat.p:
            continue
        t += rng.randint(5, 24)
        line = rng.choice(beat.alternatives)
        is_ask = line.startswith("!")
        line = line.removeprefix("!")
        if is_ask and ask is None:
            ask = t
        row: dict = {**base, "t": t, "source": "network"}
        if line.startswith("@OTP"):
            row |= {"kind": "sms_otp", "sender_type": SENDERS[line.split()[1]], "org": slots["org"]}
        elif line == "@APP":
            row |= {"kind": "bank_app_traffic", "org": slots["org"]}
        elif line.startswith("@ACC"):
            _, action, status = line.split()
            row |= {"kind": "account_change", "action": action, "status": status}
        else:
            speaker = "caller" if line[0] == "C" else "customer"
            row |= {"kind": "turn", "speaker": speaker, "text": line[2:].format(**slots)}
        events.append(row)
    t += rng.randint(5, 20)
    events.append({**base, "t": t, "source": "network", "kind": "call_end"})
    return events, ask


def build_session(index: int, rng: random.Random, family: Family) -> dict:
    sid = f"tr_{index:04d}_{family.type}"
    org = rng.choice(family.orgs)
    slots = {"org": org, "name": rng.choice(FIRST_NAMES), "amount": rng.choice(AMOUNTS)}
    start = {
        "session_id": sid,
        "t": 0,
        "source": "network",
        "kind": "call_start",
        "direction": family.direction,
        "number": phone_number(rng, toll_free=family.verified or family.direction == "outbound"),
        "carrier_label": "none",
        "attestation": rng.choice(family.attestation),
        "first_seen": rng.random() < family.first_seen,
        "verified_org": org if family.verified else None,
    }
    events, ask = build_events(sid, rng, family, slots)
    if family.cls == "scam" and ask is None:  # the ask beat is mandatory; this guards the template data
        raise ValueError(f"{family.type}: scam session without an ask")
    return {
        "session_id": sid,
        "label": {
            "scam": family.cls == "scam",
            "type": family.type,
            "hard_negative": family.cls == "hard",
            "first_scam_t": ask,
        },
        "events": [start, *events],
    }


def generate(n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    total = sum(f.share for f in FAMILIES)
    sessions: list[dict] = []
    for family in FAMILIES:
        for _ in range(max(1, round(n * family.share / total))):
            sessions.append(build_session(len(sessions), rng, family))
    rng.shuffle(sessions)
    return sessions


def rewrite_with_nemotron(sessions: list[dict]) -> int:
    """Rewrite spoken lines through Lane 1's client. Keeps the template line on any invalid reply (R11)."""
    from data.forge.nemotron_writer import rewrite_session

    return sum(rewrite_session(s) for s in sessions)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=640)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "train")
    ap.add_argument("--writer", choices=["template", "nemotron"], default="template")
    args = ap.parse_args()

    sessions = generate(args.n, args.seed)
    rewritten = rewrite_with_nemotron(sessions) if args.writer == "nemotron" else 0
    validated = [EvalCase.model_validate(s).model_dump(mode="json") for s in sessions]

    args.out.mkdir(parents=True, exist_ok=True)
    for old in args.out.glob("shard_*.jsonl"):
        old.unlink()
    for i in range(0, len(validated), SHARD_SIZE):
        lines = [json.dumps(s, separators=(",", ":")) for s in validated[i : i + SHARD_SIZE]]
        (args.out / f"shard_{i // SHARD_SIZE:02d}.jsonl").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    hard = sum(s["label"]["hard_negative"] for s in validated)
    scams = sum(s["label"]["scam"] for s in validated)
    print(
        f"{len(validated)} sessions ({args.writer}, {rewritten} rewritten): "
        f"{scams} scam, {len(validated) - scams} benign, {hard} hard negatives ({100 * hard / len(validated):.0f}%)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
