# Lane 2: Decision, data and evals

**Best fit:** the most careful, analytical person; comfortable with plain Python logic, testing and a bit of ML evaluation. Owns detection quality, which judges score directly.
**Why one person:** the decision rules, the data that tests them and the eval numbers must agree; one owner keeps them consistent.

## You own
`services/agents/decision/`, `services/agents/signals/`, `data/`, `evals/`, `proofs/`

## You don't touch
`graph/`, `nodes/`, `llm.py` (Lane 1) · `tools/`, `api/`, `db/` (Lane 4) · `contracts/` (Lead) · `apps/web/` (Lane 3)

## You consume
`contracts/events.py`, `contracts/state.py`, `contracts/interfaces.py` (`Decider`)

## You produce
- `decision/decide.py`: `decide(state) -> Risk`, deterministic, < 100 ms, with a Jev adapter behind a flag and a rule fallback
- `decision/config.py`: thresholds per level
- `signals/`: Caller Screen scoring (scam list + anomaly features: first-seen, call burst, attestation) and Signal Watcher (Trigger A detection)
- `data/forge/`: synthetic session generator (Nemotron) writing `contracts.events.EvalCase` JSON
- `data/eval/`: the frozen eval set, written by a different model or by hand (F12)
- `evals/run_eval.py` results for the Devpost; red-team log in `evals/redteam.md`
- `proofs/`: Lean properties (R1, R5, R6)

## Tasks (done-when)
1. **L2-1 Fixtures** (by 12am): the three files in `evals/fixtures/` validate (`pytest contracts`). Add 2 more hard negatives.
2. **L2-2 decide()** (by 1:30am): tests prove R1, R4, R5, R6, R7 on fixtures; hero1 reaches `alert`, real-bank stays at or below `nudge`.
3. **L2-3 Signals** (by 3am): Caller Screen and Trigger A run on fixtures and emit `Signal` objects.
4. **L2-4 Data** (by 5am): 500+ training sessions and 100+ eval sessions (at least 30% hard negatives), all schema-valid.
5. **L2-5 Numbers** (by 7am): `run_eval.py` report on the eval set: catch rate, false alerts on hard negatives, time to detect, calibration.
6. **L2-6 Lean + red team** (by 10am): R1, R5, R6 stated and proved on a model of the policy; at least 5 red-team breaks logged with fixes.

## Rules that bite you most
R1, R5, R6, R7, R10.
