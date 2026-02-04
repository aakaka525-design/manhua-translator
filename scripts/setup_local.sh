#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$ROOT_DIR/tools/bin"
TMP_DIR="$(mktemp -d)"
VERSION="v0.2.0"

if [[ "$(uname -s)" == "Darwin" ]]; then
  ZIP_NAME="realesrgan-ncnn-vulkan-v0.2.0-macos.zip"
elif [[ "$(uname -s)" == "Linux" ]]; then
  ZIP_NAME="realesrgan-ncnn-vulkan-v0.2.0-ubuntu.zip"
else
  echo "Unsupported OS: $(uname -s)"
  exit 1
fi

URL="https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan/releases/download/${VERSION}/${ZIP_NAME}"

python -m pip install -r "$ROOT_DIR/requirements.txt"

mkdir -p "$BIN_DIR"

curl -L "$URL" -o "$TMP_DIR/$ZIP_NAME"
unzip -q "$TMP_DIR/$ZIP_NAME" -d "$TMP_DIR/extract"

BIN_SRC="$(find "$TMP_DIR/extract" -type f -name realesrgan-ncnn-vulkan | head -n 1)"
MODEL_SRC="$(find "$TMP_DIR/extract" -type d -name models | head -n 1)"

if [[ -z "$BIN_SRC" ]]; then
  echo "Binary not found in zip"
  exit 1
fi

cp "$BIN_SRC" "$BIN_DIR/realesrgan-ncnn-vulkan"
chmod +x "$BIN_DIR/realesrgan-ncnn-vulkan"

if [[ -n "$MODEL_SRC" ]]; then
  rm -rf "$BIN_DIR/models"
  cp -R "$MODEL_SRC" "$BIN_DIR/models"
fi

rm -rf "$TMP_DIR"

echo "✅ Real-ESRGAN installed to $BIN_DIR"
