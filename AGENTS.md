# Safe Signal: agent and teammate map

Read this first, every session. It is a map, not a manual: details live in `context/`.

## What we're building (one paragraph)
Safe Signal protects T-Mobile customers on gray-zone calls: calls T-Mobile does NOT already label
"Scam Likely", including calls the customer dials. During the call it watches for two triggers
(a bank code arriving while on a call with an unknown number; the caller asking for something the
customer would never want), alerts the customer with a reason and three buttons, and never hangs up
on its own. After the call, a Nemotron planner runs callback, recovery and evidence.
More: `context/product.md`.

## Read order
1. `AGENTS.md` (this file)
2. `context/rules.md` (non-negotiable)
3. Your lane brief: `context/lanes/lane-<n>-*.md`
4. `contracts/` (the only shared types)
5. `context/architecture.md` when you touch an interface

## Repo map
| Path | What | Owner |
| --- | --- | --- |
| `AGENTS.md`, `CLAUDE.md`, `context/`, `contracts/` | Shared context and types | Lead |
| `services/agents/graph/`, `nodes/`, `prompts/`, `llm.py` | LangGraph agents, Nemotron client | Lane 1 |
| `services/agents/decision/`, `signals/` | Jev adapter, rules, Caller Screen, Signal Watcher | Lane 2 |
| `data/`, `evals/`, `proofs/` | Synthetic data, eval runner, Lean | Lane 2 |
| `apps/web/` | Console, phone view, landing | Lane 3 |
| `services/api/`, `services/agents/tools/`, `db/`, `deploy/`, `spikes/` | API, Photon, ElevenLabs, STT, Tiger Data, deploy | Lane 4 |
| `docs/demo-script.md`, `docs/devpost.md` | Demo and submission | Lane 4 |
| `PROGRESS.md`, `tasks.json` | Status (everyone updates their own rows) | All |

**Only edit paths your lane owns.** Need a change elsewhere? Ask the owner, or open a PR they review.

## Commands
```
./checks/check.sh                 # every gate; must pass before a PR
python -m pytest contracts        # contracts + fixtures still valid
python evals/run_eval.py --cases evals/fixtures --preds <preds.jsonl>
cd apps/web && npm run dev        # web (Lane 3)
uvicorn services.api.main:app --reload   # API (Lane 4)
```

## How to work (humans and agents alike)
- **Plan before editing.** State the plan in 3 to 6 lines, then change the fewest files that do it.
- **Every task has a done-when** in `tasks.json`. Done means the check passes, not "looks right".
- **Build against fixtures and mocks first** (`evals/fixtures/`, `services/agents/tools/mock.py`), so
  no lane waits on another.
- **Small PRs, one task each.** A fresh agent session reviews each PR against `context/rules.md`;
  the author never approves their own.
- **Update `PROGRESS.md`** when you merge: what landed, what's next, what's blocked.
- **Name your assumptions** in the PR description. Unsure about intent? Ask in the team chat, don't guess.

## Contract changes
`contracts/` is frozen once the team agrees on it (target: midnight). To change it: post the diff in the team
chat, get the Lead's OK, then update every fixture and generated type in the same PR.

## Gates and deadlines (CST)
- 12:00am contracts frozen, spikes done
- 4:00am Hero 1 (fake bank call) runs end to end, or we cut scope
- 7:00am eval numbers on the frozen eval set
- 10:00am feature freeze; 11:30am Devpost submitted; 12:00pm hard deadline

## Never
- Commit secrets (use `.env`, see `.env.example`).
- Write audio or transcript text to disk or the database.
- Auto-hang-up a call, or touch emergency numbers (911, 988).
- Let an LLM lower a risk score.
- Put an unsourced number in the UI or pitch (use `context/facts.md`).
