# Architecture

## Flow
```
call events ──► Caller Screen (prior risk)
             ├─► STT ─► Call Guardian (flags) ─┐
             └─► Signal Watcher (signals) ─────┼─► Decision / Jev ─► Alert ─► [call ends] ─► Aftercare Planner
                                               │                                             ├─► Callback
                                               └── state (contracts/state.py) ──► API ──► web ├─► Recovery
                                                                                              └─► Evidence
```

## Latency budgets (targets, measure in spikes)
| Step | Budget |
| --- | --- |
| Caller Screen | < 300 ms before ring |
| Call Guardian check | < 1.5 s per check, every ~3 s |
| Decision | < 100 ms |
| Alert delivered | < 2 s after decision |

## Interfaces between lanes (all in `contracts/`)
| From → To | Contract | File |
| --- | --- | --- |
| Lane 4 (API) → all | Events in, one `SessionState` out | `contracts/events.py`, `contracts/state.py` |
| Lane 2 → Lane 1 | `decide(state) -> Risk` | `contracts/interfaces.py` |
| Lane 4 → Lane 1 | `Comms`, `Voice`, `Store` protocols (Photon, ElevenLabs, Tiger) | `contracts/interfaces.py` |
| Lane 1/4 → Lane 3 | WebSocket `UIMessage` stream (event, state, trace) | `contracts/state.py` |
| Lane 2 → everyone | Fixture sessions for replay and tests | `evals/fixtures/` |

## Replay mode (how lanes work in parallel)
The API can replay a fixture session (`evals/fixtures/*.json`) as if it were live, emitting the same `UIMessage`
stream. Lane 3 builds the whole UI against replay; Lane 1 and 2 test against the same files; Lane 4 swaps replay
for real Photon/STT input later. Nobody waits for anybody.

## Storage (Tiger Data / Postgres)
- `events` hypertable: every event except `turn`, retention policy drops rows after 24 h.
- `evidence` table: packet JSON, kept.
- `policy_index`: pgvector embeddings of T-Mobile pages (official numbers, refund policy, what T-Mobile never asks).
