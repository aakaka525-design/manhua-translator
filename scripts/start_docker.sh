#!/usr/bin/env bash
set -euo pipefail

USE_LAMA=0
AUTO_SECURITY="${AUTO_SECURITY:-1}"
SECURITY_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --lama)
      USE_LAMA=1
      shift
      ;;
    --no-security)
      AUTO_SECURITY=0
      shift
      ;;
    --security-only)
      SECURITY_ONLY=1
      shift
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--lama] [--no-security] [--security-only]"
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECURITY_SCRIPT="$SCRIPT_DIR/security/setup_fail2ban.sh"

setup_security() {
  if [[ "$AUTO_SECURITY" -ne 1 ]]; then
    echo "Skipping fail2ban setup (--no-security or AUTO_SECURITY=0)."
    return
  fi
  if [[ ! -x "$SECURITY_SCRIPT" ]]; then
    echo "Security setup script not found: $SECURITY_SCRIPT"
    return
  fi
  "$SECURITY_SCRIPT"
}

if [[ "$SECURITY_ONLY" -eq 1 ]]; then
  echo "Running security bootstrap only..."
  setup_security
  exit 0
fi

if [[ "$USE_LAMA" -eq 1 ]]; then
  echo "Starting with LaMa-enabled api image (source build)..."
  docker compose -f docker-compose.yml -f docker-compose.lama.yml up -d --build
else
  echo "Starting with prebuilt GHCR images..."
  docker compose -f docker-compose.yml -f docker-compose.prebuilt.yml pull
  docker compose -f docker-compose.yml -f docker-compose.prebuilt.yml up -d
fi

setup_security
