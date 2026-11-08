#!/usr/bin/env bash
# Generate apps/web/src/contracts.ts from contracts/ (JSON Schema -> TypeScript).
# Usage: ./checks/gen_types.sh          write the file
#        ./checks/gen_types.sh --check  fail if the file is out of date
set -euo pipefail
cd "$(dirname "$0")/.."
out=apps/web/src/contracts.ts
tmp=$(mktemp -d)
python - "$tmp/schema.json" <<'PY'
import json, sys
from pydantic import TypeAdapter
from contracts.events import EvalCase
from contracts.state import SessionState, UIMessage
schema = TypeAdapter(tuple[UIMessage, SessionState, EvalCase]).json_schema()
json.dump(schema, open(sys.argv[1], "w"), indent=2)
PY
npx --yes json-schema-to-typescript@15 "$tmp/schema.json" --no-additionalProperties > "$tmp/contracts.ts"
if [ "${1:-}" = "--check" ]; then
  diff -q "$tmp/contracts.ts" "$out" >/dev/null || { echo "$out is stale: run ./checks/gen_types.sh"; exit 1; }
else
  mkdir -p "$(dirname "$out")" && cp "$tmp/contracts.ts" "$out" && echo "wrote $out"
fi
