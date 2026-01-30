# Parser List Recognition Design

Date: 2026-01-30
Status: Approved

## Context
The current URL parser extracts article-like metadata and content. When a URL points to a list page (catalog/collection), users need list behavior similar to the site catalog, while clearly distinguishing recognized sites from unrecognized ones.

## Goals
- Detect list pages and return a list of items (title/url/cover).
- Clearly distinguish recognized sites vs unrecognized sites.
- For recognized sites, reuse existing scraper catalog rules so items are downloadable.
- For unrecognized sites, provide list-only results (no chapter download) with warnings.

## Non-Goals
- Auto-download items from a list page.
- Full crawler coverage for arbitrary sites.
- Building a universal chapter parser for unrecognized sites.

## Recognition Strategy
- Parse `url.host` and compare with known site mapping (toongod, mangaforfree).
- If the host matches a known site or a provided base_url, set `recognized=true` and `site`.
- Otherwise set `recognized=false` and return generic list parsing results.

## API Contract (New)
`POST /api/v1/parser/list`

Request:
```json
{
  "url": "https://example.com/list",
  "mode": "http"
}
```

Response:
```json
{
  "page_type": "list",
  "recognized": true,
  "site": "toongod",
  "downloadable": true,
  "items": [
    {"id": "slug", "title": "Title", "url": "...", "cover_url": "..."}
  ],
  "warnings": []
}
```

## Parsing Behavior
### Recognized
- Derive `base_url` from the input URL.
- Map URL path/query to scraper catalog parameters when possible.
- Use existing `engine.list_catalog(...)` and return results with `downloadable=true`.
- If mapping fails, return `recognized=true` with `downloadable=false` and warnings.

### Unrecognized
- Use BeautifulSoup to extract candidate list items:
  - Collect anchor links on the same host.
  - Prefer links with image + text (card-like structures).
  - De-duplicate by normalized URL.
  - Extract `title` from link text/alt and `cover_url` from the nearest image.
- Return `downloadable=false` and warnings indicating generic parsing.

## UI/UX
- In the URL parser view, show a badge: "recognized" or "unrecognized".
- When `page_type=list`, render items as cards (same style as search results).
- Clicking a card uses existing scraper flows to fetch chapters when `downloadable=true`.
- For `downloadable=false`, keep the list display but disable download actions and show a hint.

## Error Handling & Logging
- Log recognition decision, list parsing type, and item counts to the parser log.
- Return warnings for fallback parsing or mapping failures.

## Verification
- Recognized site list URL returns `recognized=true` and items are downloadable.
- Unrecognized list URL returns `recognized=false` with items rendered and downloads disabled.
