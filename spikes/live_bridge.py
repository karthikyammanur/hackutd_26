"""L4-5 live bridge: a real Scammer Simulator call -> Safe Signal API, as it happens.

    python spikes/live_bridge.py --yes [--to +1...] [--api http://localhost:8000]

Places one call from the Scammer Simulator agent (ElevenLabs, SIP trunk) to the customer, then polls the
conversation and POSTs call_start, each transcript line as a `turn`, and call_end to /sessions/{id}/events.
The bank code (sms_otp) comes from the customer's phone (call-screener app -> POST /live/sms), not from here.

R8: transcript text is only held in memory and sent to the API. It is never printed or written to disk.
R10: only call teammates' own numbers. Refuses to dial without --yes.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

import httpx
from dotenv import load_dotenv

EL = "https://api.elevenlabs.io/v1/convai"
DONE = ("done", "failed")
SETTLE_POLLS = 2  # the newest line can still be growing; send it once it is unchanged this many polls


def speaker(role: str) -> str:
    """ElevenLabs 'agent' is the Scammer Simulator (the caller); 'user' is the customer."""
    return "caller" if role == "agent" else "customer"


class Transcript:
    """Turns ElevenLabs transcript snapshots into new, final turns, each sent once."""

    def __init__(self) -> None:
        self.sent = 0  # entries already sent
        self.last_text = ""
        self.stable = 0

    def new_turns(self, entries: list[dict[str, Any]], final: bool) -> list[tuple[float, str, str]]:
        entries = [
            e for e in entries if (e.get("message") or "").strip() and e.get("role") in ("agent", "user")
        ]
        ready = len(entries) if final else max(len(entries) - 1, self.sent)
        if not final and len(entries) > self.sent:
            newest = entries[-1]["message"]
            self.stable = self.stable + 1 if newest == self.last_text else 0
            self.last_text = newest
            if self.stable >= SETTLE_POLLS:
                ready = len(entries)
        out = [
            (float(e.get("time_in_call_secs") or 0), speaker(e["role"]), e["message"].strip())
            for e in entries[self.sent : ready]
        ]
        self.sent = max(self.sent, ready)
        return out


def caller_number(client: httpx.Client, phone_number_id: str) -> str:
    r = client.get(f"{EL}/phone-numbers/{phone_number_id}")
    r.raise_for_status()
    return r.json().get("phone_number") or "unknown"


def post(api: httpx.Client, sid: str, event: dict[str, Any]) -> None:
    r = api.post(f"/sessions/{sid}/events", json={"session_id": sid, **event})
    if r.status_code >= 300:
        print(f"  API {r.status_code} on {event['kind']}: {r.text[:200]}")


def main() -> int:
    load_dotenv(".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="actually place the call")
    ap.add_argument("--to", default=os.environ.get("DEMO_CUSTOMER_NUMBER", "").strip())
    ap.add_argument("--api", default=os.environ.get("API_URL", "http://localhost:8000").strip())
    ap.add_argument("--session-id", default=f"live-{int(time.time())}")
    ap.add_argument("--poll", type=float, default=1.0, help="seconds between transcript polls")
    args = ap.parse_args()

    need = ["ELEVENLABS_API_KEY", "SCAMMER_AGENT_ID", "ELEVENLABS_PHONE_NUMBER_ID"]
    missing = [v for v in need if not os.environ.get(v, "").strip()]
    if missing or not args.to:
        print("Missing:", ", ".join(missing + ([] if args.to else ["--to / DEMO_CUSTOMER_NUMBER"])))
        return 1
    if not args.yes:
        print(f"Dry run. Would call ...{args.to[-4:]} as the Scammer Simulator. Re-run with --yes.")
        return 0

    el = httpx.Client(headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}, timeout=20)
    api = httpx.Client(base_url=args.api, timeout=10)
    sid = args.session_id
    api.get("/health").raise_for_status()  # fail before dialing if the API is down

    number = caller_number(el, os.environ["ELEVENLABS_PHONE_NUMBER_ID"])
    r = el.post(
        f"{EL}/sip-trunk/outbound-call",
        json={
            "agent_id": os.environ["SCAMMER_AGENT_ID"],
            "agent_phone_number_id": os.environ["ELEVENLABS_PHONE_NUMBER_ID"],
            "to_number": args.to,
        },
    )
    r.raise_for_status()
    conv = r.json().get("conversation_id")
    if not conv:
        print("ElevenLabs placed the call but returned no conversation_id:", r.text[:300])
        return 1
    placed = time.monotonic()
    print(f"session {sid}  conversation {conv}  calling ...{args.to[-4:]}", flush=True)
    print(f"console: ws {args.api.replace('http', 'ws')}/ws/{sid}")

    post(api, sid, {
        "kind": "call_start", "t": 0, "source": "network", "direction": "inbound",
        "number": number, "first_seen": True,
    })  # fmt: skip

    tx = Transcript()
    last_t = 0.0
    status = ""
    d: dict[str, Any] = {}
    try:
        while True:
            d = el.get(f"{EL}/conversations/{conv}").json()
            status = d.get("status", "")
            final = status in DONE
            for t, who, text in tx.new_turns(d.get("transcript") or [], final):
                last_t = max(last_t, t)
                post(api, sid, {"kind": "turn", "t": t, "source": "network", "speaker": who, "text": text})
                wall = time.monotonic() - placed  # includes ringing, so wall - t is lag plus ring time
                print(
                    f"  t={t:>5.0f}  wall={wall:>5.0f}  {who:<8} turn sent ({len(text)} chars)", flush=True
                )  # R8
            if final:
                break
            time.sleep(args.poll)
    except KeyboardInterrupt:
        print("stopped by hand")
    finally:
        end_t = max(last_t + 1, float((d.get("metadata") or {}).get("call_duration_secs") or 0))
        post(api, sid, {"kind": "call_end", "t": end_t, "source": "network"})
        print(f"call {status or 'stopped'}; call_end sent at t={end_t:.0f}. After-call plan runs in the API.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
