# Lane 2 start prompt: Decision, data, evals

```
You're my coding partner on Safe Signal (HackUTD 2026, T-Mobile track). I own lane 2: decision, data and evals.
Detection quality is a judging criterion, so correctness and honest numbers matter more than speed here.

Read first, in order: AGENTS.md, context/rules.md, context/lanes/lane-2-decision-data.md, context/product.md,
contracts/ (all files), evals/README.md and the three files in evals/fixtures/.

Hard boundaries:
- Edit only services/agents/decision/, services/agents/signals/, data/, evals/, proofs/ (plus my rows in tasks.json and PROGRESS.md).
- contracts/ is frozen. If you think it needs a change, stop and tell me the exact diff and why.
- decide() is deterministic: no LLM calls, no network, under 100 ms.

Tonight, in this order:

1) L2-1: add two more hard-negative fixtures to evals/fixtures/ (same EvalCase format), e.g. a real T-Mobile care
   callback where the customer dialed the verified number, and a benign long call with a first-seen number
   (doctor's office or recruiter) that mentions a "transfer" or a "code" innocently.
   Done when: `python -m pytest -q contracts` passes with 5 fixtures.

2) L2-2: services/agents/decision/ with:
   - config.py: weights per Signal kind and Flag kind, thresholds for nudge / whisper / alert.
   - decide.py: `decide(state: SessionState) -> Risk`. Score = deterministic signal score, combined with flag
     confidences so flags can only ADD risk (R6). Apply merge_risk with the previous risk (R5).
     Direction + verified_org rule: customer dialed a verified number → cap at nudge unless a flag of kind
     gift_cards / safe_account / remote_access appears (R7).
     Emergency numbers (contracts.events.EMERGENCY_NUMBERS) → always Level.none, no actions (R1).
     If state.guard_paused → return the previous risk unchanged (R4).
   - jev_adapter.py: same signature, calls Jev if JEV_URL is set, falls back to the rules on any error or timeout.
   - tests/: one test per rule R1, R4, R5, R6, R7, plus: replaying each fixture's events (build signals and flags
     with simple test helpers) puts hero1 and fake_tmobile_support at alert and every hard negative at nudge or below.
   Done when: `python -m pytest -q services/agents/decision/tests` passes and ./checks/check.sh passes.

Work style: plan first (3 to 6 lines + files you'll touch) and wait for my OK. Small commits. Name every assumption.
When each task is done: show the commands and their output, set its status to "done" in tasks.json, add one line
to PROGRESS.md, and commit with a message starting "L2-1:" or "L2-2:".
```

## Next tasks (paste after L2-2 is merged, or use the resume prompt)
- **L2-3** Caller Screen (scam list + anomaly features) and Signal Watcher (Trigger A: `sms_otp` or `bank_app_traffic` during a call with an unverified number) emitting `Signal`s.
- **L2-4** `data/forge/`: Nemotron generator writing EvalCase JSON; 500+ train sessions, 30%+ hard negatives. Eval set (100+) written separately (Claude or by hand) into `data/eval/` and never used for tuning.
- **L2-5** Replay `data/eval/` through the graph, write predictions JSONL, run `evals/run_eval.py --gate`, commit the report to `evals/report.md`.
- **L2-6** `proofs/`: Lean statements and proofs of R1, R5, R6 on a small model of the policy; red-team log in `evals/redteam.md`.
