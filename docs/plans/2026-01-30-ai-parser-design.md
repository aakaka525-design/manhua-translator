# AI Parser Design (Scraper)

Date: 2026-01-30
Project: manhua
Scope: URL parser with AI refinement + logging

## 1. Background
We need a universal URL parser that can extract content and metadata from arbitrary pages, not just supported manga sites. The parser should be accurate, robust across static and dynamic pages, and safe to operate with clear logging during development.

## 2. Goals
- Accept any URL and extract正文 + 元数据 (title, author, date, summary, cover, tags, content).
- Work for static and JS-rendered pages.
- Use AI to refine/complete missing fields, not to hallucinate content.
- Provide clear development logs for diagnosis.

## 3. Non-Goals
- Full site crawler or multi-page site discovery.
- Bypass or defeat anti-bot challenges.
- Persisting parsed content into the library (optional future step).

## 4. Architecture
Two-stage pipeline: rule_parse -> ai_refine.

### 4.1 Fetch
- Try HTTP fetch first.
- If content is empty or parsing confidence is low, retry using headless browser.
- Normalize HTML (strip scripts, remove boilerplate if needed).

### 4.2 Rule Parse
Use Readability/JSON-LD/meta tags and CSS heuristics to extract:
- title, author, date, summary, cover_url
- content_text and paragraph list
- tags/keywords if present

### 4.3 AI Refine
- Only if fields are missing or low-confidence.
- AI input is a trimmed DOM snippet (title block + main content block + meta/JSON-LD).
- AI outputs only missing fields with a confidence score.
- Never generate content not present in HTML.

## 5. Data Schema
Return `ContentMeta` with source + confidence per field.

ContentMeta
- url, site, title, author, published_at, summary
- cover_url
- content_text (string)
- paragraphs (string[])
- tags (string[])
- source_map: { field: "rule" | "ai" }
- confidence_map: { field: number }
- warnings: string[]

## 6. API
`POST /api/v1/parser/parse`
Request:
```
{ "url": "...", "mode": "auto|http|headless", "site_hint": "..." }
```
Response:
```
{ content: ContentMeta, warnings: [] }
```

## 7. Frontend
- Add a "URL 解析" subpage in the scraper module.
- Input field + Parse button.
- Render results: title, cover, summary, paragraphs.
- Buttons: Copy JSON / Copy text.

## 8. Logging (Development)
Add a dedicated logger `parser` -> `logs/YYYYMMDD_parser.log`.
Log events:
- fetch_start / fetch_end: url domain, mode, status, size, duration
- rule_parse: fields found, missing list, paragraph count, confidence
- ai_refine: model, token usage (if available), refined fields
- normalize: final source_map and confidence_map summary
Optional: `PARSE_DEBUG=1` to log small snippets (1-2 paragraphs).

## 9. Error Handling
- Invalid URL -> 400 with clear message.
- Fetch failure -> 502 with root cause.
- AI failure -> fallback to rule result + warning.

## 10. Testing
- Manual: parse static blog/news page.
- Manual: parse SPA content (headless mode).
- Manual: verify missing fields are filled by AI and flagged by source_map.
