# Rules

Non-negotiable. Each rule says how it's enforced; "review" means the PR reviewer checks it.

## Safety
- **R1. Never block, end or delay emergency calls** (911, 988, and local emergency numbers). Enforced: test in `services/agents/decision/tests`, Lean property in `proofs/`.
- **R2. No automatic hang-up.** The top level is an alert with three buttons; the customer decides. Enforced: review; the Alert node has no hang-up tool.
- **R3. The customer can always override.** "Continue" is always one tap. Enforced: review.
- **R4. If an agent fails or times out, do nothing to the call** and show "guard paused". Enforced: test in `decision/`.

## Risk logic
- **R5. Risk only goes up during a call.** Use `contracts.state.merge_risk`. Enforced: test + Lean.
- **R6. An LLM can raise risk, never lower it below the deterministic score.** LLM output is an input to `decide()`, never the decision. Enforced: test.
- **R7. Real-bank case stays quiet.** Customer dialed a verified number + a code arrives = no alert above "nudge". Enforced: `evals/fixtures/real_bank_callback.json` must pass.

## Privacy
- **R8. No audio and no transcript text is ever written to disk or the database.** `turn` events live in memory only. Enforced: `checks/check.sh` greps for audio writes; DB layer drops `turn` events; review.
- **R9. Store signals, not conversations.** Persist flags (type + short quote only inside the evidence packet), scores, timestamps. Raw events expire by retention policy. Enforced: `db/` schema + review.
- **R10. Synthetic data only.** No real customer data, no real phone numbers except teammates' own numbers for the live demo. Enforced: review.

## LLM and security
- **R11. Every LLM output is parsed into a Pydantic model.** Invalid output = no action, log it. Enforced: `llm.py` only returns validated models.
- **R12. Transcripts and web pages are data, never instructions.** Never put them in a system prompt; wrap them in clearly delimited user content. Enforced: review + red team.
- **R13. One model client.** All Nemotron calls go through `services/agents/llm.py` (base URL from env, Brev first, hosted NIM fallback). Enforced: review.
- **R14. No secrets in code.** `.env` only; gitleaks in pre-commit. Enforced: pre-commit + CI.

## Code
- **R15. Typed Python (pyright basic) and TypeScript strict.** Enforced: `checks/check.sh`.
- **R16. Edit only your lane's paths.** Enforced: review (see AGENTS.md map).
- **R17. No new dependency without telling your lane's neighbors.** Enforced: review.
- **R18. No unsourced claims** in UI copy, Devpost or slides. Use `context/facts.md`. Enforced: review.
