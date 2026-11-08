"""L4-1 read-only ElevenLabs check: both agents exist and which phone numbers the account owns.

Places no call and sends nothing. Phone numbers are masked in the output (R10).
Run: python spikes/elevenlabs_check.py
"""

from __future__ import annotations

import os
import sys

import httpx
from dotenv import load_dotenv

API = "https://api.elevenlabs.io/v1/convai"


def mask(number: str) -> str:
    return f"...{number[-4:]}" if number else "?"


def main() -> int:
    load_dotenv()
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        print("Set ELEVENLABS_API_KEY")
        return 1
    h = {"xi-api-key": key}
    ok = True
    for var in ("ELEVENLABS_AGENT_ID", "SCAMMER_AGENT_ID"):
        agent_id = os.environ.get(var, "").strip()
        if not agent_id:
            print(f"{var}: not set")
            ok = False
            continue
        r = httpx.get(f"{API}/agents/{agent_id}", headers=h, timeout=20)
        name = r.json().get("name") if r.status_code == 200 else r.text[:200]
        print(f"{var}: HTTP {r.status_code} name={name!r}")
        ok = ok and r.status_code == 200

    r = httpx.get(f"{API}/phone-numbers", headers=h, timeout=20)
    print(f"phone-numbers: HTTP {r.status_code}")
    if r.status_code != 200:
        print(r.text[:300])
        return 1
    data = r.json()
    items = data if isinstance(data, list) else data.get("phone_numbers", [])
    if not items:
        print("  (none: this account has no phone number, so outbound calls cannot be placed)")
        ok = False
    for p in items:
        agent = (p.get("assigned_agent") or {}).get("agent_id", "-")
        print(
            f"  id={p.get('phone_number_id')} provider={p.get('provider')} "
            f"label={p.get('label')!r} number={mask(p.get('phone_number', ''))} agent={agent}"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
