#!/usr/bin/env bash
set -euo pipefail

docker compose -f docker-compose.yml -f docker-compose.prebuilt.yml pull
docker compose -f docker-compose.yml -f docker-compose.prebuilt.yml up -d
