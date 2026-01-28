# Scraper Browser Channel Config Design

Date: 2026-01-27
Project: manhua
Scope: Frontend toggle for Playwright browser channel

## 1. Background
Playwright challenges persist on some Cloudflare sites. Running with the system Chrome channel can reduce challenge frequency compared to default Chromium. The UI needs a simple way to enable this.

## 2. Goals
- Provide a simple toggle: "Use Chrome channel".
- Only affect headed (non-HTTP) mode.
- Keep backend API unchanged (uses existing `browser_channel`).

## 3. Non-Goals
- No new backend endpoints.
- No multi-channel selector (edge/brave) in this iteration.

## 4. UX/Behavior
- Add a checkbox in scraper settings: "使用 Chrome 通道（推荐）".
- When enabled and `http_mode=false`, send `browser_channel=chrome`.
- When disabled or `http_mode=true`, do not send `browser_channel`.
- Display a short note: "仅有头模式生效，需已安装 Chrome".

## 5. Data Flow
- Add `useChromeChannel` to frontend state (default true).
- `getPayload()` includes `browser_channel` when enabled and in headed mode.

## 6. Error Handling
- If Chrome is not installed, Playwright will fail; surface the error to the UI.

## 7. Testing
- Manual: toggle on/off, verify payload contains `browser_channel` only in headed mode.
- Manual: run headed mode with/without Chrome installed to validate error feedback.
