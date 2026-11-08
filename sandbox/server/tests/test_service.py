"""End-to-end tests against an in-process app with fake Jev and Nemotron. No network."""

import asyncio
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [
    str(ROOT),
    str(ROOT.parent / "worker" / "src"),
    str(ROOT.parent / "evidence" / "worker" / "src"),
    str(ROOT.parent / "evidence" / "backfill"),
]

import httpx  # noqa: E402
import load_corpus  # noqa: E402
import service as s  # noqa: E402
from pipeline import FLAGS  # noqa: E402

PASSWORD = "correct horse"
AUTH = {"authorization": f"Bearer {PASSWORD}"}
SECRET = "read me the secret marker code"


def case(case_id: str, scam: bool, channel: str = "call", weak: bool = False) -> dict:
    events = (
        [{"t": 0, "kind": "sms", "from_type": None, "text": SECRET, "domain": None, "domain_age_days": None}]
        if channel == "sms"
        else [{"t": i, "kind": "turn", "who": "caller", "text": f"{SECRET} {i}"} for i in range(8)]
    )
    return {
        "case_id": case_id,
        "channel": channel,
        "source": "generated",
        "label_quality": "weak" if weak else "exact",
        "scam": scam,
        "method": "bank_fraud_department" if scam else "legitimate",
        "family": "impersonation" if scam else "none",
        "hard_negative": False,
        "money_moment_t": None,
        "direction": "inbound",
        "events": events,
    }


class FakeTransport:
    def __init__(self):
        self.jev_error = None
        self.block: asyncio.Event | None = None
        self.jev_calls = 0
        self.max_jev = 0
        self.inflight = 0

    async def post_json(self, url, headers, payload, timeout):
        if "typesafe" in url:
            self.jev_calls += 1
            self.inflight += 1
            self.max_jev = max(self.max_jev, self.inflight)
            try:
                if self.block:
                    await self.block.wait()
                await asyncio.sleep(0)
                if self.jev_error:
                    raise s.HttpError(self.jev_error)
                danger = (
                    "0" not in payload["state"].split("MOST RECENT")[-1][:60] or "bank" in payload["state"]
                )
                tier = "dangerous" if SECRET in payload["state"] else "safe"
                answers = {
                    name: {"noul": 0.9 if name == "asks_for_code" and danger else 0.1} for name in FLAGS
                }
                answers["danger_tier"] = {
                    "choice": tier,
                    "probabilities": {"safe": 0.1, "uncertain": 0.3, "dangerous": 0.6},
                }
                answers["scam_method"] = {"choice": "bank_fraud_department"}
                return {"answers": answers, "usage": {}}
            finally:
                self.inflight -= 1
        assert url.startswith("http://localhost")
        system = payload["messages"][0]["content"]
        content = (
            '{"summary": "note"}'
            if "running note" in system
            else '{"marker": "m", "feedback": "f", "improvement": "i"}'
        )
        return {"choices": [{"message": {"content": content}}]}

    async def get_ok(self, url, key, timeout=6):
        return True

    async def close(self):
        pass


@pytest.fixture
def stack(tmp_path):
    data = tmp_path / "corpus"
    (data / "out").mkdir(parents=True)
    (data / "external").mkdir()
    cases = [case(f"c{i}", i % 2 == 0, "sms" if i % 3 == 0 else "call") for i in range(30)]
    cases.append(case("weak1", True, weak=True))
    (data / "out" / "a.jsonl").write_text("\n".join(json.dumps(c) for c in cases) + "\n")
    corpus = str(tmp_path / "corpus.db")
    sys.argv = ["x", str(data), corpus]
    load_corpus.main()
    settings = s.Settings(
        state_db=str(tmp_path / "state.db"),
        corpus_db=corpus,
        password_hash=hashlib.sha256(PASSWORD.encode()).hexdigest(),
        jev_key="k",
    )
    return settings


class Harness:
    def __init__(self, settings, transport):
        self.service = s.Service(settings, transport)
        self.app = s.build_app(self.service)

    async def __aenter__(self):
        await self.service.startup()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://t")
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()
        await self.service.shutdown()

    async def wait(self, run_id, statuses=("done", "failed", "cancelled")):
        for _ in range(2000):
            live = (await self.client.get(f"/runs/{run_id}/live", headers=AUTH)).json()
            if live["status"] in statuses:
                return live
            await asyncio.sleep(0.005)
        raise AssertionError("run did not finish")


