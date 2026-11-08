#!/usr/bin/env bash
# Serves two Nemotron models on THIS machine with vLLM, reachable from localhost only.
# Run it on the sandbox's own instance. It generates a key and writes it to sandbox/.env.
set -euo pipefail
SANDBOX_DIR="${SANDBOX_DIR:-$HOME/safe-signal/sandbox}"
FAST_MODEL="nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16"
DEEP_MODEL="nvidia/NVIDIA-Nemotron-Nano-9B-v2"

KEY_FILE="$SANDBOX_DIR/.nemotron_key"
[ -s "$KEY_FILE" ] || (umask 077; openssl rand -hex 24 > "$KEY_FILE")
API_KEY="$(cat "$KEY_FILE")"

ENV_FILE="$SANDBOX_DIR/.env"
touch "$ENV_FILE"; chmod 600 "$ENV_FILE"
grep -v '^NEMOTRON_API_KEY=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
echo "NEMOTRON_API_KEY=$API_KEY" >> "$ENV_FILE.tmp"
mv "$ENV_FILE.tmp" "$ENV_FILE"; chmod 600 "$ENV_FILE"

start() {  # name, host port, model, max length, gpu fraction, max parallel sequences
  if [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" = "true" ]; then echo "$1 already running"; return; fi
  docker rm -f "$1" >/dev/null 2>&1 || true
  docker run -d --name "$1" --gpus all --ipc=host -p "127.0.0.1:$2:8000" \
    -v "$HOME/.cache/huggingface:/root/.cache/huggingface" vllm/vllm-openai:latest \
    --model "$3" --served-model-name "$1" --api-key "$API_KEY" \
    --trust-remote-code --max-model-len "$4" --gpu-memory-utilization "$5" --max-num-seqs "$6"
}

wait_ready() {  # name, port
  for _ in $(seq 1 120); do
    if curl -sf -H "Authorization: Bearer $API_KEY" "localhost:$2/v1/models" >/dev/null; then
      echo "$1 READY"; return 0
    fi
    if [ "$(docker inspect -f '{{.State.Running}}' "$1")" != "true" ]; then
      echo "$1 CRASHED"; docker logs --tail 30 "$1" 2>&1 | cut -c1-220; return 1
    fi
    sleep 10
  done
  echo "$1 TIMED OUT"; docker logs --tail 30 "$1" 2>&1 | cut -c1-220; return 1
}

# One at a time: vLLM checks free GPU memory at startup, so concurrent starts can fail.
start nemotron-fast 8000 "$FAST_MODEL" 8192 0.30 64
wait_ready nemotron-fast 8000
start nemotron-deep 8001 "$DEEP_MODEL" 16384 0.60 32
wait_ready nemotron-deep 8001
echo "ALL MODELS READY"
