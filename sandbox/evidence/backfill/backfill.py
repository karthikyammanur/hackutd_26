"""Turn sandbox evaluation results into anonymized incidents for the evidence store.

    python3 backfill.py --run <run id>                  read per-case results (needs the export route)
    python3 backfill.py --markers <markers.json>        use saved failure markers instead
    python3 backfill.py --run <run id> --max-incidents 200

Only ids, labels, tiers, scores and flag names are read. Call and message text is never requested or sent.
A daily counter stops the load under the row limit; re-running the next day resumes where it left off, and
the deterministic incident ids make repeats harmless.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SANDBOX = HERE.parent.parent
sys.path.insert(0, str(SANDBOX / "worker" / "src"))

from taxonomy import METHODS  # noqa: E402

SOURCE = "sandbox_synthetic"
SPREAD_DAYS = 90
BATCH_SIZE = 100
SIGNAL_THRESHOLD = 0.5
DAILY_ROW_LIMIT = 20_000
RESERVED_ROWS = 2_000  # left for live traffic and anything else writing that day
# Used until the backend reports real numbers: 1 row and ~6 indexes, ~4 signals x2, timeline x2, 2 rollups,
# ~4 signal rollups x2, and FTS, which writes several shadow rows.
CONSERVATIVE_ROWS_PER_INCIDENT = 40
INCIDENT_NAMESPACE = uuid.UUID("3f6c1c1e-1d5b-4f5e-9a39-5c8f2e1f7a10")

TIERS = {"safe", "uncertain", "dangerous"}
OUTCOMES = {"caught", "soft_miss", "missed", "clear", "soft_false_alarm", "false_alarm"}
# A correctly cleared call is not an incident, and no_verdict means no model answered.
NOT_INCIDENTS = {"clear", "no_verdict"}
INCIDENT_KEYS = {
    "incident_id",
    "occurred_hour",
    "channel",
    "source",
    "method",
    "family",
    "predicted_method",
    "tier",
    "outcome",
    "max_risk",
    "first_alert_bucket_s",
    "duration_bucket_s",
    "money_moved_before_alert",
    "model",
    "caller_cluster",
    "signals",
    "timeline",
}
_UNSAFE_TEXT = (
    re.compile(r"\d{7,}"),
    re.compile(r"\d{3}[\s.\-)]+\d{3}[\s.\-]+\d{4}"),
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    re.compile(r"https?://|www\.", re.I),
    re.compile(r"\b[\w-]+\.(?:com|net|org|click|site|club|buzz|work|info|xyz)\b", re.I),
)


class PrivacyError(ValueError):
    pass


def bucket(seconds: float | None, size: int = 15) -> int | None:
    if seconds is None:
        return None
    return int(max(seconds, 0) // size * size)


def incident_id_for(run_id: str, case_id: str, model: str) -> str:
    return uuid.uuid5(INCIDENT_NAMESPACE, f"{run_id}|{case_id}|{model}").hex  # the store's accepted hash format


def occurred_hour_for(incident_id: str, anchor: datetime) -> str:
    """Stable position in the 90 days before the anchor. These dates are synthetic, as `source` records."""
    digest = int(hashlib.sha256(incident_id.encode()).hexdigest(), 16)
    moment = anchor - timedelta(hours=digest % (SPREAD_DAYS * 24) + 1)
    return moment.strftime("%Y-%m-%dT%H:00:00Z")


def to_incident(result: dict, run_id: str, anchor: datetime) -> dict | None:
    """Map one per-case result. Returns None when it isn't an incident or can't be mapped cleanly."""
    row = result["row"]
    outcome, tier, method = row.get("outcome"), row.get("tier"), result.get("method")
    if result.get("weak") or outcome in NOT_INCIDENTS or outcome not in OUTCOMES or tier not in TIERS:
        return None
    if method not in METHODS or result.get("channel") not in ("call", "sms"):
        return None

    predicted = result.get("predicted_method") or None
    incident_id = incident_id_for(run_id, result["case_id"], result["model"])
    first = row.get("first_dangerous_t")
    risk = round(float(row.get("max_p_dangerous") or 0.0), 2)
    caught_first = row.get("caught_before_money")
    signals = sorted(
        (
            {"signal": name, "strength": round(float(p), 2)}
            for name, p in (row.get("peak_flags") or {}).items()
            if float(p) >= SIGNAL_THRESHOLD
        ),
        key=lambda s: (-s["strength"], s["signal"]),
    )
    # Per-frame history isn't kept by the sandbox, so the only measured point is the first dangerous rating.
    timeline = [] if first is None else [{"seq": 0, "t_bucket_s": bucket(first), "tier": "dangerous", "risk": risk}]
    # No summary here: the evidence store writes it from these fields and refuses client-supplied text.
    return {
        "incident_id": incident_id,
        "occurred_hour": occurred_hour_for(incident_id, anchor),
        "channel": result["channel"],
        "source": SOURCE,
        "method": method,
        "family": METHODS[method][0],
        "predicted_method": predicted if predicted in METHODS else None,
        "tier": tier,
        "outcome": outcome,
        "max_risk": risk,
        "first_alert_bucket_s": bucket(first),
        "duration_bucket_s": None,
        "money_moved_before_alert": None if caught_first is None else int(not caught_first),
        "model": result["model"],
        "caller_cluster": None,
        "signals": signals,
        "timeline": timeline,
    }


def _strings(value) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def assert_safe(incident: dict) -> None:
    """Last check before anything leaves this machine."""
    extra = set(incident) - INCIDENT_KEYS
    if extra:
        raise PrivacyError(f"unexpected fields: {sorted(extra)}")
    if incident["caller_cluster"] is not None:
        raise PrivacyError("caller_cluster must stay null for synthetic data")
    for text in _strings({k: v for k, v in incident.items() if k not in ("occurred_hour", "incident_id")}):  # generated here
        if any(pattern.search(text) for pattern in _UNSAFE_TEXT):
            raise PrivacyError(f"sensitive pattern in field value of {incident['incident_id']}")


def channel_from_case_id(case_id: str) -> str | None:
    if "-call-" in case_id or case_id.startswith("robocall"):
        return "call"
    if "-sms-" in case_id or case_id.startswith("sms"):
        return "sms"
    return None


def results_from_markers(markers: Iterable[dict]) -> Iterator[dict]:
    """Saved failure markers only list flags at or above 0.5, so that floor is recorded as their strength.

    The model-written feedback and improvement fields are deliberately not read.
    """
    for marker in markers:
        flags = [f for f in str(marker.get("top_flags") or "").split(";") if f]
        yield {
            "case_id": marker["session_id"],
            "model": marker["model"],
            "method": marker["call_type"],
            "channel": channel_from_case_id(marker["session_id"]),
            "weak": False,
            "predicted_method": None,
            "row": {
                "outcome": marker["outcome"],
                "tier": marker["got"],
                "max_p_dangerous": marker.get("max_p_dangerous"),
                "first_dangerous_t": None,
                "caught_before_money": None,
                "peak_flags": dict.fromkeys(flags, SIGNAL_THRESHOLD),
            },
        }


class HttpResults:
    """Reads the sandbox export route page by page."""

    def __init__(self, base_url: str, password: str, run_id: str, model: str | None = None):
        self.base = f"{base_url.rstrip('/')}/runs/{run_id}/results"
        self.password = password
        self.model = model

    def __iter__(self) -> Iterator[dict]:
        after_case, after_model = "", ""
        while True:
            query = {"limit": "1000", "after_case": after_case, "after_model": after_model}
            if self.model:
                query["model"] = self.model
            page = _get_json(f"{self.base}?{urllib.parse.urlencode(query)}", self.password)
            yield from page["items"]
            if not page.get("next"):
                return
            after_case, after_model = page["next"]["after_case"], page["next"]["after_model"]


def _get_json(url: str, password: str) -> dict:
    request = urllib.request.Request(url, headers={"authorization": f"Bearer {password}", "user-agent": "safe-signal-backfill/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def http_post(url: str, password: str, body: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"authorization": f"Bearer {password}", "content-type": "application/json", "user-agent": "safe-signal-backfill/0.1"},
        method="POST",
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code != 429 and error.code < 500:
                raise RuntimeError(f"evidence store refused the batch: HTTP {error.code} {error.read()[:300]!r}") from error
        except urllib.error.URLError:
            pass
        time.sleep(2**attempt)
    raise RuntimeError("evidence store is not responding")


class State:
    """Persistent per-UTC-day row counter and resume position."""

    def __init__(self, path: Path, today: str, anchor: datetime):
        self.path = path
        data = json.loads(path.read_text()) if path.exists() else {}
        self.day = data.get("day", today)
        self.rows_today = int(data.get("rows_today", 0))
        self.anchor = data.get("anchor") or anchor.strftime("%Y-%m-%dT%H:00:00Z")
        self.position = dict(data.get("position", {}))
        self.loaded = int(data.get("loaded", 0))
        self.rows_per_incident = float(data.get("rows_per_incident", CONSERVATIVE_ROWS_PER_INCIDENT))
        if self.day != today:
            self.day, self.rows_today = today, 0

    def anchor_time(self) -> datetime:
        return datetime.strptime(self.anchor, "%Y-%m-%dT%H:00:00Z").replace(tzinfo=UTC)

    def save(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.__dict__ | {"path": None}, indent=1))
        temporary.replace(self.path)


def run_backfill(
    results: Iterable[dict],
    run_id: str,
    post: Callable[[dict], dict],
    state: State,
    budget: int = DAILY_ROW_LIMIT - RESERVED_ROWS,
    max_incidents: int | None = None,
    scan: Callable[[list[dict]], None] | None = None,
) -> dict:
    """Post batches until the source ends, the row budget runs out, or max_incidents is reached."""
    done_before = int(state.position.get(run_id, 0))
    seen = sent = skipped = 0
    batch: list[dict] = []
    report = {"stopped": "finished"}
    anchor = state.anchor_time()

    def flush() -> bool:
        nonlocal sent, batch
        if not batch:
            return True
        needed = len(batch) * state.rows_per_incident
        if state.rows_today + needed > budget:
            report["stopped"] = "daily_row_budget"
            return False
        for incident in batch:
            assert_safe(incident)
        if scan:
            scan(batch)
        response = post({"incidents": batch})
        written = response.get("rows_written")
        if isinstance(written, (int, float)) and written > 0:
            state.rows_today += int(written)
            state.rows_per_incident = max(float(written) / len(batch), 1.0)
        else:  # the backend didn't report it, so assume the conservative cost actually happened
            state.rows_today += int(needed)
        sent += len(batch)
        state.loaded += len(batch)
        state.position[run_id] = seen
        state.save()
        batch = []
        return True

    for result in results:
        seen += 1
        if seen <= done_before:
            continue
        incident = to_incident(result, run_id, anchor)
        if incident is None:
            skipped += 1
            continue
        if max_incidents is not None and sent + len(batch) >= max_incidents:
            seen -= 1
            report["stopped"] = "max_incidents"
            break
        batch.append(incident)
        if len(batch) == BATCH_SIZE:
            position_before_batch = seen
            if not flush():
                seen = position_before_batch - BATCH_SIZE
                break
    else:
        flush()
    if report["stopped"] == "max_incidents":
        flush()
    state.save()
    return report | {"sent": sent, "skipped": skipped, "rows_today": state.rows_today, "rows_per_incident": state.rows_per_incident}


def read_env_value(path: Path, key: str) -> str:
    for line in path.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit(f"{key} is missing from {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--run", help="sandbox run id, read through the export route")
    parser.add_argument("--markers", type=Path, help="saved markers.json instead of the export route")
    parser.add_argument("--run-label", help="id namespace for --markers, defaults to the file's parent directory")
    parser.add_argument("--model", default="jev-latest", help="one incident per case, from this model")
    parser.add_argument("--max-incidents", type=int)
    parser.add_argument("--budget", type=int, default=DAILY_ROW_LIMIT - RESERVED_ROWS)
    parser.add_argument("--sandbox-url", default="https://safe-signal-sandbox.berenis-fopa.workers.dev")
    parser.add_argument("--evidence-url", default=os.environ.get("EVIDENCE_URL", "https://safe-signal-evidence.berenis-fopa.workers.dev"))
    parser.add_argument("--state", type=Path, default=HERE / ".state.json")
    parser.add_argument("--corpus-scan", action="store_true", help="also check every batch against local corpus text")
    args = parser.parse_args()
    if not args.run and not args.markers:
        raise SystemExit("Give --run or --markers")

    if args.run:
        password = read_env_value(SANDBOX / "worker" / ".env", "SANDBOX_PASSWORD")
        results: Iterable[dict] = HttpResults(args.sandbox_url, password, args.run, args.model)
        run_id = args.run
    else:
        markers = [m for m in json.loads(args.markers.read_text()) if m.get("model") == args.model]
        results = results_from_markers(markers)
        run_id = args.run_label or args.markers.resolve().parent.name

    evidence_password = read_env_value(SANDBOX / "evidence" / ".env", "EVIDENCE_PASSWORD")
    now = datetime.now(UTC)
    state = State(args.state, now.strftime("%Y-%m-%d"), now)
    scan = None
    if args.corpus_scan:
        from pii_scan import CorpusScanner

        scan = CorpusScanner.from_files(sorted((SANDBOX / "corpus" / "out").glob("generated_*.jsonl"))).check_batch
    report = run_backfill(
        results,
        run_id,
        lambda body: http_post(f"{args.evidence_url.rstrip('/')}/incidents", evidence_password, body),
        state,
        args.budget,
        args.max_incidents,
        scan,
    )
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
