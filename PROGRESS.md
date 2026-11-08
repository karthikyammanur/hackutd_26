# Progress

Update on every merge: newest at the top, one line each. Anyone (or a fresh Claude session) should be able to pick up from here.

## Now
| Lane | Working on | Blocked by |
| --- | --- | --- |
| Lead | Contracts freeze, repo setup | |
| 1 Agents | L1-5 swap mocks for lane 4 adapters | lane 4 real adapters (L4-4) |
| 2 Decision + data | L2-1 fixtures, L2-2 decide() | |
| 3 Web | L3-1 replay | |
| 4 Platform + demo | L4-1 spikes | |

## Log
- 2026-11-08 L4-3 (API): services/api: /health, WS /ws/{id} (UIMessage event/trace/state), POST /sessions/{id}/events (live, ordered worker per session, 202), /sessions/{id}/choice (1/2/3 or name), /sessions/{fixture}/replay?speed=. Graphs run off the event loop; no turn text after call_end. hero1 via /events matches replay levels; live run on Nemotron verified through a real server. Waiting on lane 3 to connect (L4-3 done-when). docs/api.md has the quickstart.
- 2026-11-08 L1: alert copy grounded in code: draft reason from the newest flag/signal, Nemotron only rephrases, every claim keyword (code, read back, gift card, safe account, remote access, transfer, SIM) must map to a flag or signal or the draft is used. Live hero1 t=92 whisper now says the code arrived, not that the caller wants it.
- 2026-11-08 L1-4 done: Nemotron planner (deep) with rules in code (lock_account kept at alert unless continue; notify only on choice; call_bank forces callback; evidence last), Callback/Recovery (deep, 25 s) and Evidence summary (fast) with template fallbacks, AlertCopy wording (fast, 1.5 s). Live hero1: every step ran on Nemotron, in order, with results. Guardian: no hindsight flags; hero1 alert at t=101.
- 2026-11-08 L1-2 done: Nemotron Guardian (fast, 3 s timeout), quote->turn t matching, caller-only, dedupe, guard_paused on failure (keyword fallback off). Live: hero1 read_code@101, real bank no flags, 12 checks p50 546 / p95 1137 ms. Runner --offline keeps the keyword stand-in.
- 2026-11-08 LEAD contracts: Store.official_number + Account.hold_changes. L1: Alert node delivers (whisper -> Voice.whisper, alert -> Comms.notify + 3 buttons, template wording); lock_account uses Account; callback uses Store.official_number. pyright now runs in check.sh. Guardian LLM waits on l1-prompts merge.
- 2026-11-08 L1-3 done: walking skeleton. One graph (during + after phases), in-memory checkpointer per session, deterministic stand-ins in graph/stubs.py (decide, caller screen, signal watcher, keyword guardian, fake Comms/Voice/Store). hero1 -> alert at t=101 with 3 buttons, plan + trace; real_bank_callback -> none; eval gate passes on fixtures. Next: L1-2 Guardian.
- 2026-11-08 L1-1 done: llm.py routes fast/deep tiers to their own Brev servers, thinking off at source, NIM fallback per tier (models TBD). Live: fast p50 383 / p95 1696 ms, deep p50 712 / p95 1634 ms (10 calls each, p95 = cold first call).
- 2026-11-08 L1-1 (partial): services/agents/llm.py, Brev to NIM fallback, validate + retry once; 9 offline tests pass. Next: live Brev test, then walking skeleton.
- 2026-11-07 22:50 Kit created: AGENTS.md, context/, contracts/, evals/, checks/.

## Known issues (for red team)
- Guardian (fast 4B) gives policy_contradiction 0.85 to a first-turn story on a scam call ("your number was used to open accounts in two states") despite the rule that a story with no ask is not a contradiction. Harmless on that call (it is a scam), but the same opener on a real fraud alert would add risk. The judged-turn rule only stops hindsight re-flags, not a first look. Lead decision: leave as is.

## Gates
- [ ] 12:00am contracts frozen, spikes done
- [ ] 4:00am Hero 1 end to end
- [ ] 7:00am eval numbers
- [ ] 10:00am feature freeze
- [ ] 11:30am Devpost submitted
