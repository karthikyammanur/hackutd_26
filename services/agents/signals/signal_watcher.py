"""Signal Watcher: Trigger A (bank code or bank-app traffic mid-call) plus account changes.

Trigger A only fires for unknown or unverified callers. `caller.verified_org` is what Caller Screen chose
to believe, so a spoofed verified number has already been cleared by the time it gets here.
"""

from __future__ import annotations

from contracts.events import AccountChange, BankAppTraffic, SmsOtp
from contracts.state import CallerInfo, Signal
from services.agents.decision import config
from services.agents.decision.decide import has_verified_org


def watch_event(event: object, caller: CallerInfo) -> list[Signal]:
    """Signals for one event during a call. Turns and anything else produce nothing here."""
    if isinstance(event, AccountChange):
        if event.status == "held":  # our own hold, not evidence about the caller
            return []
        weight = config.ACCOUNT_CHANGE_WEIGHT[event.action]
        return [
            Signal(
                kind="account_change_during_call",
                t=event.t,
                weight=weight,
                detail=f"{event.action} {event.status}",
            )
        ]
    if has_verified_org(caller):
        return []
    if isinstance(event, SmsOtp):
        weight = config.OTP_WEIGHT[event.sender_type]
        return [
            Signal(
                kind="otp_during_call",
                t=event.t,
                weight=weight,
                detail=f"{event.sender_type} {event.org or ''}".strip(),
            )
        ]
    if isinstance(event, BankAppTraffic):
        return [
            Signal(
                kind="bank_app_during_call", t=event.t, weight=config.WEIGHT_BANK_APP, detail=event.org or ""
            )
        ]
    return []
