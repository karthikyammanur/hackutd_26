"""L4-1 ElevenLabs spike: place ONE outbound call from the Scammer Simulator agent to a teammate's phone.

Same request as the teammate's el-call.ts (POST /convai/sip-trunk/outbound-call), but every ID comes from env.
Real call. Refuses to run without --yes. Only call teammates' own numbers (R10).
Run: python spikes/elevenlabs_call.py --yes [--to +1...]   (default --to is DEMO_CUSTOMER_NUMBER)
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx
from dotenv import load_dotenv

URL = "https://api.elevenlabs.io/v1/convai/sip-trunk/outbound-call"


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="actually place the call")
    ap.add_argument("--to", default=os.environ.get("DEMO_CUSTOMER_NUMBER", "").strip())
    ap.add_argument("--agent-var", default="SCAMMER_AGENT_ID")
    args = ap.parse_args()

    need = ["ELEVENLABS_API_KEY", args.agent_var, "ELEVENLABS_PHONE_NUMBER_ID"]
    missing = [v for v in need if not os.environ.get(v, "").strip()]
    if missing or not args.to:
        print("Missing:", ", ".join(missing + ([] if args.to else ["--to / DEMO_CUSTOMER_NUMBER"])))
        return 1
    if not args.yes:
        print(f"Dry run. Would call ...{args.to[-4:]} with {args.agent_var}. Re-run with --yes.")
        return 0

    r = httpx.post(
        URL,
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
        json={
            "agent_id": os.environ[args.agent_var],
            "agent_phone_number_id": os.environ["ELEVENLABS_PHONE_NUMBER_ID"],
            "to_number": args.to,
        },
        timeout=30,
    )
    print("status", r.status_code)
    print(r.text[:1000])
    return 0 if r.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
