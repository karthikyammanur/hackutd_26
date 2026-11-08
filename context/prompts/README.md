# Starter prompts

## How to use
1. Clone the repo, `pip install -e ".[dev]" && pre-commit install`, copy `.env.example` to `.env`.
2. Open **Claude Code at the repo root** (it loads `CLAUDE.md` → `AGENTS.md` automatically).
3. Paste your lane's **start prompt** once. Claude plans first and waits for your OK.
4. Every new session after that (new terminal, context got long, next morning): paste the **resume prompt** below.
5. One Claude session per task. When a task's done-when passes: commit, open a PR, start a fresh session.

Using Claude chat instead of Claude Code? Upload `AGENTS.md`, `context/rules.md`, your lane brief and `contracts/` first, then paste the prompt.

| Lane | Start prompt |
| --- | --- |
| 1: Agents | Lead runs this lane |
| 2: Decision, data, evals | `lane-2.md` |
| 3: Web | `lane-3.md` |
| 4: Platform and demo | `lane-4.md` |

## Resume prompt (any lane, any new session)
```
Resume work on Safe Signal, lane <N>.
Read AGENTS.md, context/rules.md, context/lanes/lane-<N>-*.md, PROGRESS.md and tasks.json, then run `git log --oneline -15`.
Pick the first task in tasks.json for lane <N> whose status is "todo" and whose depends_on are all "done" (or can be mocked).
Tell me which task, your plan in 3 to 6 lines, and which files you'll touch. Wait for my OK before editing.
When done: show the done-when evidence (commands + output), set the task to "done" in tasks.json, add one line to PROGRESS.md, and commit.
```

## Review prompt (fresh session, before merging any PR)
```
You are reviewing a pull request for Safe Signal. You did not write it.
Read AGENTS.md and context/rules.md, then review the diff: `git diff main...HEAD`.
Check: every rule R1 to R18 that applies, files outside the author's lane (AGENTS.md map), contract changes without approval,
untested logic, secrets, anything written to disk that could be audio or transcript text.
Run ./checks/check.sh. Reply with: blocking issues, non-blocking issues, and a merge / don't-merge call.
```
