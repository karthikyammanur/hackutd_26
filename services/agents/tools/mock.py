"""Mocks of Lane 4's tools for every lane (L4-2).

These are Lane 1's fakes from graph/stubs.py under the names the lane brief promised, so there is one copy.
stubs.py already checks each one against contracts/interfaces.py with pyright.
"""

from __future__ import annotations

from services.agents.graph.stubs import FakeAccount as MockAccount
from services.agents.graph.stubs import FakeComms as MockComms
from services.agents.graph.stubs import FakeStore as MockStore
from services.agents.graph.stubs import FakeVoice as MockVoice
from services.agents.graph.stubs import fake_tools as mock_tools

__all__ = ["MockAccount", "MockComms", "MockStore", "MockVoice", "mock_tools"]
