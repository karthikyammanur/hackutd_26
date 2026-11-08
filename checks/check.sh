#!/usr/bin/env bash
# Every gate in one command. Must pass before a PR merges. Skips parts that don't exist yet.
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0
step() { printf '\n== %s\n' "$1"; }
run() { "$@" || { echo "FAILED: $*"; fail=1; }; }

step "Secrets (gitleaks)"
if command -v gitleaks >/dev/null; then run gitleaks detect --no-banner --redact; else echo "gitleaks not installed, skipping (pre-commit still runs it)"; fi

step "No audio or transcript files committed (R8)"
bad=$(git ls-files 2>/dev/null | grep -Ei '\.(wav|mp3|m4a|ogg|flac|webm)$|transcript' | grep -v '^context/' || true)
if [ -n "$bad" ]; then echo "Audio or transcript files tracked:"; echo "$bad"; fail=1; else echo "ok"; fi

step "Python lint and format (ruff)"
run ruff check .
run ruff format --check .

step "Python types (pyright)"
targets=$(for d in contracts services evals; do [ -d "$d" ] && echo "$d"; done)
if command -v pyright >/dev/null; then run pyright $targets; else echo "pyright not installed, skipping"; fi

step "Contracts and fixtures"
run python -m pytest -q contracts

if [ -d services/agents/decision/tests ]; then
  step "Decision rules (R1, R4, R5, R6, R7)"
  run python -m pytest -q services/agents/decision/tests
fi
if [ -d services ]; then
  step "Other Python tests"
  run python -m pytest -q services --ignore=services/agents/decision/tests
fi

step "Eval scorer smoke test"
run python evals/run_eval.py --cases evals/fixtures --preds evals/example_preds.jsonl --gate > /dev/null && echo "ok"

if [ -f apps/web/package.json ]; then
  step "Generated TS types are current"
  run ./checks/gen_types.sh --check
  step "Web typecheck and lint"
  (cd apps/web && run npx tsc --noEmit && run npm run lint --if-present)
fi

echo
if [ "$fail" -ne 0 ]; then echo "CHECKS FAILED"; exit 1; fi
echo "ALL CHECKS PASSED"
