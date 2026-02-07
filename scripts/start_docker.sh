#!/usr/bin/env bash
set -euo pipefail

USE_LAMA=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --lama)
      USE_LAMA=1
      shift
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--lama]"
      exit 1
      ;;
  esac
done

if [[ "$USE_LAMA" -eq 1 ]]; then
  echo "Starting with LaMa-enabled api image (source build)..."
  docker compose -f docker-compose.yml -f docker-compose.lama.yml up -d --build
else
  echo "Starting with prebuilt GHCR images..."
  docker compose -f docker-compose.yml -f docker-compose.prebuilt.yml pull
  docker compose -f docker-compose.yml -f docker-compose.prebuilt.yml up -d
fi
