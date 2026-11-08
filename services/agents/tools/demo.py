"""DemoStore and SimAccount: in-memory stand-ins used with the real comms until Tiger Data lands (L4-4).

Both build on Lane 1's fakes in graph/stubs.py, so the turn-dropping rule (R8) lives in one place.
Nothing is written to disk.
"""

from __future__ import annotations

import logging
import os

from services.agents.graph.stubs import VERIFIED_NUMBERS, FakeAccount, FakeStore
from services.agents.tools.errors import demo_number

log = logging.getLogger(__name__)

DEMO_BANK_ORG = "Lone Star Bank"  # the bank in evals/fixtures/hero1_fake_bank.json


class DemoStore(FakeStore):
    """FakeStore plus the demo bank: DEMO_BANK_NUMBER, when set, is Lone Star Bank's verified number."""

    def __init__(self, bank_number: str = "") -> None:
        super().__init__()
        self.verified = dict(VERIFIED_NUMBERS)
        if bank_number:
            self.verified = {n: o for n, o in self.verified.items() if o != DEMO_BANK_ORG}
            self.verified[bank_number] = DEMO_BANK_ORG
        self.org_numbers = {org: num for num, org in self.verified.items()}

    @classmethod
    def from_env(cls) -> DemoStore:
        return cls(bank_number=demo_number("DEMO_BANK_NUMBER", os.environ.get("DEMO_BANK_NUMBER", "")))

    def lookup_verified(self, number: str) -> str | None:
        return self.verified.get(number)

    def official_number(self, org: str) -> str | None:
        return self.org_numbers.get(org)


class SimAccount(FakeAccount):
    """Simulated account holds (the demo has no real T-Mobile account system)."""

    def hold_changes(self, session_id: str, actions: list[str], minutes: int) -> str:
        hold_id = super().hold_changes(session_id, actions, minutes).replace("fake-", "sim-")
        log.info(
            "simulated hold session=%s actions=%s minutes=%d id=%s", session_id, actions, minutes, hold_id
        )
        return hold_id
