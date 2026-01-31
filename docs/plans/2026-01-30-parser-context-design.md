# Parser Context Decoupling Design

Date: 2026-01-30
Status: Approved

## Context
The URL parser currently reuses the left-side scraper settings (baseUrl, mode, state file). This causes confusion and failures when a user parses a URL from a different site than the selected scraper site.

## Goals
- Decouple URL parsing and chapter loading from the left-side scraper settings.
- Derive the parser site context directly from the input URL.
- Keep the UI simple and minimal (no new inputs or toggles).
- Make "View Chapters" reliable when the parsed site is recognized.

## Non-Goals
- Adding new UI controls for parser site selection.
- Replacing existing search/catalog flows.
- Advanced cross-site scraping beyond recognized sites.

## Architecture
Introduce a parser-specific context derived from the input URL. This context is used for parser list/detail requests and for the "View Chapters" action. The left-side settings remain for normal search/catalog flows and are not used by parser actions.

### Parser Context
Derived fields:
- `base_url`: from URL origin (scheme + host)
- `host`: from URL
- `recognized`: from `/api/v1/parser/list` response
- `downloadable`: from `/api/v1/parser/list` response

Defaults for recognized sites:
- `storage_state_path` and `user_data_dir` use built-in defaults (same as initial site defaults), not user-edited left-panel values.

## Data Flow
1) User enters URL and clicks Parse.
2) Frontend derives `base_url` and stores `parser.context`.
3) Frontend calls `/api/v1/parser/list` with URL/mode.
4) If list response contains items, render list view.
5) "View Chapters" triggers a new action that calls `/api/v1/scraper/chapters` using `parser.context.base_url` and parser mode (http/headless), plus default site state paths when recognized.
6) If list response is empty, fall back to `/api/v1/parser/parse` and render detail view.

## UI/UX
- Keep the parser panel layout unchanged.
- Add a single line above results: `Parsed site: <host>`.
- Show badges for recognized/unrecognized.
- Disable "View Chapters" when `downloadable=false` and show a short hint.
- No new inputs or toggles.

## Error Handling
- Invalid URL: show error under input and stop.
- Unrecognized site: list-only display; "View Chapters" disabled.
- Chapter fetch failure: show error in the existing error slot.

## Testing
- Unit tests for parser list endpoint remain unchanged.
- Frontend tests should assert the list endpoint usage and presence of recognition badges.
- Manual: parse a recognized list URL and confirm chapters load even if left-side site differs.
