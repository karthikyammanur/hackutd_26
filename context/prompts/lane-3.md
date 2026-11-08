# Lane 3 start prompt: Web

```
You're my coding partner on Safe Signal (HackUTD 2026, T-Mobile track). I own lane 3: the web app.
It's what judges watch for most of the demo, so it must look like a real startup product, not a hackathon page.

Read first, in order: AGENTS.md, context/rules.md, context/lanes/lane-3-web.md, context/product.md,
context/architecture.md, contracts/state.py and contracts/events.py, and the three files in evals/fixtures/.

Hard boundaries:
- Edit only apps/web/ (plus my rows in tasks.json and PROGRESS.md).
- Types come from contracts/ via ./checks/gen_types.sh into apps/web/src/contracts.ts. Never hand-edit that file
  and never redefine those types.
- Copy and numbers in the UI come only from context/facts.md (R18). "Continue" is always one tap (R3).
- The phone view is a clearly labeled concept of a T-Life feature. No T-Mobile logo or trademark assets.

Tonight, in this order:

1) Scaffold apps/web: Next.js (App Router), TypeScript strict, Tailwind, shadcn/ui. Add `lint` and `typecheck`
   scripts. Run ./checks/gen_types.sh to create src/contracts.ts.
   Done when: `npm run dev` serves a page and `npx tsc --noEmit` passes.

2) L3-1 Replay: src/lib/replay.ts reads a fixture (copy evals/fixtures/*.json into apps/web/public/fixtures/ with a
   small script) and emits UIMessage objects on a timer scaled from each event's `t` (speed control: 1x, 4x).
   Build a `useSessionStream(sessionId)` hook with one interface for both replay and the future WebSocket
   (switched by NEXT_PUBLIC_REPLAY).
   Done when: /console plays hero1_fake_bank.json and lists events in order.

3) L3-2 Console (/console): call header (direction, number, verified or not), live transcript pane (in memory only),
   risk score line over time, current level badge (none / nudge / whisper / alert), reasons list, and an
   "Agent trace" panel for the Aftercare Planner. Use a fake risk series computed from events for now; real
   SessionState arrives later over the same hook.
   Done when: all three fixtures play correctly and the real-bank fixture visibly stays at nudge or below.

Design: calm, high-contrast, operations-console feel; one accent color for alerts; risk levels encoded by color
AND label; works at laptop width and on a phone.

Work style: plan first (3 to 6 lines + files you'll touch) and wait for my OK. Small commits. Name every assumption.
When each task is done: show the commands and their output, set its status to "done" in tasks.json, add one line
to PROGRESS.md, and commit with a message starting "L3-1:" etc.
```

## Next tasks (use the resume prompt)
- **L3-3** `/phone`: alert card with the one-line reason, three buttons (call my bank on my card's number, ask my trusted contact, continue), whisper indicator, after-call summary. Tapping sends a `user_choice`.
- **L3-4** Switch the hook to the API WebSocket (`NEXT_PUBLIC_API_WS`) with one env flag.
- **L3-5** Landing page, a "privacy receipt" on each alert (what fired, how sure, what was never collected), real-phone check.
