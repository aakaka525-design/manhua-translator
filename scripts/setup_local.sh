#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$ROOT_DIR/tools/bin"
TMP_DIR="$(mktemp -d)"

PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python"
fi

BACKEND="${UPSCALE_BACKEND:-pytorch}"

$PYTHON_BIN -m pip install -r "$ROOT_DIR/requirements.txt"

mkdir -p "$BIN_DIR"

if [[ "$BACKEND" == "ncnn" ]]; then
  VERSION="v0.2.5.0"
  if [[ "$(uname -s)" == "Darwin" ]]; then
    ZIP_NAME="realesrgan-ncnn-vulkan-20220424-macos.zip"
  elif [[ "$(uname -s)" == "Linux" ]]; then
    ZIP_NAME="realesrgan-ncnn-vulkan-20220424-ubuntu.zip"
  else
    echo "Unsupported OS: $(uname -s)"
    exit 1
  fi

  URL="https://github.com/xinntao/Real-ESRGAN/releases/download/${VERSION}/${ZIP_NAME}"

  curl -L "$URL" -o "$TMP_DIR/$ZIP_NAME"
  unzip -q "$TMP_DIR/$ZIP_NAME" -d "$TMP_DIR/extract"

  BIN_SRC="$(find "$TMP_DIR/extract" -type f -name realesrgan-ncnn-vulkan -not -path "*/__MACOSX/*" -size +1024c | head -n 1)"
  MODEL_SRC="$(find "$TMP_DIR/extract" -type d -name models -not -path "*/__MACOSX/*" | head -n 1)"

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

  echo "✅ Real-ESRGAN (ncnn) installed to $BIN_DIR"
else
  $PYTHON_BIN -m pip install torch torchvision realesrgan basicsr

  MODEL_PATH="${UPSCALE_MODEL_PATH:-$BIN_DIR/RealESRGAN_x4plus.pth}"
  MODEL_URL="${UPSCALE_MODEL_URL:-}"

  if [[ ! -f "$MODEL_PATH" ]]; then
    if [[ -n "$MODEL_URL" ]]; then
      curl -L "$MODEL_URL" -o "$MODEL_PATH"
    else
      echo "Model not found: $MODEL_PATH"
      echo "Set UPSCALE_MODEL_PATH or UPSCALE_MODEL_URL to download the .pth file."
      exit 1
    fi
  fi

  echo "✅ Real-ESRGAN (PyTorch) model ready: $MODEL_PATH"
fi

rm -rf "$TMP_DIR"