def run(coro):
    return asyncio.run(coro)


def test_auth_and_health(stack):
    async def go():
        async with Harness(stack, FakeTransport()) as h:
            assert (await h.client.get("/healthz")).status_code == 200
            assert (await h.client.get("/runs")).status_code == 401
            assert (await h.client.get("/runs", headers={"authorization": "Bearer nope"})).status_code == 401
            assert (await h.client.get("/runs", headers=AUTH)).status_code == 200
            assert (await h.client.get("/nope", headers=AUTH)).status_code == 404

    run(go())


def test_corpus_counts_everything(stack):
    async def go():
        async with Harness(stack, FakeTransport()) as h:
            body = (await h.client.get("/corpus", headers=AUTH)).json()
            assert body["total"] == 31 and body["by_channel"]["sms"] == 10

    run(go())


def test_bad_input_rejected(stack):
    async def go():
        async with Harness(stack, FakeTransport()) as h:
            for body in ({"lanes": 129}, {"limit": 0}, {"models": ["gpt"]}):
                assert (await h.client.post("/runs", json=body, headers=AUTH)).status_code == 400
            assert (await h.client.post("/runs", content="not json", headers=AUTH)).status_code == 400

    run(go())


def test_full_run_rescore_matches_live_and_no_text_leaks(stack):
    async def go():
        async with Harness(stack, FakeTransport()) as h:
            started = (
                await h.client.post(
                    "/runs",
                    json={
                        "limit": 31,
                        "lanes": 8,
                        "models": ["jev-latest", "baseline-rules", "nemotron-fast"],
                    },
                    headers=AUTH,
                )
            ).json()
            live = await h.wait(started["id"])
            assert live["status"] == "done" and live["processed"] == 31
            assert live["brev"]["instances_reported"] == 1
            assert live["weak_labels"]["n"] == 3
            rescored = (await h.client.post(f"/runs/{started['id']}/rescore", json={}, headers=AUTH)).json()
            assert rescored["mode"] == "model_tier"
            for row in rescored["by_model"]:
                match = next(m for m in live["by_model"] if m["model"] == row["model"])
                assert row["score"] == match["score"] and row["caught"] == match["caught"]
            moved = (
                await h.client.post(
                    f"/runs/{started['id']}/rescore", json={"dangerous_threshold": 0.7}, headers=AUTH
                )
            ).json()
            assert moved["mode"] == "peak_probability_thresholds"
            assert (
                await h.client.post(
                    f"/runs/{started['id']}/rescore", json={"dangerous_threshold": 7}, headers=AUTH
                )
            ).status_code == 400

            results = (
                await h.client.get(f"/runs/{started['id']}/results?model=jev-latest&limit=10", headers=AUTH)
            ).json()
            assert len(results["items"]) == 10 and results["next"]
            assert set(results["items"][0]) == {
                "case_id",
                "model",
                "method",
                "family",
                "channel",
                "source",
                "weak",
                "predicted_method",
                "row",
            }
            responses = [
                await h.client.get(f"/runs/{started['id']}{p}", headers=AUTH)
                for p in ("", "/live", "/results", "/markers.json", "/markers.csv")
            ]
            assert all(SECRET not in r.text for r in responses)
            stored = (
                sqlite3.connect(stack.state_db)
                .execute("SELECT group_concat(row), group_concat(hard_flag) FROM results")
                .fetchone()[0]
            )
            assert SECRET not in stored
            assert (
                await h.client.get(f"/runs/{started['id']}/markers.json", headers=AUTH)
            ).status_code == 200

    run(go())


def test_second_run_conflicts_and_cancel_stops_it(stack):
    async def go():
        transport = FakeTransport()
        transport.block = asyncio.Event()
        async with Harness(stack, transport) as h:
            started = (await h.client.post("/runs", json={"limit": 20, "lanes": 2}, headers=AUTH)).json()
            assert (await h.client.post("/runs", json={"limit": 2}, headers=AUTH)).status_code == 409
            assert (await h.client.post(f"/runs/{started['id']}/cancel", headers=AUTH)).json() == {
                "cancelled": True
            }
            assert (await h.client.get(f"/runs/{started['id']}/live", headers=AUTH)).json()[
                "status"
            ] == "cancelled"

    run(go())


