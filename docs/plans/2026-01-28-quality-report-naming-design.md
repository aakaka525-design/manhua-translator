# Quality Report Naming With Source Design

Date: 2026-01-28
Project: manhua
Scope: Include source info in quality report filenames while keeping task_id for uniqueness

## 1. Goal
Make quality report filenames reflect the source (series/chapter/page) and still remain unique by appending the task_id.

## 2. Decision
- Use **source + task_id** in the filename.
- Source is derived from `TaskContext.image_path`:
  - Prefer the path segment after `data/raw/` if present.
  - Use the **last 3 segments** (series / chapter / filename).
  - Strip file extension.
  - Sanitize into a safe slug (lowercase, keep `a-z0-9_-`, collapse others to `_`).
  - Truncate slug to a safe length if needed.

## 3. Filename Format
```
<source_slug>__<task_id>.json
```

Example:
```
data/raw/wireless-onahole/chapter-71-raw/17.jpg
-> wireless-onahole__chapter-71-raw__17__<task_id>.json
```

## 4. Non-Goals
- Changing report content schema.
- Creating nested directories per series/chapter.
- Backfilling old report names.

## 5. Testing
- Add a unit test to ensure filename contains the source slug and task_id.
