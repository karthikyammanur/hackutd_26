# Evidence store contract

Anonymous incident indicators T-Mobile can search and chart over time. Separate from the test corpus.

**Where it runs now:** one SQLite file, `~/safe-signal/data/evidence.db`, on the Brev machine, served by `sandbox/server/evidence.py` under `/evidence/*`. Each finished run is logged automatically, one incident per test case. The D1 and free-tier rules below apply only to the unused Cloudflare Worker in `worker/`; `worker/src/core.py` is still the shared validation and SQL.

## Ownership
| Owner | Paths |
| --- | --- |
| Backend | `sandbox/evidence/worker/` |
| Backfill | `sandbox/evidence/backfill/` |
| UI | `apps/web/` |

## Privacy rules (enforced in code, not by convention)
Never stored or returned: names, phone numbers, emails, addresses, account or card numbers, customer ids, device ids, audio, transcript text, message text, verbatim quotes.

- Records hold indicators only. `summary` is generated from the indicator fields alone, so the model generating it never sees call content.
- No customer identifier of any kind, hashed or otherwise.
- `caller_cluster` is optional: a keyed HMAC of the caller number using a secret that rotates monthly, for spotting one source hitting many people. The raw number never reaches this service; the caller computes the HMAC. Nullable, and never derived from the customer's number.
- Timestamps round to the hour. Call timing rounds to 15-second buckets.
- `POST /incidents` rejects unknown fields, non-enum values, and any free text containing 7+ consecutive digits, an email, a URL or a phone-like pattern. A rejected batch writes nothing.
- Aggregate charts suppress any group under 5 incidents as `"<5"` for `source=live`. Synthetic data is exempt so demos remain informative.
- Retention: `live` incidents expire after 365 days. Rollups may stay.

## Cost rules: free tier only
No R2, Queues, Vectorize, Workers AI, Logpush, Analytics Engine or anything billed. New D1 database `safe-signal-evidence`, new Worker `safe-signal-evidence`.
- Do not touch `safe-signal-corpus`. It is nearly full.
- Stay under 20,000 D1 rows written per day across all tables, including FTS and indexes, and 200 MB stored. Backfill must count and stop at the limit.
- Reads: every query uses an index or a rollup. No full scans on any request path. Charts read rollups, not raw rows. Page size max 100.
- Cache `/stats/*` at the edge for 60 seconds.

## Schema
```sql
incidents(incident_id TEXT PRIMARY KEY, occurred_hour TEXT, channel TEXT, source TEXT,
  method TEXT, family TEXT, predicted_method TEXT, tier TEXT, outcome TEXT, max_risk REAL,
  first_alert_bucket_s INTEGER, duration_bucket_s INTEGER, money_moved_before_alert INTEGER,
  model TEXT, caller_cluster TEXT, summary TEXT, created_at TEXT)
incident_signals(incident_id TEXT, signal TEXT, strength REAL, PRIMARY KEY (incident_id, signal))
incident_timeline(incident_id TEXT, seq INTEGER, t_bucket_s INTEGER, tier TEXT, risk REAL, PRIMARY KEY (incident_id, seq))
rollup_daily(day TEXT, source TEXT, channel TEXT, method TEXT, family TEXT, tier TEXT, outcome TEXT, n INTEGER, PRIMARY KEY (day, source, channel, method, family, tier, outcome))
rollup_signal_daily(day TEXT, source TEXT, method TEXT, signal TEXT, n INTEGER, PRIMARY KEY (day, source, method, signal))
incidents_fts USING fts5(incident_id UNINDEXED, method, family, tier, signals, summary)
```
`method` uses ids from `sandbox/worker/src/taxonomy.py`. `tier`: safe, uncertain, dangerous. `source`: `sandbox_synthetic`, `live`. `outcome` is nullable and only known in testing: caught, soft_miss, missed, clear, soft_false_alarm, false_alarm.

## API (`Authorization: Bearer <password>`, password in `sandbox/evidence/.env`, Worker keeps only its SHA-256 hash)
| Route | Purpose |
| --- | --- |
| `POST /incidents` | `{"incidents": [...]}`, max 100, idempotent by `incident_id`, nested `signals` and `timeline` |
| `GET /incidents` | `q, method, family, channel, tier, outcome, signal, source, from, to, cursor, limit` |
| `GET /incidents/<id>` | evidence packet: indicators, signals, timeline, summary |
| `GET /stats/overview` | totals by tier, family, source, date range |
| `GET /stats/timeseries` | `bucket=day`, `by=method\|family\|tier`, `from`, `to`, `source` |
| `GET /stats/signals` | signal frequency, optionally by `method` |
| `GET /stats/methods` | per-method counts and tier mix |
| `GET /export.csv` | current filters, max 5,000 rows, CSV-injection safe |

`GET /incidents` returns `{"items": [...], "next_cursor": null, "total_estimate": 0}`.

## Rules
Do not commit. Never print secrets. Do not create or modify Brev instances. Do not deploy Worker `safe-signal-sandbox`: a long evaluation is running on it. Label all sandbox data as synthetic wherever it is shown. Every number shown must come from the database.
