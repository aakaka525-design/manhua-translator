# Docker Deployment (CPU) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a CPU-only Docker setup that reliably runs OCR/LaMa with pinned versions, auto-model warmup, and a production frontend served by Nginx with same-origin API.

**Architecture:** Two services (api + web) in docker compose. The api service uses a pinned Paddle/PaddleOCR stack and runtime flags to avoid OneDNN/PIR issues, plus auto model setup on startup. The web service serves Vite production build and reverse-proxies `/api` to the api container.

**Tech Stack:** Docker, docker-compose, Python 3.10, FastAPI, Nginx, Vite.

### Task 1: Add Docker requirements (pinned CPU stack)

**Files:**
- Create: `docker/requirements-docker-cpu.txt`

**Step 1: Write the requirements file**

```text
-r ../requirements.txt
paddlepaddle==2.6.2
paddleocr==2.7.3
paddlex==3.4.0
PyYAML==6.0.2
simple-lama-inpainting==0.1.2
```

**Step 2: Validate the file exists**

Run: `test -f docker/requirements-docker-cpu.txt`
Expected: exit code 0

**Step 3: Commit**

```bash
git add docker/requirements-docker-cpu.txt
git commit -m "build: add docker cpu requirements"
```

### Task 2: Add backend Dockerfile

**Files:**
- Create: `docker/Dockerfile.api`

**Step 1: Write the Dockerfile**

```dockerfile
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    FLAGS_use_mkldnn=0 \
    FLAGS_use_pir_api=0 \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
  && rm -rf /var/lib/apt/lists/*

COPY docker/requirements-docker-cpu.txt /app/docker/requirements-docker-cpu.txt
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/docker/requirements-docker-cpu.txt

COPY . /app

EXPOSE 8000
CMD ["python", "main.py", "server", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 2: Validate the Dockerfile**

Run: `grep -n "FLAGS_use_mkldnn" -n docker/Dockerfile.api`
Expected: shows the env flags line.

**Step 3: Commit**

```bash
git add docker/Dockerfile.api
git commit -m "build: add api dockerfile"
```

### Task 3: Add frontend Dockerfile and Nginx config

**Files:**
- Create: `docker/Dockerfile.web`
- Create: `docker/nginx.conf`

**Step 1: Write Dockerfile for frontend**

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* /app/frontend/
WORKDIR /app/frontend
RUN npm install
COPY frontend/ /app/frontend/
RUN npm run build

FROM nginx:alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html
EXPOSE 80
```

**Step 2: Write Nginx config**

```nginx
server {
  listen 80;
  server_name _;

  root /usr/share/nginx/html;
  index index.html;

  location /api/ {
    proxy_pass http://api:8000/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  }

  location / {
    try_files $uri /index.html;
  }
}
```

**Step 3: Validate files exist**

Run: `test -f docker/Dockerfile.web && test -f docker/nginx.conf`
Expected: exit code 0

**Step 4: Commit**

```bash
git add docker/Dockerfile.web docker/nginx.conf
git commit -m "build: add web dockerfile and nginx config"
```

### Task 4: Add docker-compose for CPU deployment

**Files:**
- Create: `docker-compose.yml`

**Step 1: Write compose file**

```yaml
version: "3.8"
services:
  api:
    build:
      context: .
      dockerfile: docker/Dockerfile.api
    environment:
      AUTO_SETUP_MODELS: "on"
      MODEL_WARMUP_TIMEOUT: "300"
      LAMA_DEVICE: "cpu"
      FLAGS_use_mkldnn: "0"
      FLAGS_use_pir_api: "0"
      PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK: "True"
    volumes:
      - ./data:/app/data
      - ./output:/app/output
      - ./logs:/app/logs
      - ./models:/root/.paddlex
    ports:
      - "8000:8000"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/system/models', timeout=5).read()"]
      interval: 10s
      timeout: 5s
      retries: 12

  web:
    build:
      context: .
      dockerfile: docker/Dockerfile.web
    depends_on:
      api:
        condition: service_healthy
    ports:
      - "80:80"
```

**Step 2: Validate compose config**

Run: `docker compose config > /tmp/manhua-compose.yml`
Expected: exit code 0, config renders.

**Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "build: add docker compose deployment"
```

### Task 5: Add .dockerignore

**Files:**
- Create: `.dockerignore`

**Step 1: Write .dockerignore**

```text
.git
.worktrees
__pycache__
.venv
node_modules
frontend/node_modules
frontend/dist
output
data
logs
models
```

**Step 2: Commit**

```bash
git add .dockerignore
git commit -m "build: add dockerignore"
```

### Task 6: Update README with Docker Quick Start

**Files:**
- Modify: `README.md`

**Step 1: Add Docker section**

Add a section with:
- `docker compose up -d --build`
- `curl http://localhost/api/v1/system/models`
- `http://<host>/` for UI
- Notes on volumes and CPU-only defaults

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add docker deployment instructions"
```

### Task 7: Smoke test checklist (manual)

**Step 1: Build containers**

Run: `docker compose up -d --build`

**Step 2: Verify API health**

Run: `curl http://localhost/api/v1/system/models`
Expected: `ready` for all models.

**Step 3: Verify frontend**

Open: `http://localhost/`
Expected: UI loads without CORS/MIME errors.

**Step 4: Stop stack**

Run: `docker compose down`
