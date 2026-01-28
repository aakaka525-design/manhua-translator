# Scraper UA Sync Design

Date: 2026-01-27
Project: manhua
Scope: Scraper frontend UA sync + payload wiring

## 1. Background
The scraper UI now supports a fixed User-Agent (UA) to reduce repeated Cloudflare challenges. Users asked for a simple way to reuse the current browser UA without overwriting their custom value.

## 2. Goals
- Provide a one-click "Use current browser UA" action.
- Auto-fill UA only when the field is empty and fixed UA is enabled.
- Avoid overriding user-supplied UA values.
- Keep server API unchanged (still uses `user_agent`).

## 3. Non-Goals
- No server-side UA inference or detection.
- No new persistence format beyond the existing state store.
- No change to HTTP-mode behavior.

## 4. UX/Behavior
- Add a small button next to the UA input: "Use current browser UA".
- If fixed UA is enabled and the field is empty, auto-fill with `navigator.userAgent` once.
- Never overwrite a non-empty UA unless the user explicitly clicks the button.
- If `navigator.userAgent` is unavailable, silently skip and keep current value.

## 5. Data Flow
- UI state holds `lockUserAgent` and `userAgent`.
- `getPayload()` includes `user_agent` only when `lockUserAgent` is true.
- No backend changes required; payload already supports `user_agent`.

## 6. Error Handling
- If UA cannot be read, keep the existing value and show no error.
- Button is disabled only if the setting is not enabled (optional).

## 7. Testing
- Manual: enable fixed UA, clear input, load page -> auto-filled.
- Manual: type custom UA, reload -> preserved, no overwrite.
- Manual: click sync button -> value replaced with browser UA.
- Integration: verify payload includes `user_agent` only when fixed UA is enabled.

## 8. Rollout
- Frontend-only change; rebuild `frontend` and redeploy static assets.
