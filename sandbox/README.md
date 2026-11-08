# Sandbox

Replays labeled fake calls through the detection pipeline and reports what to improve. Test bench only: it doesn't feed the main agent yet.

```
fake calls ─► microframes ─► Nemotron agent ─► Jev (safe / uncertain / dangerous) ─► scoreboard vs labels
                  (LangGraph loop, one pass per frame)                                      │
                                               logs/ (failures, lessons) ◄─ Nemotron review agent
```

- **Microframes:** a new frame on each caller turn or phone signal, seeing only what had happened by then.
- **Nemotron fast:** keeps a short note on turns that scrolled out of the window. It never scores, and the newest six turns always reach Jev verbatim.
- **Jev:** picks the tier and answers the 12 red-flag questions from `test/jev-lab/scam.ts`.
- **Call tier:** the highest tier any frame reached, since risk only goes up during a call.
- **Scoreboard:** right tier 1 point, `uncertain` half, wrong tier 0. Built only in code.
- **Nemotron deep:** reads the failures and writes recommendations. Any it can't tie to a real failed session are dropped.

## Output
| Path | What |
| --- | --- |
| `runs/<id>/scoreboard.md`, `.json` | Results by call type, plus pipeline health |
| `runs/<id>/calls.csv` | One row per call: expected, got, points |
| `runs/<id>/frames.jsonl` | Jev's answer for every frame |
| `runs/<id>/recommendations.md`, `.json` | What's going wrong and how to fix it |
| `logs/failure_log.jsonl` | Error rate per call type, per run |
| `logs/consistent_failures.json` | Types failing at 20% or more in 2+ of the last 5 runs |
| `logs/lessons.jsonl` | Recommendations, status `proposed`, for the main agent to use later |

Only scores, flags and ids are written. Transcript text and agent notes stay in memory (R8).

## Run on Brev
Uses its own instance, `safe-signal-sandbox`. From the repo root:

```bash
brev exec safe-signal-sandbox "mkdir -p ~/safe-signal"
brev copy sandbox safe-signal-sandbox:safe-signal/
# also copy test/datagen/out/sessions.jsonl to safe-signal/sandbox/data/
# and put TYPESAFE_API_KEY in safe-signal/sandbox/.env
brev exec safe-signal-sandbox "bash ~/safe-signal/sandbox/brev/setup_models.sh"
brev exec safe-signal-sandbox "cd ~/safe-signal && python3 -m venv .venv && .venv/bin/pip install -q -r sandbox/requirements.txt"
brev exec safe-signal-sandbox "cd ~/safe-signal && .venv/bin/python -m sandbox.run --per-type 20"
```

`--per-type 0` replays all 42,003 calls, about 250,000 Jev requests, so check your Jev quota first.

**The GPU bills by the hour.** Delete only this instance when finished: `brev delete safe-signal-sandbox`.

Tests: `pip install -r sandbox/requirements.txt && python -m pytest sandbox/tests`
