# Scraper Cover Proxy Design

Date: 2026-01-27
Project: manhua
Scope: Proxy + cache cover images for Cloudflare sites

## 1. Background
Cover URLs from Cloudflare-protected sites return 403 when loaded directly in the browser due to CORP and challenge rules. We need a same-origin proxy to fetch and cache images.

## 2. Goals
- Serve cover images reliably without direct cross-origin requests.
- Cache images on disk to avoid repeated fetches.
- Support Cloudflare-protected sources by falling back to Playwright.

## 3. Non-Goals
- Full image CDN or long-term cache invalidation.
- General-purpose open proxy.

## 4. Design
- New endpoint: `GET /api/v1/scraper/image` with query params:
  - `url`, `base_url`, `storage_state_path`, `user_data_dir`, `browser_channel`, `user_agent`
- Host allowlist: `toongod.org`, `mangaforfree.com`.
- Cache path: `data/cache/covers/<sha256>.ext`.
- Fetch order:
  1. HTTP fetch with cookies + referer.
  2. If 403/failed: Playwright headless fetch using storage_state or persistent profile.
- Return bytes with correct content-type.

## 5. Error Handling
- Invalid host -> 400.
- Fetch failure -> 403.
- Missing Playwright -> return 403.

## 6. Frontend
- Wrap cover URLs via `proxyImageUrl()`.
- Include profile/channel/UA params when available.

## 7. Testing
- Manual: cover loads with proxy.
- Manual: cache hit returns immediately.
- Manual: invalid host rejected.
