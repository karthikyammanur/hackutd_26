"""Optional Jev decision layer behind JEV_URL, with the rules as baseline and fallback.

Jev's API is an open question (context/decisions.md), so this assumes the simplest contract: POST a JSON
summary of the state, get back a JSON object that validates as contracts.state.Risk.

Whatever Jev says, it can only raise risk above the rules, and it can't override R1, R4 or R7.
Any error, timeout or invalid reply means the rule result is returned.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request

from contracts.state import Risk, SessionState, merge_risk
from services.agents.decision import config
from services.agents.decision.decide import decide, is_emergency, trusted_cap_applies

log = logging.getLogger(__name__)


def _payload(state: SessionState) -> dict:
    """Only what a decision needs: no flag quotes and no phone number (R9)."""
    caller = state.caller
    return {
        "session_id": state.session_id,
        "caller": caller.model_dump(mode="json", exclude={"number"}) if caller else None,
        "prior_risk": state.prior_risk.model_dump(mode="json") if state.prior_risk else None,
        "signals": [s.model_dump(mode="json") for s in state.signals],
        "flags": [{"kind": f.kind, "t": f.t, "confidence": f.confidence} for f in state.flags],
    }


def _call_jev(url: str, state: SessionState) -> Risk:
    headers = {"Content-Type": "application/json"}
    if key := os.environ.get("JEV_API_KEY", ""):
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(
        url, data=json.dumps(_payload(state)).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(request, timeout=config.JEV_TIMEOUT_S) as response:
        return Risk.model_validate(json.loads(response.read()))


def decide_with_jev(state: SessionState) -> Risk:
    """Same signature as decide(). With JEV_URL unset this is exactly the rule decision."""
    baseline = decide(state)
    url = os.environ.get("JEV_URL", "").strip()
    if not url or state.guard_paused or state.caller is None or is_emergency(state.caller.number):
        return baseline
    if trusted_cap_applies(state):  # R7 is not negotiable
        return baseline
    try:
        return merge_risk(baseline, _call_jev(url, state))
    except Exception as exc:  # any failure: the rules already gave a safe answer
        log.warning("Jev unavailable for session %s (%s); using rules", state.session_id, type(exc).__name__)
        return baseline
