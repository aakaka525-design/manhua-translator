# Scraper State File Upload Design

Date: 2026-01-27
Project: manhua
Scope: Mobile-friendly upload of Playwright storage_state.json

## 1. Background
Users on mobile cannot easily obtain Playwright state files. The UI should accept an uploaded JSON state file and store it on the server in the default location to keep setup simple.

## 2. Goals
- Provide a simple file upload in the scraper settings.
- Auto-save to the default path per site.
- Immediately show cookie validity after upload.

## 3. Non-Goals
- No in-browser cookie export.
- No automatic Cloudflare challenge handling on mobile.

## 4. UX/Behavior
- Add an "Upload state file" button to the scraper settings.
- Accept .json only; upload via multipart/form-data.
- Server saves to:
  - Mangaforfree: data/mangaforfree_state.json
  - ToonGod: data/toongod_state.json
- After upload, update the path input and run state-info check.

## 5. API
- POST /api/v1/scraper/upload-state
  - Input: base_url, file
  - Output: { path, status, message, expires_at, expires_at_text }

## 6. Error Handling
- Invalid JSON -> clear error message.
- Missing cookies -> explicit error.
- Oversize file -> reject with size limit.

## 7. Testing
- Manual: upload valid state -> path updated + status shown.
- Manual: upload invalid JSON -> error shown.
- Manual: upload non-json -> error shown.
