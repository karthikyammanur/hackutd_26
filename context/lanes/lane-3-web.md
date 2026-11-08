# Lane 3: Web (console, phone view, landing)

**Best fit:** the strongest frontend person. This lane is what judges see for most of the demo.
**Why it's independent:** it builds entirely against replayed fixture sessions, so it never waits on the backend.

## You own
`apps/web/` (Next.js, TypeScript strict, Tailwind, shadcn/ui)

## You don't touch
Anything outside `apps/web/`. Types come from `contracts/` (generated into `apps/web/src/contracts.ts` by `checks/gen_types.sh`; never hand-edit).

## You consume
- `UIMessage` stream over WebSocket from `services/api` (Lane 4)
- Until then: a local replayer that reads `evals/fixtures/*.json` and emits the same `UIMessage`s on a timer

## You produce
- `/console`: live call timeline, risk score chart over time, reasons list, alert level, agent trace (Aftercare Planner steps), evidence packet view
- `/phone`: T-Life-style phone mock: alert card with reason + three buttons, whisper indicator, after-call summary
- `/`: landing page (startup feel, real domain if we enter GoDaddy)
- A "privacy receipt" on each alert: what fired, how sure, what was never collected

## Tasks (done-when)
1. **L3-1 Replay** (by 12:30am): `/console` plays `hero1_fake_bank.json` and shows events in order.
2. **L3-2 Console** (by 3am): risk chart, reasons, level and trace render from replay; works for all three fixtures.
3. **L3-3 Phone view** (by 4am): alert card with three buttons; tapping sends a `user_choice` message.
4. **L3-4 Live wire-up** (by 6am): switch from replay to the API WebSocket with one env flag.
5. **L3-5 Landing + polish** (by 10am): landing page, mobile layout checked on a real phone, copy uses only `context/facts.md`.

## Rules that bite you most
R3 (continue is always one tap), R18 (no unsourced numbers in copy), R8 (never display or store full transcripts beyond the live view).
