# Scraper Auth Page Design

Date: 2026-01-27
Project: manhua
Scope: Scraper "认证" subpage with zero input

## 1. Background
Mobile users need a simple way to complete Cloudflare challenges for server-side scraping without typing server URLs. A fixed auth entry point is preferred.

## 2. Goals
- Provide a one-click "认证" subpage and button.
- Zero user input for auth URL.
- Support optional server-configured override via `SCRAPER_AUTH_URL`.

## 3. Non-Goals
- Embedding remote browser via iframe.
- Automating challenge completion.

## 4. UX/Behavior
- Add a third tab: "认证".
- Add a "去认证" button inside settings.
- The auth page shows the resolved URL and a button to open it in a new tab.
- Provide simple steps and quick "检测状态 / 站点检测" actions.

## 5. API
- GET `/api/v1/scraper/auth-url`
  - Returns `SCRAPER_AUTH_URL` if configured, otherwise `${origin}/auth`.

## 6. Error Handling
- If API fails, fallback to `${origin}/auth` with a small hint.

## 7. Testing
- Manual: open auth page and verify link uses configured URL.
- Manual: fallback to `/auth` when API fails.
