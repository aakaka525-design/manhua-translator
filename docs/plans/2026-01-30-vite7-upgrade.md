# Vite 7 Dependency Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Align Vite 7 with compatible plugin versions so `npm install` and `npm run build` succeed on Node 20.

**Architecture:** Upgrade `@vitejs/plugin-vue` to a Vite 7 compatible major version, refresh the lockfile, and verify build output. Keep other plugins unless they fail peer checks.

**Tech Stack:** Vite 7, @vitejs/plugin-vue 6, vite-plugin-pwa 1.2.0, vite-plugin-compression 0.5.1, npm.

---

### Task 1: Confirm current Vite state and install behavior

**Files:**
- Modify: none

**Step 1: Check current installed Vite version**

Run (in `frontend/`):

```bash
node -p "require('./node_modules/vite/package.json').version" || true
```

Expected: If Vite is still 5.x, note that upgrade is pending.

**Step 2: Run install to see current behavior**

Run (in `frontend/`): `npm install`
Expected: If Vite is 5.x, install succeeds. If Vite is 7.x with plugin-vue 4.x, expect ERESOLVE.

---

### Task 2: Upgrade Vite 7 and @vitejs/plugin-vue to compatible versions

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

**Step 1: Update dev dependency**

Set `vite` to `^7.3.1` and `@vitejs/plugin-vue` to `^6.0.3` in `frontend/package.json`.

**Step 2: Reinstall dependencies**

Run (in `frontend/`): `npm install`
Expected: PASS

---

### Task 3: Verify build

**Files:**
- Modify: none

**Step 1: Run production build**

Run (in `frontend/`): `npm run build`
Expected: PASS (no unresolved import errors for @fontsource/*)

---

### Task 4: Verify tests (optional)

**Step 1: Run pytest from venv**

Run (repo root): `.venv/bin/pytest`
Expected: PASS

---

### Task 5: Commit

**Step 1: Commit (only if user requests)**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: align plugin-vue with Vite 7"
```
