# Sandbox swarm contract

Shared interface between corpus, backend and UI. Change it only by telling the other owners.

## Ownership
| Owner | Paths |
| --- | --- |
| Research | `sandbox/corpus/research/`, `sandbox/corpus/external/`, `sandbox/worker/src/taxonomy.py` |
| Corpus | `sandbox/corpus/generate/`, `sandbox/corpus/out/`, `sandbox/corpus/load_d1.py` |
| Backend | `sandbox/worker/` except `taxonomy.py` |
| UI | `apps/web/` |

## Case (one JSON object per line in `sandbox/corpus/out/*.jsonl` and `sandbox/corpus/external/*.jsonl`)
```json
{
  "case_id": "gen-call-000001",
  "channel": "call",
  "source": "datagen | generated | robocall_public | sms_public",
  "label_quality": "exact | weak",
  "scam": true,
  "method": "<id from sandbox/worker/src/taxonomy.py METHODS>",
  "family": "<family from METHODS>",
  "hard_negative": false,
  "money_moment_t": null,
  "direction": "inbound",
  "events": []
}
```
- Call events: the datagen kinds `turn`, `sms_otp`, `bank_app_open`, `bank_transfer`, `account`.
- SMS events: `{"t": 0, "kind": "sms", "from_type": "shortcode|longcode|alphanumeric", "text": "...", "domain": null, "domain_age_days": null}`.
- Never include fields that leak the label (`caller`, carrier labels, campaign ids). No real people's phone numbers: replace digit runs in public data.
- `label_quality: weak` means the label is inferred. Report weak cases separately and never mix them into headline accuracy.

## D1
Database `safe-signal-corpus`, created by Corpus. Binding `CORPUS`.
`cases(case_id TEXT PRIMARY KEY, channel, source, label_quality, scam INTEGER, method, family, hard_negative INTEGER, rand REAL, payload TEXT)`; indexes on `(source, method, rand)` and `(channel, rand)`.

## API (Python Worker `safe-signal-sandbox`, `Authorization: Bearer <password>`)
| Route | Purpose |
| --- | --- |
| `GET /corpus` | counts by channel, source, method, family |
| `GET /models` | classifiers available and their live health |
| `POST /runs` | `{"limit": 500, "channels": ["call","sms"], "methods": [], "sources": [], "models": ["jev-latest"], "lanes": 8, "window_turns": 6}` |
| `GET /runs`, `GET /runs/<id>` | list, summary |
| `GET /runs/<id>/live` | live state below; poll about once a second |
| `POST /runs/<id>/rescore` | `{"dangerous_threshold": 0.5, "uncertain_threshold": 0.2, "require_hard_flag": false}`, recomputes `by_method` and `by_model` from stored frames with no model calls |
| `GET /runs/<id>/markers.json`, `.csv` | check-agent markers |
| `POST /runs/<id>/cancel` | stop |
| `GET /lessons` | repeat failures across runs and proposed lessons |

`/live` response:
```json
{
  "id": "run-x", "status": "running|checking|done|failed|cancelled", "elapsed_s": 12.3,
  "total": 500, "processed": 120, "decisions_per_s": 42.1, "frames_per_s": 40.2,
  "lanes": {"configured": 8, "active": 8},
  "brev": {"instances_reported": 1, "endpoints": [{"name": "fast", "healthy": true}, {"name": "deep", "healthy": true}]},
  "steps": [{"name": "frames|agent|jev|score|check", "count": 0, "p50_ms": 0, "p95_ms": 0, "errors": 0}],
  "by_method": [{"method": "...", "family": "...", "n": 0, "caught": 0, "soft_miss": 0, "missed": 0, "clear": 0, "soft_false_alarm": 0, "false_alarm": 0, "no_verdict": 0, "score": 0.0, "method_accuracy": 0.0}],
  "by_model": [{"model": "...", "n": 0, "score": 0.0, "catch_rate": 0.0, "false_alarm_rate": 0.0, "p50_ms": 0}],
  "recent": [{"case_id": "...", "channel": "call", "method": "...", "predicted_method": "...", "tier": "dangerous", "outcome": "caught", "model": "...", "flags": ["asks_for_code"], "ms": 93}],
  "timeline": [{"t": 1.0, "processed": 3, "decisions": 20, "score": 0.8}]
}
```

## Rules
- Every number shown must be measured. No simulated, random or placeholder metrics anywhere, including Brev instance counts.
- No transcript or message text is stored in run results or returned by any API (R8). Only scores, flags, ids and markers.
- Fake data stays at the level of public FTC/FBI awareness examples: no resistance handling, no detector-evasion scripting, nothing usable as an operational script.
- Do not create, stop or delete Brev instances. `soft-copper-mandrill` is used only as an inference endpoint through the existing key.
- Do not commit. Never print secrets. Do not touch Cloudflare projects other than the ones named here.