def test_sustained_server_errors_auto_pause_then_resume_finishes(stack, monkeypatch):
    async def fast_sleep(*_):
        await original(0)

    original = asyncio.sleep
    monkeypatch.setattr(s.asyncio, "sleep", fast_sleep)

    async def go():
        transport = FakeTransport()
        transport.jev_error = 503
        async with Harness(stack, transport) as h:
            started = (
                await h.client.post(
                    "/runs", json={"limit": 31, "lanes": 2, "models": ["jev-latest"]}, headers=AUTH
                )
            ).json()
            paused = await h.wait(started["id"], ("failed", "done"))
            assert paused["status"] == "failed" and "Auto-paused" in paused["error"]
            before = paused["processed"]
            assert before < 31
            transport.jev_error = None
            assert (await h.client.post(f"/runs/{started['id']}/resume", headers=AUTH)).json() == {
                "resumed": True
            }
            done = await h.wait(started["id"])
            assert done["status"] == "done" and done["processed"] == 31

    run(go())


def test_jev_out_of_credits_pauses_with_a_clear_message(stack):
    async def go():
        transport = FakeTransport()
        transport.jev_error = 402
        async with Harness(stack, transport) as h:
            started = (
                await h.client.post(
                    "/runs", json={"limit": 31, "lanes": 1, "models": ["jev-latest"]}, headers=AUTH
                )
            ).json()
            paused = await h.wait(started["id"], ("failed", "done"))
            assert paused["status"] == "failed" and "out of credits" in paused["error"]
            assert paused["processed"] < 31

    run(go())


def test_restart_recovers_a_running_run_without_double_counting(stack):
    async def go():
        transport = FakeTransport()
        harness = Harness(stack, transport)
        async with harness as h:
            started = (
                await h.client.post(
                    "/runs", json={"limit": 31, "lanes": 1, "models": ["jev-latest"]}, headers=AUTH
                )
            ).json()
            for _ in range(1000):
                if h.service.live_cache.get(started["id"], {}).get("processed", 0) >= 5:
                    break
                await asyncio.sleep(0.001)
        conn = sqlite3.connect(stack.state_db)
        assert conn.execute("SELECT status FROM runs").fetchone()[0] == "running"
        conn.close()
        async with Harness(stack, FakeTransport()) as h2:
            done = await h2.wait(started["id"])
            assert done["status"] == "done" and done["processed"] == 31
            assert sum(row["n"] for row in done["by_model"]) == 30

    run(go())


def test_global_jev_concurrency_is_bounded(stack):
    limited = s.Settings(**{**stack.__dict__, "jev_concurrency": 3})

    async def go():
        transport = FakeTransport()
        async with Harness(limited, transport) as h:
            started = (
                await h.client.post(
                    "/runs", json={"limit": 31, "lanes": 20, "models": ["jev-latest"]}, headers=AUTH
                )
            ).json()
            await h.wait(started["id"])
        assert transport.max_jev <= 3

    run(go())


def test_public_runs_hit_a_daily_budget_but_direct_api_does_not(stack, monkeypatch):
    monkeypatch.setattr(s, "PUBLIC_DAILY_RUNS", 1)
    public = {**AUTH, "x-safe-signal-public": "1"}

    async def go():
        async with Harness(stack, FakeTransport()) as h:
            billed = {"limit": 2, "lanes": 1, "models": ["jev-latest"]}
            first = await h.client.post("/runs", json=billed, headers=public)
            assert first.status_code == 201
            await h.wait(first.json()["id"], ("done",))
            blocked = await h.client.post("/runs", json=billed, headers=public)
            assert blocked.status_code == 429
            assert "limit" in blocked.json()["error"]
            local = await h.client.post("/runs", json={"limit": 2, "lanes": 1, "models": ["baseline-rules"]}, headers=public)
            assert local.status_code == 201
            await h.wait(local.json()["id"], ("done",))
            direct = await h.client.post("/runs", json=billed, headers=AUTH)
            assert direct.status_code == 201
            await h.wait(direct.json()["id"], ("done",))

    run(go())


EVIDENCE_PASSWORD = "evidence only"
OVERVIEW = "/evidence/stats/overview?source=sandbox_synthetic"


async def incident_total(h) -> int:
    for _ in range(200):
        response = await h.client.get(OVERVIEW, headers=AUTH)
        if response.status_code == 200 and response.json()["total"] > 0:
            return response.json()["total"]
        await asyncio.sleep(0.02)
    raise AssertionError("no incidents were logged")


