"""L2-4: the training and eval sets are schema-valid, big enough, synthetic, and separate."""

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from contracts.events import EMERGENCY_NUMBERS, CallStart
from evals.replay import load_eval_cases
from services.agents.decision.decide import normalize_number
from services.agents.signals.caller_screen import load_scam_numbers

ROOT = Path(__file__).resolve().parents[4]
FICTIONAL = re.compile(r"^\+1\d{3}55501\d{2}$")


@pytest.fixture(scope="module")
def train():
    return load_eval_cases(ROOT / "data" / "train")


@pytest.fixture(scope="module")
def eval_set():
    return load_eval_cases(ROOT / "data" / "eval")


def hard_share(cases):
    return sum(c.label.hard_negative for c in cases) / len(cases)


def check_well_formed(case):
    assert isinstance(case.events[0], CallStart)
    assert case.events[-1].kind == "call_end"
    ts = [e.t for e in case.events]
    assert ts == sorted(ts), case.session_id
    assert (case.label.first_scam_t is not None) == case.label.scam, case.session_id
    assert not (case.label.scam and case.label.hard_negative), case.session_id


def number(case):
    first = case.events[0]
    assert isinstance(first, CallStart)
    return first.number


def test_train_size_and_mix(train):
    assert len(train) >= 500
    assert hard_share(train) >= 0.30


def test_eval_size_and_mix(eval_set):
    assert len(eval_set) >= 100
    assert hard_share(eval_set) >= 0.30


def test_all_sessions_well_formed(train, eval_set):
    for case in train + eval_set:
        check_well_formed(case)


def test_r10_only_fictional_numbers(train, eval_set):
    for case in train + eval_set:
        assert FICTIONAL.match(number(case)), case.session_id
        assert normalize_number(number(case)) not in EMERGENCY_NUMBERS


def test_eval_is_separate_from_train(train, eval_set):
    assert not {c.session_id for c in train} & {c.session_id for c in eval_set}
    spoken = {e.text for c in train for e in c.events if e.kind == "turn"}
    shared = {e.text for c in eval_set for e in c.events if e.kind == "turn"} & spoken
    # Short generic replies can coincide, but scripts must not be copied across.
    assert all(len(line) < 30 for line in shared), sorted(shared)[:5]


def test_scam_list_does_not_leak_into_eval(eval_set):
    listed = load_scam_numbers()
    assert listed and not {normalize_number(number(c)) for c in eval_set} & listed


# ---- Nemotron writer, against a stand-in for Lane 1's client ----


def session():
    return {
        "session_id": "x",
        "events": [
            {"kind": "call_start"},
            {"kind": "turn", "text": "one"},
            {"kind": "turn", "text": "two"},
            {"kind": "call_end"},
        ],
    }


def install_llm(monkeypatch, structured):
    monkeypatch.setitem(sys.modules, "services.agents.llm", SimpleNamespace(structured=structured))


def texts(s):
    return [e["text"] for e in s["events"] if e["kind"] == "turn"]


def test_writer_uses_a_valid_rewrite(monkeypatch):
    from data.forge.nemotron_writer import Rewrite, rewrite_session

    install_llm(monkeypatch, lambda _prompt, _model: Rewrite(lines=["uno", "dos"]))
    s = session()
    assert rewrite_session(s) and texts(s) == ["uno", "dos"]


def test_writer_keeps_template_on_wrong_line_count(monkeypatch):
    from data.forge.nemotron_writer import Rewrite, rewrite_session

    install_llm(monkeypatch, lambda _prompt, _model: Rewrite(lines=["only one"]))
    s = session()
    assert not rewrite_session(s) and texts(s) == ["one", "two"]


def test_writer_keeps_template_on_model_error(monkeypatch):
    from data.forge.nemotron_writer import rewrite_session

    def boom(_prompt, _model):
        raise TimeoutError

    install_llm(monkeypatch, boom)
    s = session()
    assert not rewrite_session(s) and texts(s) == ["one", "two"]
