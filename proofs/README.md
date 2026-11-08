# Proofs

`SafeSignal.lean` is a small model of `services/agents/decision/decide.py`, with machine-checked proofs. It uses core Lean only, so there's nothing to install beyond Lean 4.

```
lean proofs/SafeSignal.lean
```

A clean run exits 0, and the printed axioms list contains no `sorryAx`. Checked with Lean 4.35.0.

| Rule | Theorem | What it says |
| --- | --- | --- |
| R1 | `r1_emergency_is_none`, `r1_whole_call` | An emergency call is at `none` after any evidence |
| R5 | `r5_decide_never_lowers`, `r5_whole_call` | Across a call, score and level never fall |
| R6 | `r6_llm_never_lowers` | The decision with LLM flags is at least the decision without them |
| R7 (bonus) | `r7_trusted_stays_quiet` | Dialed to a verified number, no confident hard flag: at or below `nudge` |

Thresholds are parameters, so the proofs hold for any values in `config.py` as long as the R7 cap is below `whisper` and `whisper` is at or below `alert`.

**Limits:** these are proofs about the model, not about the Python itself. The model matches the shape of `decide()`, and the Python tests in `services/agents/decision/tests` check the code against the same rules. If the order of the checks in `decide()` changes, update the model too. The model uses per-mille integers in place of floats, and takes per-kind deduplication as already done.
