"""L4-5 live bridge, from the command line: the same thing the console's "start call" button does.

    python spikes/live_bridge.py --yes [--api http://localhost:8000]

Asks the API to place one Scammer Simulator call to DEMO_CUSTOMER_NUMBER (POST /calls/start). The API follows
the call live (services/api/live_call.py) and runs the graph; watch it on WS /ws/{session_id}.
R10: the number always comes from the API's .env, never from here. Refuses to dial without --yes.
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx
from dotenv import load_dotenv


def main() -> int:
    load_dotenv(".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="actually place the call")
    ap.add_argument("--api", default=os.environ.get("API_URL", "http://localhost:8000").strip())
    args = ap.parse_args()
    if not args.yes:
        print("Dry run. Would ask the API to place one Scammer Simulator call. Re-run with --yes.")
        return 0
    r = httpx.post(f"{args.api}/calls/start", timeout=40)
    if r.status_code != 202:
        print(f"API {r.status_code}: {r.text[:300]}")
        return 1
    body = r.json()
    print(f"calling. session {body['session_id']}  conversation {body['conversation_id']}")
    print(
        f"watch: {args.api.replace('http', 'ws', 1)}{body['ws']}   state: {args.api}/sessions/{body['session_id']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
