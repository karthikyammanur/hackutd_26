"""The console's view of a live call (view.py): markers only, and the fixture the web tests read stays current.

python services/api/tests/test_view.py     # rewrites apps/web/tests/fixtures/live-views.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from contracts.events import CallEnd, Event  # noqa: E402
from services.agents.graph.runner import Session  # noqa: E402
from services.agents.graph.stubs import fake_tools, offline_structured  # noqa: E402
from services.agents.nodes.during import keyword_guardian  # noqa: E402
from services.agents.tests.test_card_scenario import GAVE_CARD, OPENING, SID, START  # noqa: E402
from services.api.view import session_view  # noqa: E402

FIXTURE = ROOT / "apps" / "web" / "tests" / "fixtures" / "live-views.json"


def _view(events: list[Event], answered: float | None) -> dict[str, Any]:
    s = Session(SID, fake_tools(), guardian=keyword_guardian, structured=offline_structured)
    for e in events:
        s.feed(e)
    return session_view(s.state(), t=events[-1].t, answered_t=answered, call_running=False)


def card_views() -> dict[str, dict[str, Any]]:
    """S1 declined, S2 hung up after the card ask, S3 read the card out (test_card_scenario.py)."""
    end = lambda t: CallEnd(session_id=SID, t=t, source=START.source)  # noqa: E731
    return {
        "s1": _view([START, end(0)], None),
        "s2": _view([START, *OPENING, end(45)], 2),
        "s3": _view([START, *OPENING, *GAVE_CARD, end(75)], 2),
    }


def test_view_is_markers_only() -> None:
    views = card_views()
    raw = json.dumps(views)
    for line in [*OPENING, *GAVE_CARD]:
        assert line.text[:30] not in raw
    assert START.number not in raw and "4 2 4 2" not in raw
    s1, s2, s3 = views["s1"], views["s2"], views["s3"]
    assert s1["erased"] and s1["plan"] == [] and s1["answered_t"] is None
    assert s2["disclosed"] is False and "callback" not in [p["name"] for p in s2["plan"]]
    assert s3["disclosed"] is True and {"name": "callback", "status": "done"} in s3["plan"]
    assert all(v["erased"] for v in views.values())


def test_console_fixture_matches_the_api() -> None:
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == card_views(), (
        "the API's view changed: run python services/api/tests/test_view.py, then the web tests"
    )


if __name__ == "__main__":
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(card_views(), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE.relative_to(ROOT)}")
