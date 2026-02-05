# Prebuilt Docker Images + One-Click Start Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Publish prebuilt GHCR images for api+web and add a one-click startup script that pulls and runs those images.

**Architecture:** Use GitHub Actions to build/push `api` and `web` images to GHCR on `main`. Provide a `docker-compose.prebuilt.yml` override and `scripts/start_docker.sh` that pulls and starts prebuilt images without building locally.

**Tech Stack:** Docker, Docker Compose, GitHub Actions, GHCR, shell script, pytest for config assertions.

---

### Task 1: Add failing tests for prebuilt compose/script/workflow

**Files:**
- Create: `tests/test_prebuilt_images_config.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_prebuilt_compose_references_ghcr_images():
    content = Path("docker-compose.prebuilt.yml").read_text(encoding="utf-8")
    assert "ghcr.io/aakaka525-design/manhua-translator-api" in content
    assert "ghcr.io/aakaka525-design/manhua-translator-web" in content


def test_start_script_uses_prebuilt_compose():
    content = Path("scripts/start_docker.sh").read_text(encoding="utf-8")
    assert "docker-compose.prebuilt.yml" in content
    assert "docker compose" in content


def test_workflow_publishes_ghcr_images():
    content = Path(".github/workflows/docker-publish.yml").read_text(encoding="utf-8")
    assert "ghcr.io/aakaka525-design/manhua-translator-api" in content
    assert "ghcr.io/aakaka525-design/manhua-translator-web" in content
```

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_prebuilt_images_config.py`  
Expected: FAIL (files do not exist yet).

**Step 3: Commit**

```bash
git add tests/test_prebuilt_images_config.py
git commit -m "test: add prebuilt image config expectations"
```

---

### Task 2: Add prebuilt compose override and one-click start script

**Files:**
- Create: `docker-compose.prebuilt.yml`
- Create: `scripts/start_docker.sh`

**Step 1: Implement minimal compose override**

```yaml
services:
  api:
    image: ghcr.io/aakaka525-design/manhua-translator-api:${IMAGE_TAG:-latest}
    build: null
  web:
    image: ghcr.io/aakaka525-design/manhua-translator-web:${IMAGE_TAG:-latest}
    build: null
```

**Step 2: Implement start script**

```bash
#!/usr/bin/env bash
set -euo pipefail

docker compose -f docker-compose.yml -f docker-compose.prebuilt.yml pull
docker compose -f docker-compose.yml -f docker-compose.prebuilt.yml up -d
```

Make it executable: `chmod +x scripts/start_docker.sh`.

**Step 3: Run tests to verify they pass**

Run: `pytest -q tests/test_prebuilt_images_config.py`  
Expected: PASS.

**Step 4: Commit**

```bash
git add docker-compose.prebuilt.yml scripts/start_docker.sh
git commit -m "feat: add prebuilt compose and start script"
```

---

### Task 3: Add GHCR build+push workflow

**Files:**
- Create: `.github/workflows/docker-publish.yml`

**Step 1: Implement workflow (build api/web on main)**

Key requirements:
- Trigger: `push` on `main`
- Login: `ghcr.io` using `GITHUB_TOKEN`
- Buildx + cache
- Tags: `latest` + `sha` (git commit)
- Platforms: `linux/amd64`
- Build args: pass `INSTALL_LAMA` (default 0)
- Image names:
  - `ghcr.io/aakaka525-design/manhua-translator-api`
  - `ghcr.io/aakaka525-design/manhua-translator-web`

**Step 2: Run tests to verify they pass**

Run: `pytest -q tests/test_prebuilt_images_config.py`  
Expected: PASS.

**Step 3: Commit**

```bash
git add .github/workflows/docker-publish.yml
git commit -m "build: publish prebuilt images to ghcr"
```

---

### Task 4: Document usage

**Files:**
- Modify: `README.md`
- Modify: `.env.example`

**Step 1: Update README**

Add a “Prebuilt Images” section:
- One-liner: `scripts/start_docker.sh`
- Optional tag override: `IMAGE_TAG=sha-...`
- Explain uses GHCR images (api/web)

**Step 2: Update .env.example**

Add:
```
IMAGE_TAG=latest
```

**Step 3: (Optional) Run tests**

Run: `pytest -q tests/test_prebuilt_images_config.py`  
Expected: PASS.

**Step 4: Commit**

```bash
git add README.md .env.example
git commit -m "docs: add prebuilt image usage"
```

---

## Verification

Run: `pytest -q tests/test_prebuilt_images_config.py`  
Expected: PASS.

---

## Rollout Notes

- GHCR packages will appear under the repo’s Packages tab.
- If private repo, users must `docker login ghcr.io` with a token that has `read:packages`.

