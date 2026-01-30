# Docker Deployment Design (CPU)

Date: 2026-01-30
Project: manhua
Focus: Fix server deployment config drift via Docker (CPU-only)

## 1. Background
Server deployment showed OCR returning zero regions even though models reported `ready`. Root cause was runtime incompatibility in Paddle/PIR/OneDNN plus version drift and missing model auto-setup. Frontend also had CORS/MIME errors when served separately over HTTP.

## 2. Goals
- Provide a CPU-only Docker deployment that works consistently on Linux servers.
- Ensure OCR/LaMa models download and warm up automatically at container start.
- Lock dependency versions to avoid runtime incompatibilities.
- Serve frontend and backend with same origin to eliminate CORS/MIME issues.
- Persist model caches and outputs on the host.

## 3. Non-Goals
- GPU (CUDA) support.
- TLS/HTTPS termination (HTTP only for now).
- Multi-node scaling.

## 4. Proposed Architecture
Use docker compose with two services:
- **api**: Python backend container (FastAPI) with pinned Paddle/OCR stack and warmup on startup.
- **web**: Nginx serving production-built frontend and reverse-proxy `/api` to `api:8000`.

Optional:
- **auth-browser**: use existing `docker-compose.auth.yml` for scraper auth.

## 5. Key Design Decisions
- **Pinned versions** to avoid `onednn_instruction` and PIR runtime errors:
  - `paddlepaddle==2.6.2`
  - `paddleocr==2.7.3`
  - `paddlex==3.4.0`
  - `PyYAML==6.0.2`
- **Runtime flags** to disable unstable backends:
  - `FLAGS_use_mkldnn=0`
  - `FLAGS_use_pir_api=0`
  - `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True`
- **Auto model setup**:
  - `AUTO_SETUP_MODELS=on`
  - `MODEL_WARMUP_TIMEOUT=300`
  - `LAMA_DEVICE=cpu`
- **Same-origin frontend** via Nginx to avoid CORS and MIME issues.

## 6. Data & Cache Persistence
Bind mounts:
- `./data:/app/data`
- `./output:/app/output`
- `./logs:/app/logs`
- `./models:/root/.paddlex` (OCR model cache)

## 7. Health Checks
- `/api/v1/system/models` should report all `ready`.
- Compose healthcheck waits for readiness before marking container healthy.

## 8. Success Criteria
- `curl /api/v1/system/models` shows `ready` for `ppocr_det/ppocr_rec/lama`.
- `translate/image` returns `regions_count > 0` for known Korean pages.
- Frontend loads from `http://<host>/` without CORS or MIME errors.

## 9. Rollout Plan
1) Add Dockerfile(s), Nginx config, and docker-compose.yml.
2) Update README with Docker quick start.
3) Build and run `docker compose up -d` on server.
4) Validate health checks and a sample translation.

## 10. Risks & Mitigations
- **Large model downloads**: persist `./models` on host to avoid re-downloads.
- **Python/Paddle incompatibility**: pin versions and disable OneDNN/PIR.
- **Frontend build size**: use multi-stage build and Nginx gzip.

## 11. Open Questions
- None for CPU-only; HTTPS can be added later via reverse proxy.

## 12. Troubleshooting Notes (from tests)
- **AI translator init failed (`No module named 'openai'`)**: ensure `openai` is included in Docker requirements and rebuild.
- **OCR returns zero regions**: confirm `SOURCE_LANGUAGE` and `OCR_WARMUP_LANGS` are set to `korean`, enable `DEBUG_OCR=1` for raw OCR logs.
- **Paddle PIR/OneDNN errors**: keep `FLAGS_use_mkldnn=0` and `FLAGS_use_pir_api=0`.
- **Frontend CORS/MIME errors**: use same-origin web container at `http://<host>/` or add HTTPS via reverse proxy.
- **API unhealthy on first run**: model download warmup can take time; check logs and wait for health check to pass.
