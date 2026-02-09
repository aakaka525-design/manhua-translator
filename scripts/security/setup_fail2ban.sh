#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FILTER_SRC="$ROOT_DIR/deploy/fail2ban/filter.d/manhua-nginx-probe.conf"
JAIL_TEMPLATE="$ROOT_DIR/deploy/fail2ban/jail.d/manhua-nginx-probe.local.template"

log() {
  printf '[security] %s\n' "$*"
}

if [[ "$(uname -s)" != "Linux" ]]; then
  log "Skipping fail2ban setup (Linux only)."
  exit 0
fi

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  log "Skipping fail2ban setup (requires root)."
  exit 0
fi

if [[ ! -f "$FILTER_SRC" || ! -f "$JAIL_TEMPLATE" ]]; then
  log "Missing fail2ban templates under deploy/fail2ban."
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  log "Skipping fail2ban setup (apt-get not found)."
  exit 0
fi

if ! command -v fail2ban-client >/dev/null 2>&1; then
  log "Installing fail2ban..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y fail2ban
fi

NGINX_LOG_DIR="${MANHUA_NGINX_LOG_DIR:-$ROOT_DIR/logs/nginx}"
ACCESS_LOG="${MANHUA_NGINX_ACCESS_LOG:-$NGINX_LOG_DIR/access.log}"
ERROR_LOG="${MANHUA_NGINX_ERROR_LOG:-$NGINX_LOG_DIR/error.log}"

mkdir -p "$NGINX_LOG_DIR"
touch "$ACCESS_LOG" "$ERROR_LOG"
chmod 755 "$NGINX_LOG_DIR"
chmod 644 "$ACCESS_LOG" "$ERROR_LOG"

install -D -m 0644 "$FILTER_SRC" /etc/fail2ban/filter.d/manhua-nginx-probe.conf
TMP_JAIL="$(mktemp)"
sed "s|__LOG_PATH__|$ACCESS_LOG|g" "$JAIL_TEMPLATE" >"$TMP_JAIL"
install -D -m 0644 "$TMP_JAIL" /etc/fail2ban/jail.d/manhua-nginx-probe.local
rm -f "$TMP_JAIL"

if systemctl list-unit-files fail2ban.service >/dev/null 2>&1; then
  systemctl enable --now fail2ban
fi

fail2ban-client reload
fail2ban-client status manhua-nginx-probe >/dev/null
log "fail2ban jail 'manhua-nginx-probe' is active."
