# Progress

Update on every merge: newest at the top, one line each. Anyone (or a fresh Claude session) should be able to pick up from here.

## Now
| Lane | Working on | Blocked by |
| --- | --- | --- |
| Lead | Contracts freeze, repo setup | |
| 1 Agents | L1-1 model client | Brev endpoint (L4-1) |
| 2 Decision + data | L2-5 re-run through the real graph; everything else in the lane is done | L1-3 during graph |
| 3 Web | L3-1 replay | |
| 4 Platform + demo | L4-1 spikes | |

## Log
- 2026-11-08 Lane 2: decide(), Jev adapter, Caller Screen, Signal Watcher, 5 fixtures, 639 train + 125 eval sessions, Lean R1/R5/R6/R7, 5 red-team breaks fixed. Baseline eval (`evals/report.md`): 47.1% catch at alert with a keyword stand-in, gate FAILED; needs Call Guardian via L1-3. Train data is template-only until Nemotron and `llm.py` land.
- 2026-11-07 22:50 Kit created: AGENTS.md, context/, contracts/, evals/, checks/.

## Gates
- [ ] 12:00am contracts frozen, spikes done
- [ ] 4:00am Hero 1 end to end
- [ ] 7:00am eval numbers
- [ ] 10:00am feature freeze
- [ ] 11:30am Devpost submitted
