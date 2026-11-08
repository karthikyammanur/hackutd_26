"""The tools the graph gets injected. Swap fakes for real adapters by building a different Tools."""

from __future__ import annotations

from dataclasses import dataclass

from contracts.interfaces import Comms, Decider, Store, Voice


@dataclass(frozen=True)
class Tools:
    decider: Decider
    comms: Comms
    voice: Voice
    store: Store
