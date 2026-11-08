from __future__ import annotations

from contracts.interfaces import Account, Comms, Store, Voice
from services.agents.graph import stubs
from services.agents.tools.mock import MockAccount, MockComms, MockStore, MockVoice, mock_tools


def test_mocks_are_lane1_fakes() -> None:
    assert MockComms is stubs.FakeComms and MockStore is stubs.FakeStore
    t = mock_tools()
    comms: Comms = t.comms
    voice: Voice = MockVoice()
    store: Store = MockStore()
    account: Account = MockAccount()
    assert comms and voice and store and account


def test_mock_store_drops_turns() -> None:
    s = MockStore()
    s.append_event("s1", {"kind": "turn", "text": "read me the code"})
    s.append_event("s1", {"kind": "sms_otp"})
    assert s.events == [{"kind": "sms_otp"}]
