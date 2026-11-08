# Lane 1: Agents (LangGraph + Nemotron)

**Best fit:** the strongest Python person who is comfortable prompting LLMs and reading LangGraph docs.
**Why one person:** every agent shares one state object, one model client and one graph; splitting them across people causes collisions.

## You own
`services/agents/graph/`, `services/agents/nodes/`, `services/agents/prompts/`, `services/agents/llm.py`

## You don't touch
`decision/`, `signals/` (Lane 2) · `tools/`, `services/api/` (Lane 4) · `contracts/` (Lead) · `apps/web/` (Lane 3)

## You consume
- `contracts/state.py` (SessionState), `contracts/interfaces.py` (`Decider`, `Comms`, `Voice`, `Store`)
- Until Lane 2 and 4 land: `services/agents/tools/mock.py` and a stub `decide()` that returns the deterministic score
- Fixtures: `evals/fixtures/*.json`

## You produce
- `llm.py`: one OpenAI-compatible client (Brev base URL from env, hosted NIM fallback); `structured(prompt, Model) -> Model` that always validates (R11)
- Nodes: Call Guardian, Alert (wording), Aftercare Planner, Callback, Recovery, Evidence summary
- `graph/build.py`: `build_graph() -> CompiledGraph` with during and after subgraphs
- A `trace` list in state that Lane 3 renders (planner step, tool, result)

## Tasks (done-when)
1. **L1-1 Model client** (by 12:30am): `pytest services/agents/tests/test_llm.py` passes against Brev with a schema-validated reply.
2. **L1-2 Call Guardian** (by 2am): on `hero1_fake_bank.json` it flags `read_code` at the caller's ask; on `real_bank_callback.json` no `read_code` flag with confidence > 0.5.
3. **L1-3 During graph** (by 3am): replaying `hero1_fake_bank.json` produces an `alert` level and three buttons in state, using the stub or real `decide()`.
4. **L1-4 Aftercare Planner** (by 5am): after `call_end`, the plan has ordered steps and each step calls a mock tool; trace shows every step.
5. **L1-5 Real tools** (by 7am): swap mocks for Lane 4's adapters; Hero 1 runs end to end with a real callback.

## Rules that bite you most
R6 (LLM never lowers risk), R11 (validate every output), R12 (transcripts are data), R2 (no hang-up tool on Alert).
