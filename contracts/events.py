"""Call events: the only input format every lane agrees on.

`turn` events carry transcript text. They live in memory only and are never persisted (rules R8).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Source(StrEnum):
    network = "network"  # seen by the carrier (calls, short-code texts, DNS, account events)
    phone = "phone"  # seen on the handset (T-Life component)
    system = "system"  # produced by Safe Signal itself


class Direction(StrEnum):
    inbound = "inbound"
    outbound = "outbound"  # the customer dialed


class _Event(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    t: float = Field(ge=0, description="seconds since call start")
    source: Source


class CallStart(_Event):
    kind: Literal["call_start"] = "call_start"
    direction: Direction
    number: str
    carrier_label: Literal["none", "scam_likely", "spam"] = "none"
    attestation: Literal["A", "B", "C", "none"] = "none"
    first_seen: bool
    verified_org: str | None = None  # set when the number is on our verified list


class Turn(_Event):
    kind: Literal["turn"] = "turn"
    speaker: Literal["caller", "customer"]
    text: str


class SmsOtp(_Event):
    kind: Literal["sms_otp"] = "sms_otp"
    sender_type: Literal["bank_shortcode", "other_shortcode", "longcode"]
    org: str | None = None


class BankAppTraffic(_Event):
    kind: Literal["bank_app_traffic"] = "bank_app_traffic"
    org: str | None = None


class AccountChange(_Event):
    kind: Literal["account_change"] = "account_change"
    action: Literal["sim_change", "port_out", "call_forwarding_on"]
    status: Literal["attempted", "held", "completed"]


class UserChoice(_Event):
    kind: Literal["user_choice"] = "user_choice"
    choice: Literal["call_bank", "ask_trusted_contact", "continue", "dismiss"]


class CallEnd(_Event):
    kind: Literal["call_end"] = "call_end"


Event = Annotated[
    CallStart | Turn | SmsOtp | BankAppTraffic | AccountChange | UserChoice | CallEnd,
    Field(discriminator="kind"),
]

EMERGENCY_NUMBERS = frozenset({"911", "988", "112"})


class EvalLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scam: bool
    type: str  # e.g. bank_safe_account, fake_support_outbound, benign_bank_callback
    hard_negative: bool = False
    first_scam_t: float | None = None  # when the scam ask first happens; None for benign


class EvalCase(BaseModel):
    """One synthetic session: used for fixtures, replay, training and eval."""

    model_config = ConfigDict(extra="forbid")
    session_id: str
    label: EvalLabel
    events: list[Event]
