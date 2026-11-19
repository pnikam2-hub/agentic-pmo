#!/usr/bin/env bash
# Start an OpenAI-compatible endpoint on :8000.
# llama.cpp: default. Set ENGINE=vllm for a 40 GB+ card (more throughput, more moving parts).
set -euo pipefail

WORK="${WORK:-/opt/gpu-trial}"
MODEL_FILE="${MODEL_FILE:-Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf}"
CTX="${CTX:-32768}"

if [ "${ENGINE:-llamacpp}" = "vllm" ]; then
  pip3 install --quiet --break-system-packages vllm
  exec python3 -m vllm.entrypoints.openai.api_server \
    --model "${VLLM_MODEL:-Qwen/Qwen3-Coder-30B-A3B-Instruct}" \
    --served-model-name local-coder \
    --host 0.0.0.0 --port 8000 \
    --max-model-len "$CTX" --gpu-memory-utilization 0.90
fi

exec "$WORK/llama.cpp/build/bin/llama-server" \
  -m "$WORK/models/$MODEL_FILE" \
  -c "$CTX" -ngl 99 -fa on \
  --host 0.0.0.0 --port 8000 \
  --jinja
