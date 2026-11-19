#!/usr/bin/env bash
# Install llama.cpp with CUDA and fetch a 4-bit coder model that fits a 24 GB card.
# Run on the rented GPU box, as root. Idempotent enough to re-run after a reboot.
set -euo pipefail

MODEL_REPO="${MODEL_REPO:-unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF}"
MODEL_FILE="${MODEL_FILE:-Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf}"
WORK="${WORK:-/opt/gpu-trial}"

echo "== GPU =="
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || {
  echo "nvidia-smi missing: this box has no usable GPU. Stop."; exit 1; }

echo "== base packages =="
apt-get update -qq
apt-get install -y -qq build-essential cmake git curl libcurl4-openssl-dev python3-pip python3-venv

echo "== llama.cpp (CUDA) =="
if [ ! -d "$WORK/llama.cpp" ]; then
  mkdir -p "$WORK" && cd "$WORK"
  git clone --depth 1 https://github.com/ggml-org/llama.cpp
fi
cd "$WORK/llama.cpp"
cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j "$(nproc)"

echo "== model =="
mkdir -p "$WORK/models"
if [ ! -f "$WORK/models/$MODEL_FILE" ]; then
  pip3 install --quiet --break-system-packages huggingface_hub
  python3 - "$MODEL_REPO" "$MODEL_FILE" "$WORK/models" <<'PY'
import sys
from huggingface_hub import hf_hub_download
repo, filename, dest = sys.argv[1], sys.argv[2], sys.argv[3]
path = hf_hub_download(repo_id=repo, filename=filename, local_dir=dest)
print("downloaded", path)
PY
fi

echo
echo "ready. start the server with:  $WORK/llama.cpp/build/bin/llama-server \\"
echo "  -m $WORK/models/$MODEL_FILE -c 32768 -ngl 99 --host 0.0.0.0 --port 8000 -fa on"
