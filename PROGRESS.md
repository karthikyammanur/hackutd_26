# Progress

Update on every merge: newest at the top, one line each. Anyone (or a fresh Claude session) should be able to pick up from here.

## Now
| Lane | Working on | Blocked by |
| --- | --- | --- |
| Lead | Contracts freeze, repo setup | |
| 1 Agents | L1-4 Aftercare Planner + step LLMs (plan) | |
| 2 Decision + data | L2-1 fixtures, L2-2 decide() | |
| 3 Web | L3-1 replay | |
| 4 Platform + demo | L4-1 spikes | |

## Log
- 2026-11-08 L1-2 done: Nemotron Guardian (fast, 3 s timeout), quote->turn t matching, caller-only, dedupe, guard_paused on failure (keyword fallback off). Live: hero1 read_code@101, real bank no flags, 12 checks p50 546 / p95 1137 ms. Runner --offline keeps the keyword stand-in.
- 2026-11-08 LEAD contracts: Store.official_number + Account.hold_changes. L1: Alert node delivers (whisper -> Voice.whisper, alert -> Comms.notify + 3 buttons, template wording); lock_account uses Account; callback uses Store.official_number. pyright now runs in check.sh. Guardian LLM waits on l1-prompts merge.
- 2026-11-08 L1-3 done: walking skeleton. One graph (during + after phases), in-memory checkpointer per session, deterministic stand-ins in graph/stubs.py (decide, caller screen, signal watcher, keyword guardian, fake Comms/Voice/Store). hero1 -> alert at t=101 with 3 buttons, plan + trace; real_bank_callback -> none; eval gate passes on fixtures. Next: L1-2 Guardian.
- 2026-11-08 L1-1 done: llm.py routes fast/deep tiers to their own Brev servers, thinking off at source, NIM fallback per tier (models TBD). Live: fast p50 383 / p95 1696 ms, deep p50 712 / p95 1634 ms (10 calls each, p95 = cold first call).
- 2026-11-08 L1-1 (partial): services/agents/llm.py, Brev to NIM fallback, validate + retry once; 9 offline tests pass. Next: live Brev test, then walking skeleton.
- 2026-11-07 22:50 Kit created: AGENTS.md, context/, contracts/, evals/, checks/.

## Gates
- [ ] 12:00am contracts frozen, spikes done
- [ ] 4:00am Hero 1 end to end
- [ ] 7:00am eval numbers
- [ ] 10:00am feature freeze
- [ ] 11:30am Devpost submitted
