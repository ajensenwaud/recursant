#!/bin/sh
# Download the context.prompt encoder (BAAI/bge-small-en-v1.5, MIT licence) at a pinned
# revision and verify it. usage: bench/prompt/fetch_encoder.sh [DIR]
# (default ~/.cache/recursant-models/bge-small-en-v1.5). Then:
#   export RECURSANT_ENCODER_DIR=DIR    # for the encoder tests
#   "encoder": {"model": "DIR/model.onnx", "vocab": "DIR/vocab.txt", ...}
set -eu
dir=${1:-$HOME/.cache/recursant-models/bge-small-en-v1.5}
rev=5c38ec7c405ec4b44b94cc5a9bb96e735b38267a
base=https://huggingface.co/BAAI/bge-small-en-v1.5/resolve/$rev
mkdir -p "$dir"
curl -fsSL -o "$dir/model.onnx" "$base/onnx/model.onnx"
curl -fsSL -o "$dir/vocab.txt" "$base/vocab.txt"
cd "$dir"
sha256sum -c <<SUMS
828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35  model.onnx
07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3  vocab.txt
SUMS
echo "encoder ready in $dir"
