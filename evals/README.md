# Evals

Detection quality is a judging criterion. These numbers go on the Devpost, so they must come from a set the system never trained or tuned on.

## Files
| Path | What | Owner |
| --- | --- | --- |
| `fixtures/` | 3+ hand-checked sessions used by every lane for replay and tests | Lane 2 |
| `run_eval.py` | Scorer (standard library only) | Lane 2 |
| `example_preds.jsonl` | Example prediction format | Lane 2 |
| `../data/eval/` | Frozen eval set, written by a different model or by hand (F12) | Lane 2 |
| `redteam.md` | Each red-team break: transcript snippet, why it got through, fix commit | Lane 2 |
| `replay.py` | Replays sessions through Caller Screen, Signal Watcher and `decide()`; writes predictions | Lane 2 |
| `stand_in_guardian.py` | Keyword baseline in place of Call Guardian until the graph exists. Not Nemotron | Lane 2 |
| `tune.py` | Threshold sweep on training data; refuses `data/eval` | Lane 2 |
| `report.md` | Latest numbers and how far to trust them | Lane 2 |

## Session format
One `contracts.events.EvalCase` per file: `session_id`, `label` (`scam`, `type`, `hard_negative`, `first_scam_t`), `events`.

## Prediction format
One JSON line per session: `{"session_id", "alerts": [{"t", "level", "score"}], "latency_ms": [...]}`. Produce it by replaying each session through the graph and recording every alert.

## What we report
| Metric | Target (tune, then freeze) |
| --- | --- |
| Catch rate at `alert` | at least 80% |
| False `alert` rate on benign sessions | at most 5% |
| False `alert` rate on hard negatives | report honestly, aim for 0 on the real-bank case |
| Time to detect | median at or before the scam ask |
| Calibration (ECE) | report it; lower is better |
| Latency p95 per check | under 1.5 s for Guardian, under 100 ms for Decision |

## Rules for honest numbers
- Write the eval set before tuning thresholds; never look at it while tuning.
- At least 30% hard negatives: real bank callbacks, real T-Mobile care, doctors, recruiters, family emergencies.
- Report what fails, by scam type. Judges trust a table with a weak row more than a perfect one.

```
python evals/run_eval.py --cases evals/fixtures --preds evals/example_preds.jsonl
python evals/replay.py --cases data/eval --flags keyword --out out/preds.jsonl
python evals/run_eval.py --cases data/eval --preds out/preds.jsonl --gate
```
