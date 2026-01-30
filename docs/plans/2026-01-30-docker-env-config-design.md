# Docker Env Config Defaults (Manhua)

Date: 2026-01-30
Project: manhua
Goal: Make model/runtime parameters configurable via env with safe defaults for Docker.

## Background
Docker runtime needs stable Paddle flags, OCR warmup language, and optional LaMa install toggles. These were hardcoded in `docker-compose.yml` and not fully documented in `.env.example`.

## Decision
Adopt env-driven defaults in `docker-compose.yml` and document them in `.env.example`.

## Scope
- Add missing model/runtime parameters to `.env.example`.
- Replace hardcoded values in `docker-compose.yml` with `${VAR:-default}` syntax.
- Keep existing behavior by using the same defaults as before.

## Parameters (Defaults)
- `AUTO_SETUP_MODELS=on`
- `MODEL_WARMUP_TIMEOUT=300`
- `OCR_WARMUP_LANGS=korean`
- `LAMA_DEVICE=cpu`
- `INSTALL_LAMA=0`
- `FLAGS_use_mkldnn=0`
- `FLAGS_use_pir_api=0`
- `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True`

## Success Criteria
- Docker compose boots with identical defaults when `.env` is absent.
- Users can override runtime behavior by editing `.env` only.

## Risks
- Mis-typed env values can change runtime behavior. Mitigated by defaults and `.env.example`.