def evidence_stack(stack):
    digest = hashlib.sha256(EVIDENCE_PASSWORD.encode()).hexdigest()
    return s.Settings(**{**stack.__dict__, "evidence_password_hash": digest})


def test_finished_runs_are_logged_once_and_never_store_text(stack):
    settings = evidence_stack(stack)

    async def go():
        async with Harness(settings, FakeTransport()) as h:
            body = {"limit": 10, "lanes": 2, "models": ["baseline-rules"]}
            first = await h.client.post("/runs", json=body, headers=AUTH)
            await h.wait(first.json()["id"], ("done",))
            total = await incident_total(h)
            again = await h.client.post("/runs", json=body, headers=AUTH)
            await h.wait(again.json()["id"], ("done",))
            for _ in range(100):
                count = h.service.evidence.all("SELECT COUNT(*) AS n FROM ingested_runs")[0]["n"]
                if count == 2:
                    break
                await asyncio.sleep(0.02)
            assert count == 2
            assert await incident_total(h) == total

            listed = (await h.client.get("/evidence/incidents?limit=100", headers=AUTH)).json()
            assert listed["items"]
            assert all(item["source"] == "sandbox_synthetic" for item in listed["items"])
            packet = await h.client.get(f"/evidence/incidents/{listed['items'][0]['incident_id']}", headers=AUTH)
            assert packet.status_code == 200 and "timeline" in packet.json()
            found = await h.client.get("/evidence/incidents?q=bank", headers=AUTH)
            assert found.status_code == 200
            exported = await h.client.get("/evidence/export.csv", headers=AUTH)
            assert exported.headers["content-type"].startswith("text/csv")
            for name in ("timeseries?by=family", "signals", "methods"):
                assert (await h.client.get(f"/evidence/stats/{name}", headers=AUTH)).status_code == 200

    run(go())
    stored = b"".join(path.read_bytes() for path in Path(settings.state_db).parent.glob("evidence.db*"))
    assert SECRET.encode() not in stored


def test_evidence_password_only_opens_the_evidence_store(stack):
    limited = {"authorization": f"Bearer {EVIDENCE_PASSWORD}"}

    async def go():
        async with Harness(evidence_stack(stack), FakeTransport()) as h:
            assert (await h.client.get(OVERVIEW, headers=limited)).status_code == 200
            assert (await h.client.get("/runs", headers=limited)).status_code == 401
            assert (await h.client.get(OVERVIEW)).status_code == 401

    run(go())


def live_incident(**change) -> dict:
    return {
        "incident_id": "a" * 32,
        "occurred_hour": "2026-11-08T14:00:00Z",
        "channel": "call",
        "source": "live",
        "method": "bank_fraud_department",
        "family": "impersonation",
        "tier": "dangerous",
        "max_risk": 0.9,
        "model": "safe-signal-guard",
        "signals": [{"signal": "asks_for_code", "strength": 0.9}],
        **change,
    }


def test_store_rejects_personal_data_and_writes_nothing_from_that_batch(stack):
    async def go():
        async with Harness(stack, FakeTransport()) as h:
            good = await h.client.post("/evidence/incidents", json={"incidents": [live_incident()]}, headers=AUTH)
            assert good.status_code == 200 and good.json() == {"received": 1, "new": 1}
            bad = [live_incident(incident_id="b" * 32), live_incident(incident_id="c" * 32, phone="2145550142")]
            refused = await h.client.post("/evidence/incidents", json={"incidents": bad}, headers=AUTH)
            assert refused.status_code == 400
            assert "2145550142" not in refused.text
            assert h.service.evidence.all("SELECT COUNT(*) AS n FROM incidents")[0]["n"] == 1

    run(go())


def test_live_incidents_expire_after_retention(stack):
    async def go():
        async with Harness(stack, FakeTransport()) as h:
            old = live_incident(occurred_hour="2020-01-01T00:00:00Z")
            await h.client.post("/evidence/incidents", json={"incidents": [old]}, headers=AUTH)
            assert h.service.evidence.expire(s.datetime.now(s.UTC).date()) == 1
            assert h.service.evidence.all("SELECT COUNT(*) AS n FROM incidents")[0]["n"] == 0

    run(go())
