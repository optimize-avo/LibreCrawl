# LibreCrawl UI Redesign v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port optimize-dashboard's visual design language (dark neutral palette, teal accent, Inter typography, glass surfaces, animated border-glow, ambient background) to LibreCrawl's six Jinja templates. Zero functional changes — every `id`, `data-*`, `onclick`, and JS-target selector stays identical so no JS handler needs to be rewritten.

**Architecture:** Add Tailwind 4 as a standalone CLI build step (`@tailwindcss/cli`). A single `web/static/css/tokens.css` defines CSS custom properties as the source of truth. The Tailwind config maps each token to a utility class name byte-compatible with optimize-dashboard (`bg-card`, `text-ink`, `border-hairline`, etc.). Templates use a mix of Tailwind utilities + a small set of utility CSS classes for the four signature effects (glass, rail, border-glow, ambient background). Inter font self-hosted as woff2 in `web/static/fonts/`. Layout restructured from horizontal-top to left-rail + top-context-bar on every page.

**Tech Stack:** Tailwind 4 + `@tailwindcss/cli`, Jinja2 (no change), vanilla JS (no functional change), Inter woff2 (self-hosted). No new runtime dependencies; only one new dev dependency (`tailwindcss`).

**Branch:** `design-v2` off `main`. All commits live here. `main` is not touched.

---

## Global Constraints

- Working directory: `/Users/admin/Documents/GitHub/LibreCrawl`.
- Branch must be `design-v2`. Never commit to `main`.
- No changes to `main.py`, `src/**`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `start-librecrawl.sh`'s logic (only add an optional CSS build step call).
- All JS files (`app.js`, `dashboard.js`, `settings.js`, `column-resize.js`, `plugin-loader.js`, `incremental_poller.js`, `virtual-scroller.js`) untouched. `visualization.js` gets only a cytoscape theme color edit; behavior untouched.
- Every existing `id`, `data-*`, `onclick`, and JS `getElementById`/`querySelector` target must remain in the DOM with the same identifier. Add new wrappers/classes around them; do not rename or remove them.
- Tailwind 4 must be compiled to `web/static/css/tw.css` before the Flask app serves any page. Documented build step: `npm run build:css` in `web/`.
- All colors must come from `web/static/css/tokens.css`. No literal hex/rgb/hsl in component templates or other CSS files (matches optimize-dashboard's enforced rule).
- Self-hosted Inter: woff2 only, weights 300/400/500/600/700. License file `web/static/fonts/LICENSE-inter.md` must be present (SIL OFL 1.1).
- Google Fonts `<link>` removed from every template.
- Commit after each task with a Conventional Commits prefix (`feat:`, `chore:`, `docs:`, `style:`).

---

## File Structure

### New
- `package.json` — npm dev deps + build scripts
- `tailwind.config.js` — token → utility mapping (handled via @theme in tw-input.css instead)
- `web/static/css/tokens.css` — single source of truth (CSS custom properties)
- `web/static/css/tw-input.css` — Tailwind input (`@import "tailwindcss"; @import "./tokens.css";`)
- `web/static/css/components.css` — small utilities for the four signature effects (glass, rail, border-glow, ambient) + a few page-specific helpers
- `web/static/css/tw.css` — Tailwind compiled output (gitignored, build artifact)
- `web/static/fonts/inter-latin-300.woff2`
- `web/static/fonts/inter-latin-400.woff2`
- `web/static/fonts/inter-latin-500.woff2`
- `web/static/fonts/inter-latin-600.woff2`
- `web/static/fonts/inter-latin-700.woff2`
- `web/static/fonts/LICENSE-inter.md`
- `web/templates/partials/_rail.html`
- `web/templates/partials/_topbar.html`
- `docs/superpowers/specs/2026-07-24-ui-redesign-v2-design.md` — design spec
- `docs/superpowers/plans/2026-07-24-ui-redesign-v2.md` — this plan

### Modified
- `web/templates/index.html` — wrap in shell, restyle
- `web/templates/dashboard.html` — restyle
- `web/templates/login.html` — restyle
- `web/templates/register.html` — restyle
- `web/templates/debug_memory.html` — restyle
- `web/templates/verification_result.html` — restyle
- `web/static/js/visualization.js` — cytoscape theme colors only
- `README.md` — add "Rebuilding CSS" section
- `start-librecrawl.sh` — call `npm run build:css` before launching
- `.gitignore` — add `node_modules/`, `web/static/css/tw.css`

### Removed
- `web/static/css/styles.css` — replaced by `tokens.css` + `components.css` + Tailwind utilities

---

## Task 1: Bootstrap branch, Tailwind 4, and design tokens

**Files:**
- Create: `package.json`, `.gitignore`, `web/static/css/tokens.css`, `web/static/css/tw-input.css`, `web/static/css/components.css`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `web/static/css/tw.css` (build artifact). All later tasks consume Tailwind utilities (via `tw.css`) and the four signature-effect classes defined in `components.css`.

- [ ] **Step 1: Create the branch from `main`**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
git checkout main
git pull origin main
git checkout -b design-v2
```

Expected: branch `design-v2` created, `git status` clean.

- [ ] **Step 2: Update `.gitignore`**

Append to `/Users/admin/Documents/GitHub/LibreCrawl/.gitignore`:

```
node_modules/
web/static/css/tw.css
```

- [ ] **Step 3: Create `package.json`**

Create `/Users/admin/Documents/GitHub/LibreCrawl/package.json`:

```json
{
  "name": "librecrawl",
  "private": true,
  "version": "0.0.0",
  "scripts": {
    "build:css": "tailwindcss -i ./web/static/css/tw-input.css -o ./web/static/css/tw.css --minify",
    "watch:css": "tailwindcss -i ./web/static/css/tw-input.css -o ./web/static/css/tw.css --watch"
  },
  "devDependencies": {
    "tailwindcss": "^4.1.0",
    "@tailwindcss/cli": "^4.1.0"
  }
}
```

- [ ] **Step 4: Install dev deps**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
npm install
```

Expected: `node_modules/` created, `tailwindcss` and `@tailwindcss/cli` installed. `npx tailwindcss --help` runs.

- [ ] **Step 5: Create `web/static/css/tokens.css`**

Create `/Users/admin/Documents/GitHub/LibreCrawl/web/static/css/tokens.css`:

```css
:root {
  /* Backgrounds / surfaces — neutral base */
  --bg: #0f0f0f;
  --bg-rail: #0b0b0b;
  --card: #161616;
  --panel: #141414;
  --panel-2: #1a1a1a;
  --muted: #1c1c1c;
  --surface-active: rgba(255, 255, 255, 0.06);
  --surface-hover: rgba(255, 255, 255, 0.03);

  /* Borders */
  --border-hairline: rgba(0, 194, 184, 0.12);
  --border-functional: rgba(255, 255, 255, 0.4);
  --border-line: rgba(255, 255, 255, 0.06);

  /* Text */
  --ink: #f0f0f0;
  --fg-secondary: rgba(255, 255, 255, 0.87);
  --fg-muted: rgba(255, 255, 255, 0.5);
  --fg-disabled: rgba(255, 255, 255, 0.25);
  --dim: #7c7c7c;
  --faint: #4e4e4e;

  /* Accent — teal */
  --primary: #00c2b8;
  --primary-hover: #00d9cd;
  --primary-active: #00a89f;
  --primary-fg: #052b28;
  --ring: #00c2b8;

  /* Semantic */
  --success: #22c07a;
  --warning: #f59e0b;
  --error: #ef4444;
  --destructive: #ff6a5e;

  /* Glass */
  --bg-glass: rgba(20, 28, 27, 0.45);
  --bg-glass-hover: rgba(20, 28, 27, 0.55);
  --blur-glass: blur(24px) saturate(1.3);

  /* Type */
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
```

- [ ] **Step 6: Create `web/static/css/tw-input.css`**

Create `/Users/admin/Documents/GitHub/LibreCrawl/web/static/css/tw-input.css`:

```css
@import "tailwindcss";
@import "./tokens.css";
@import "./components.css";

@theme {
  --color-bg: var(--bg);
  --color-bg-rail: var(--bg-rail);
  --color-card: var(--card);
  --color-panel: var(--panel);
  --color-panel-2: var(--panel-2);
  --color-muted: var(--muted);
  --color-border-hairline: var(--border-hairline);
  --color-border-functional: var(--border-functional);
  --color-border-line: var(--border-line);
  --color-ink: var(--ink);
  --color-fg-secondary: var(--fg-secondary);
  --color-fg-muted: var(--fg-muted);
  --color-fg-disabled: var(--fg-disabled);
  --color-dim: var(--dim);
  --color-faint: var(--faint);
  --color-primary: var(--primary);
  --color-primary-hover: var(--primary-hover);
  --color-primary-active: var(--primary-active);
  --color-primary-fg: var(--primary-fg);
  --color-ring: var(--ring);
  --color-success: var(--success);
  --color-warning: var(--warning);
  --color-error: var(--error);
  --color-destructive: var(--destructive);

  --font-sans: var(--font-sans);
}
```

- [ ] **Step 7: Create `web/static/css/components.css` (signature effects)**

Create `/Users/admin/Documents/GitHub/LibreCrawl/web/static/css/components.css`:

```css
/* Inter — self-hosted */
@font-face {
  font-family: 'Inter';
  src: url('/static/fonts/inter-latin-300.woff2') format('woff2');
  font-weight: 300; font-style: normal; font-display: swap;
}
@font-face {
  font-family: 'Inter';
  src: url('/static/fonts/inter-latin-400.woff2') format('woff2');
  font-weight: 400; font-style: normal; font-display: swap;
}
@font-face {
  font-family: 'Inter';
  src: url('/static/fonts/inter-latin-500.woff2') format('woff2');
  font-weight: 500; font-style: normal; font-display: swap;
}
@font-face {
  font-family: 'Inter';
  src: url('/static/fonts/inter-latin-600.woff2') format('woff2');
  font-weight: 600; font-style: normal; font-display: swap;
}
@font-face {
  font-family: 'Inter';
  src: url('/static/fonts/inter-latin-700.woff2') format('woff2');
  font-weight: 700; font-style: normal; font-display: swap;
}

/* Glass surface */
.glass {
  background: var(--bg-glass);
  backdrop-filter: var(--blur-glass);
  -webkit-backdrop-filter: var(--blur-glass);
  border: 1px solid var(--border-hairline);
  border-radius: 10px;
}
@supports not (backdrop-filter: blur(1px)) {
  .glass { background: var(--card); }
}

/* Ambient background */
.canvas-ambient {
  background:
    radial-gradient(60% 50% at 15% 20%, rgba(0, 194, 184, 0.10), transparent 70%),
    radial-gradient(50% 40% at 85% 80%, rgba(0, 194, 184, 0.06), transparent 70%),
    var(--bg);
  animation: ambient-drift 20s ease-in-out infinite alternate;
}
@keyframes ambient-drift {
  0%   { background-position: 0% 0%, 100% 100%, 0 0; }
  100% { background-position: 10% 5%, 90% 95%, 0 0; }
}

/* Animated teal border-glow (CSS only) */
@property --glow-angle {
  syntax: '<angle>';
  inherits: false;
  initial-value: 0deg;
}
.glow-primary {
  position: relative;
  isolation: isolate;
}
.glow-primary::before {
  content: "";
  position: absolute;
  inset: -2px;
  border-radius: inherit;
  padding: 2px;
  background: conic-gradient(from var(--glow-angle),
    var(--primary), transparent 40%, transparent 60%, var(--primary));
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  animation: glow-spin 4s linear infinite;
  opacity: 0;
  transition: opacity 0.2s;
  z-index: -1;
  pointer-events: none;
}
.glow-primary:hover::before,
.glow-primary:focus-visible::before { opacity: 1; }
@keyframes glow-spin { to { --glow-angle: 360deg; } }

/* Sidebar rail */
.rail {
  background: var(--bg-rail);
  width: 240px;
  min-width: 240px;
  display: flex;
  flex-direction: column;
  height: 100vh;
}
@media (max-width: 1024px) {
  .rail { width: 64px; min-width: 64px; }
  .rail .rail-label { display: none; }
  .rail .rail-wordmark-text { display: none; }
}

/* Nav rows */
.nav-row {
  display: flex;
  align-items: center;
  padding: 8px 14px;
  font-size: 13px;
  letter-spacing: -0.01em;
  color: var(--dim);
  position: relative;
  border-radius: 4px;
  outline: none;
  transition: color 150ms;
}
.nav-row:hover { color: var(--ink); }
.nav-row[aria-current="page"] { color: var(--ink); }
.nav-row[aria-current="page"]::before {
  content: "";
  position: absolute;
  left: 6px;
  top: 50%;
  width: 6px;
  height: 6px;
  margin-top: -3px;
  border-radius: 9999px;
  background: var(--primary);
}
.nav-row:focus-visible {
  box-shadow: 0 0 0 2px var(--ring);
}

/* Focus ring (global) */
:where(button, a, input, select, textarea):focus-visible {
  outline: 2px solid var(--ring);
  outline-offset: 2px;
}

/* Tables */
.lc-table { width: 100%; border-collapse: separate; border-spacing: 0; }
.lc-table thead th {
  position: sticky; top: 0;
  background: var(--panel);
  color: var(--fg-muted);
  font-weight: 500; font-size: 12px;
  text-align: left;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-hairline);
}
.lc-table tbody td {
  background: var(--card);
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-line);
  font-size: 13px;
  color: var(--ink);
}
.lc-table tbody tr:hover td { background: var(--muted); }
.lc-table tbody tr.selected td {
  border-left: 2px solid var(--primary);
}

/* Tabs */
.tab {
  padding: 8px 14px;
  font-size: 13px;
  color: var(--fg-muted);
  border-bottom: 2px solid transparent;
  cursor: pointer;
  background: transparent;
}
.tab:hover { color: var(--ink); }
.tab.active {
  color: var(--ink);
  background: var(--panel-2);
  border-bottom-color: var(--primary);
}

/* Status pills */
.pill {
  display: inline-flex; align-items: center;
  padding: 2px 8px;
  font-size: 11px; font-weight: 500;
  border-radius: 9999px;
  border: 1px solid var(--border-hairline);
}
.pill-success { color: var(--success); border-color: rgba(34, 192, 122, 0.3); }
.pill-warning { color: var(--warning); border-color: rgba(245, 158, 11, 0.3); }
.pill-error   { color: var(--error);   border-color: rgba(239, 68, 68, 0.3); }
.pill-info    { color: var(--primary); border-color: var(--border-hairline); }

/* Progress bar */
.progress-track {
  height: 4px;
  background: var(--panel-2);
  border-radius: 9999px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: var(--primary);
  transition: width 200ms ease;
}
.progress-fill.active { animation: progress-pulse 1.6s ease-in-out infinite; }
@keyframes progress-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

/* Util */
[hidden], .hidden { display: none !important; }
```

- [ ] **Step 8: Build CSS once to verify**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
npm run build:css
ls -la web/static/css/tw.css
```

Expected: `tw.css` exists, >5KB.

- [ ] **Step 9: Commit**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
git add .gitignore package.json package-lock.json web/static/css/tokens.css web/static/css/tw-input.css web/static/css/components.css
git commit -m "chore: bootstrap tailwind 4 + design tokens for ui redesign v2"
```

---

## Task 2: Self-host Inter font

**Files:**
- Create: 5 woff2 files in `web/static/fonts/`, `web/static/fonts/LICENSE-inter.md`

- [ ] **Step 1: Download Inter from Fontsource**

```bash
mkdir -p /Users/admin/Documents/GitHub/LibreCrawl/web/static/fonts
cd /Users/admin/Documents/GitHub/LibreCrawl/web/static/fonts
curl -fLO https://cdn.jsdelivr.net/npm/@fontsource/inter@5.2.8/files/inter-latin-300-normal.woff2
curl -fLO https://cdn.jsdelivr.net/npm/@fontsource/inter@5.2.8/files/inter-latin-400-normal.woff2
curl -fLO https://cdn.jsdelivr.net/npm/@fontsource/inter@5.2.8/files/inter-latin-500-normal.woff2
curl -fLO https://cdn.jsdelivr.net/npm/@fontsource/inter@5.2.8/files/inter-latin-600-normal.woff2
curl -fLO https://cdn.jsdelivr.net/npm/@fontsource/inter@5.2.8/files/inter-latin-700-normal.woff2
```

Expected: 5 woff2 files, each ~15–25KB.

- [ ] **Step 2: Rename to paths referenced in `components.css`**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl/web/static/fonts
for w in 300 400 500 600 700; do
  mv inter-latin-${w}-normal.woff2 inter-latin-${w}.woff2
done
ls
```

Expected: `inter-latin-{300,400,500,600,700}.woff2`.

- [ ] **Step 3: Add SIL OFL 1.1 license**

Create `/Users/admin/Documents/GitHub/LibreCrawl/web/static/fonts/LICENSE-inter.md`:

```markdown
# Inter font license

The Inter font family in this directory is licensed under the SIL Open Font License, Version 1.1.

Copyright (c) The Inter Project Authors (https://github.com/rsms/inter)

Full license text: https://scripts.sil.org/OFL

The font files were obtained from the Fontsource mirror of Google Fonts:
https://github.com/fontsource/font-files
```

- [ ] **Step 4: Verify CSS rebuild still works**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
npm run build:css
grep -c "inter-latin" web/static/css/tw.css
```

Expected: `grep -c` returns a number ≥5 (font-face declarations preserved).

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
git add web/static/fonts/
git commit -m "chore: self-host inter font (woff2, sil ofl 1.1)"
```

---

## Task 3: Build global shell skeleton (rail + topbar partials)

**Files:**
- Create: `web/templates/partials/_rail.html`, `web/templates/partials/_topbar.html`

**Interfaces:**
- Produces Jinja partials:
  - `partials/_rail.html` — accepts no context; renders the rail with wordmark, nav links, account pocket.
  - `partials/_topbar.html` — accepts no context; renders the URL input + Start/Stop/Clear + Export dropdown placeholder, all with the exact `id`/`onclick`/`data-*` attributes that `app.js` expects.

- [ ] **Step 1: Create the rail partial**

Create `/Users/admin/Documents/GitHub/LibreCrawl/web/templates/partials/_rail.html`:

```html
<aside class="rail">
  <div class="px-4 py-4 flex items-center gap-2 border-b border-border-line">
    <a href="/" class="flex items-center gap-2 text-ink no-underline">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="10"></circle>
        <path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20"></path>
      </svg>
      <span class="rail-wordmark-text text-[15px] font-semibold tracking-tight">LibreCrawl</span>
    </a>
  </div>

  <nav class="flex-1 px-2 py-3" aria-label="Primary">
    <ul class="space-y-1 list-none m-0 p-0">
      <li>
        <a href="/" class="nav-row"
           aria-current="{{ 'page' if request and request.path == '/' else 'false' }}">
          <span class="rail-label">Crawl</span>
        </a>
      </li>
      <li>
        <a href="/dashboard" class="nav-row"
           aria-current="{{ 'page' if request and request.path.startswith('/dashboard') else 'false' }}">
          <span class="rail-label">Dashboard</span>
        </a>
      </li>
      <li>
        <a href="/settings" class="nav-row"
           aria-current="{{ 'page' if request and request.path.startswith('/settings') else 'false' }}">
          <span class="rail-label">Settings</span>
        </a>
      </li>
    </ul>
  </nav>

  <div class="px-3 py-3 border-t border-border-line flex items-center gap-2">
    <div class="size-7 rounded-full bg-panel grid place-items-center text-[11px] font-medium text-ink">
      {{ (user.username[:1] if user and user.username else 'L') | upper }}
    </div>
    <div class="rail-label text-[12px] text-fg-secondary truncate flex-1">
      {{ user.username if user and user.username else 'Guest' }}
    </div>
    <button type="button" onclick="logout()" class="rail-label text-[11px] text-fg-muted hover:text-ink bg-transparent border-0 cursor-pointer">
      Sign out
    </button>
  </div>
</aside>
```

- [ ] **Step 2: Create the topbar partial**

Create `/Users/admin/Documents/GitHub/LibreCrawl/web/templates/partials/_topbar.html`:

```html
<header class="px-6 py-3 border-b border-border-hairline" style="background: rgba(15,15,15,0.6); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);">
  <div class="flex items-center gap-3">
    <label for="urlInput" class="text-[12px] text-fg-muted shrink-0">URL to crawl</label>
    <input
      type="url"
      id="urlInput"
      class="flex-1 bg-card border border-border-functional rounded-md px-3 py-2 text-[13px] text-ink placeholder:text-fg-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring"
      placeholder="https://example.com"
      onkeypress="handleUrlKeypress(event)"
      autocomplete="off"
      spellcheck="false"
    >

    <button id="startBtn" class="glow-primary inline-flex items-center gap-1.5 bg-primary text-primary-fg px-3 py-2 rounded-md text-[13px] font-medium hover:bg-primary-hover active:bg-primary-active disabled:opacity-50 disabled:cursor-not-allowed" onclick="toggleCrawl()">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>
      Start
    </button>
    <button id="stopBtn" class="inline-flex items-center gap-1.5 bg-card text-error border border-border-hairline px-3 py-2 rounded-md text-[13px] font-medium hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed" onclick="stopCrawl()" disabled>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12"/></svg>
      Stop
    </button>
    <button id="clearBtn" class="inline-flex items-center gap-1.5 bg-card text-ink border border-border-hairline px-3 py-2 rounded-md text-[13px] font-medium hover:bg-muted" onclick="clearCrawlData()">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 7l-.867 12.142A2 2 0 0 1 16.138 21H7.862a2 2 0 0 1-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v3M4 7h16"/></svg>
      Clear
    </button>

    <div class="relative">
      <button class="inline-flex items-center gap-1.5 bg-card text-ink border border-border-hairline px-3 py-2 rounded-md text-[13px] font-medium hover:bg-muted export-dropdown-btn" onclick="toggleExportMenu()">
        Export
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
      </button>
      <div class="export-dropdown-menu hidden absolute right-0 mt-1 min-w-[200px] bg-popover border border-border-hairline rounded-md shadow-lg py-1 z-50" id="exportDropdownMenu">
        <div class="export-dropdown-item px-3 py-1.5 text-[13px] text-ink hover:bg-muted cursor-pointer" onclick="exportData('all')">Export All Data</div>
        <div class="export-dropdown-item px-3 py-1.5 text-[13px] text-ink hover:bg-muted cursor-pointer" onclick="exportData('overview')">Export: Overview</div>
        <div class="export-dropdown-item px-3 py-1.5 text-[13px] text-ink hover:bg-muted cursor-pointer" onclick="exportData('internal')">Export: Internal URLs</div>
        <div class="export-dropdown-item px-3 py-1.5 text-[13px] text-ink hover:bg-muted cursor-pointer" onclick="exportData('external')">Export: External URLs</div>
        <div class="export-dropdown-item px-3 py-1.5 text-[13px] text-ink hover:bg-muted cursor-pointer" onclick="exportData('links')">Export: Links</div>
        <div class="export-dropdown-item px-3 py-1.5 text-[13px] text-ink hover:bg-muted cursor-pointer" onclick="exportData('issues')">Export: Issues</div>
        <div class="export-dropdown-divider h-px bg-border-hairline my-1"></div>
        <div class="export-dropdown-item px-3 py-1.5 text-[13px] text-ink hover:bg-muted cursor-pointer" onclick="exportData('all_csv')">Export All (CSV)</div>
        <div class="export-dropdown-item px-3 py-1.5 text-[13px] text-ink hover:bg-muted cursor-pointer" onclick="exportData('all_json')">Export All (JSON)</div>
      </div>
    </div>

    <button id="saveCrawlBtn" class="inline-flex items-center bg-card text-ink border border-border-hairline px-3 py-2 rounded-md text-[13px] font-medium hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed" onclick="saveCrawl()" disabled>Save</button>
    <button id="loadCrawlBtn" class="inline-flex items-center bg-card text-ink border border-border-hairline px-3 py-2 rounded-md text-[13px] font-medium hover:bg-muted" onclick="loadCrawl()">Load</button>
  </div>

  <div id="progressContainer" class="hidden mt-3 flex items-center gap-3">
    <div class="progress-track flex-1"><div id="progressFill" class="progress-fill" style="width:0%"></div></div>
    <span id="progressText" class="text-[12px] text-fg-muted shrink-0">Initializing...</span>
  </div>
</header>
```

- [ ] **Step 3: Verify Jinja parses both partials**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
python3 -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader(['web/templates'])); env.get_template('partials/_rail.html'); env.get_template('partials/_topbar.html'); print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
git add web/templates/partials/
git commit -m "feat(ui): add rail + topbar partials (design tokens wired)"
```

---

## Task 4: Restyle `login.html` (quickest end-to-end validation)

**Files:**
- Modify: `web/templates/login.html`

**Interfaces:**
- Consumes: `tokens.css`, `components.css`, Tailwind utilities via `tw.css`
- Keeps: every existing `id`, `name`, `action`. JS expects `loginForm`, `username`, `password`, `errorMessage`.

- [ ] **Step 1: Read current `login.html` to preserve every form attribute**

```bash
grep -nE 'id=|name=|action=|onclick=' /Users/admin/Documents/GitHub/LibreCrawl/web/templates/login.html
```

Note every identifier. They must all survive the rewrite.

- [ ] **Step 2: Replace `login.html`**

Overwrite `/Users/admin/Documents/GitHub/LibreCrawl/web/templates/login.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sign in — LibreCrawl</title>
  <link rel="stylesheet" href="/static/css/tw.css">
</head>
<body class="font-sans bg-bg text-ink min-h-screen canvas-ambient">
  <main class="min-h-screen grid place-items-center px-4">
    <section class="glass w-full max-w-md p-8">
      <header class="mb-6 text-center">
        <a href="/" class="inline-flex items-center gap-2 text-ink no-underline">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10"></circle>
            <path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20"></path>
          </svg>
          <span class="text-[18px] font-semibold tracking-tight">LibreCrawl</span>
        </a>
        <h1 class="mt-4 text-[20px] font-semibold tracking-tight">Sign in</h1>
        <p class="mt-1 text-[13px] text-fg-muted">Crawl, audit, and explore any site.</p>
      </header>

      {% if error %}
      <div id="errorMessage" role="alert" class="mb-4 px-3 py-2 rounded-md border text-destructive text-[13px]" style="border-color: rgba(239,68,68,0.3); background: rgba(239,68,68,0.10);">{{ error }}</div>
      {% else %}
      <div id="errorMessage" role="alert" class="hidden mb-4 px-3 py-2 rounded-md border text-destructive text-[13px]" style="border-color: rgba(239,68,68,0.3); background: rgba(239,68,68,0.10);"></div>
      {% endif %}

      <form id="loginForm" method="POST" action="{{ url_for('login') }}" class="space-y-3">
        <div>
          <label for="username" class="block text-[12px] text-fg-muted mb-1">Username</label>
          <input id="username" name="username" type="text" required autocomplete="username"
                 class="w-full bg-card border border-border-functional rounded-md px-3 py-2 text-[13px] text-ink placeholder:text-fg-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring">
        </div>
        <div>
          <label for="password" class="block text-[12px] text-fg-muted mb-1">Password</label>
          <input id="password" name="password" type="password" required autocomplete="current-password"
                 class="w-full bg-card border border-border-functional rounded-md px-3 py-2 text-[13px] text-ink placeholder:text-fg-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring">
        </div>

        <button type="submit" class="glow-primary w-full bg-primary text-primary-fg px-3 py-2 rounded-md text-[13px] font-medium hover:bg-primary-hover active:bg-primary-active">
          Sign in
        </button>
      </form>

      <footer class="mt-6 flex items-center justify-between text-[12px] text-fg-muted">
        {% if not registration_disabled %}
        <a href="{{ url_for('register') }}" class="hover:text-ink">Create account</a>
        {% else %}
        <span></span>
        {% endif %}
        {% if not guest_disabled %}
        <a href="{{ url_for('guest_login') }}" class="hover:text-ink">Continue as guest</a>
        {% endif %}
      </footer>
    </section>
  </main>
</body>
</html>
```

- [ ] **Step 3: Rebuild CSS**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
npm run build:css
```

- [ ] **Step 4: Manually verify the login page**

Start the Flask app: `python3 main.py`. Open `http://localhost:5000/login`. Confirm:
- Dark canvas with subtle teal ambient blobs.
- Glass card centered, wordmark + "Sign in" heading.
- Username + password fields with teal focus ring.
- Primary "Sign in" button with glow on hover.
- Footer links render correctly.
- Submit the form with wrong creds → error pill appears with destructive color.
- Confirm `view-source:` shows the same `id="loginForm"`, `name="username"`, `name="password"`, `id="errorMessage"`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
git add web/templates/login.html
git commit -m "style(login): apply design v2 tokens (glass + ambient + teal)"
```

- [ ] **Step 6: Self-check — every original id still present**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
grep -cE 'id="loginForm"|name="username"|name="password"|id="errorMessage"|id="username"|id="password"' web/templates/login.html
```

Expected: ≥6.

---

## Task 5: Restyle `register.html`

**Files:**
- Modify: `web/templates/register.html`

**Interfaces:**
- Keeps: every existing `id`, `name`, `action`. JS expects `registerForm`, `username`, `email`, `password`, `confirm_password`, `errorMessage`.

- [ ] **Step 1: Read current `register.html` to preserve every form attribute**

```bash
grep -nE 'id=|name=|action=|onclick=' /Users/admin/Documents/GitHub/LibreCrawl/web/templates/register.html
```

- [ ] **Step 2: Replace `register.html`**

Overwrite `/Users/admin/Documents/GitHub/LibreCrawl/web/templates/register.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Create account — LibreCrawl</title>
  <link rel="stylesheet" href="/static/css/tw.css">
</head>
<body class="font-sans bg-bg text-ink min-h-screen canvas-ambient">
  <main class="min-h-screen grid place-items-center px-4">
    <section class="glass w-full max-w-md p-8">
      <header class="mb-6 text-center">
        <a href="/" class="inline-flex items-center gap-2 text-ink no-underline">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10"></circle>
            <path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20"></path>
          </svg>
          <span class="text-[18px] font-semibold tracking-tight">LibreCrawl</span>
        </a>
        <h1 class="mt-4 text-[20px] font-semibold tracking-tight">Create account</h1>
        <p class="mt-1 text-[13px] text-fg-muted">Free forever. No card required.</p>
      </header>

      {% if error %}
      <div id="errorMessage" role="alert" class="mb-4 px-3 py-2 rounded-md border text-destructive text-[13px]" style="border-color: rgba(239,68,68,0.3); background: rgba(239,68,68,0.10);">{{ error }}</div>
      {% else %}
      <div id="errorMessage" role="alert" class="hidden mb-4 px-3 py-2 rounded-md border text-destructive text-[13px]" style="border-color: rgba(239,68,68,0.3); background: rgba(239,68,68,0.10);"></div>
      {% endif %}

      <form id="registerForm" method="POST" action="{{ url_for('register') }}" class="space-y-3">
        <div>
          <label for="username" class="block text-[12px] text-fg-muted mb-1">Username</label>
          <input id="username" name="username" type="text" required minlength="3" autocomplete="username"
                 class="w-full bg-card border border-border-functional rounded-md px-3 py-2 text-[13px] text-ink placeholder:text-fg-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring">
        </div>
        <div>
          <label for="email" class="block text-[12px] text-fg-muted mb-1">Email</label>
          <input id="email" name="email" type="email" required autocomplete="email"
                 class="w-full bg-card border border-border-functional rounded-md px-3 py-2 text-[13px] text-ink placeholder:text-fg-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring">
        </div>
        <div>
          <label for="password" class="block text-[12px] text-fg-muted mb-1">Password</label>
          <input id="password" name="password" type="password" required minlength="8" autocomplete="new-password"
                 class="w-full bg-card border border-border-functional rounded-md px-3 py-2 text-[13px] text-ink placeholder:text-fg-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring">
        </div>
        <div>
          <label for="confirm_password" class="block text-[12px] text-fg-muted mb-1">Confirm password</label>
          <input id="confirm_password" name="confirm_password" type="password" required minlength="8" autocomplete="new-password"
                 class="w-full bg-card border border-border-functional rounded-md px-3 py-2 text-[13px] text-ink placeholder:text-fg-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring">
        </div>

        <button type="submit" class="glow-primary w-full bg-primary text-primary-fg px-3 py-2 rounded-md text-[13px] font-medium hover:bg-primary-hover active:bg-primary-active">
          Create account
        </button>
      </form>

      <footer class="mt-6 text-center text-[12px] text-fg-muted">
        <a href="{{ url_for('login') }}" class="hover:text-ink">Already have an account? Sign in</a>
      </footer>
    </section>
  </main>
</body>
</html>
```

- [ ] **Step 3: Rebuild CSS**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
npm run build:css
```

- [ ] **Step 4: Manually verify**

Start Flask. Open `/register`. Submit empty form → browser-native validation triggers. Submit with mismatched passwords → server error pill appears.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
git add web/templates/register.html
git commit -m "style(register): apply design v2 tokens"
```

- [ ] **Step 6: Self-check — every original id still present**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
grep -cE 'id="registerForm"|name="username"|name="email"|name="password"|name="confirm_password"|id="errorMessage"|id="username"|id="email"|id="password"|id="confirm_password"' web/templates/register.html
```

Expected: ≥10.

---

## Task 6: Restyle `verification_result.html`

**Files:**
- Modify: `web/templates/verification_result.html`

**Interfaces:**
- Keeps: `success` boolean, `message` string.

- [ ] **Step 1: Read the current template to preserve context variables**

```bash
grep -nE '\{%\s*(if|else|endif)|\{\{\s*[a-zA-Z_]+\s*\}\}' /Users/admin/Documents/GitHub/LibreCrawl/web/templates/verification_result.html
```

- [ ] **Step 2: Replace `verification_result.html`**

Overwrite `/Users/admin/Documents/GitHub/LibreCrawl/web/templates/verification_result.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ 'Email verified' if success else 'Verification' }} — LibreCrawl</title>
  <link rel="stylesheet" href="/static/css/tw.css">
</head>
<body class="font-sans bg-bg text-ink min-h-screen canvas-ambient">
  <main class="min-h-screen grid place-items-center px-4">
    <section class="glass w-full max-w-md p-8 text-center">
      {% if success %}
        <div class="mx-auto mb-4 size-12 rounded-full grid place-items-center text-success" style="background: rgba(34,192,122,0.15);" aria-hidden="true">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
        </div>
        <h1 class="text-[18px] font-semibold tracking-tight">Email verified</h1>
        <p class="mt-1 text-[13px] text-fg-muted">{{ message or 'Your email has been verified. You can now sign in.' }}</p>
        <a href="{{ url_for('login') }}" class="glow-primary mt-6 inline-flex items-center bg-primary text-primary-fg px-4 py-2 rounded-md text-[13px] font-medium hover:bg-primary-hover">
          Continue to sign in
        </a>
      {% else %}
        <div class="mx-auto mb-4 size-12 rounded-full grid place-items-center text-error" style="background: rgba(239,68,68,0.15);" aria-hidden="true">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </div>
        <h1 class="text-[18px] font-semibold tracking-tight">Verification failed</h1>
        <p class="mt-1 text-[13px] text-fg-muted">{{ message or 'The verification link is invalid or has expired.' }}</p>
        <a href="{{ url_for('login') }}" class="mt-6 inline-flex items-center bg-card text-ink border border-border-hairline px-4 py-2 rounded-md text-[13px] font-medium hover:bg-muted">
          Back to sign in
        </a>
      {% endif %}
    </section>
  </main>
</body>
</html>
```

- [ ] **Step 3: Rebuild CSS + manually verify**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
npm run build:css
```

Open both verification routes. Confirm icon, color, and CTA render correctly.

- [ ] **Step 4: Commit**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
git add web/templates/verification_result.html
git commit -m "style(verification): apply design v2 tokens"
```

---

## Task 7: Restyle `dashboard.html`

**Files:**
- Modify: `web/templates/dashboard.html`

**Interfaces:**
- Consumes: rail partial from Task 3.
- Keeps: every `id`/`data-*` that `dashboard.js` queries (table rows, action buttons, status pills).

- [ ] **Step 1: Read `dashboard.js` to enumerate required selectors**

```bash
grep -nE 'getElementById\(|querySelector\(|querySelectorAll\(|dataset\.' /Users/admin/Documents/GitHub/LibreCrawl/web/static/js/dashboard.js | head -40
```

Capture every `id`, class, and `data-*` attribute the JS touches. These MUST survive.

- [ ] **Step 2: Replace `dashboard.html`**

Overwrite `/Users/admin/Documents/GitHub/LibreCrawl/web/templates/dashboard.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Saved crawls — LibreCrawl</title>
  <link rel="stylesheet" href="/static/css/tw.css">
</head>
<body class="font-sans bg-bg text-ink min-h-screen canvas-ambient">
  <div class="flex min-h-screen">
    {% include 'partials/_rail.html' %}

    <main class="flex-1 min-w-0 flex flex-col">
      <header class="px-6 py-4 border-b border-border-hairline flex items-center justify-between">
        <div>
          <h1 class="text-[18px] font-semibold tracking-tight">Saved crawls</h1>
          <p id="crawlCount" class="text-[12px] text-fg-muted mt-0.5">{{ crawls|length }} {{ 'crawl' if crawls|length == 1 else 'crawls' }}</p>
        </div>
        <div class="flex items-center gap-2">
          <input id="searchInput" type="search" placeholder="Search…"
                 class="bg-card border border-border-functional rounded-md px-3 py-2 text-[13px] text-ink placeholder:text-fg-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring">
          <button id="newCrawlBtn" class="glow-primary inline-flex items-center bg-primary text-primary-fg px-3 py-2 rounded-md text-[13px] font-medium hover:bg-primary-hover" onclick="window.location='/'">
            New crawl
          </button>
        </div>
      </header>

      <section class="flex-1 px-6 py-6 overflow-auto">
        {% if crawls %}
        <div class="glass overflow-hidden">
          <table class="lc-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>URL</th>
                <th>Pages</th>
                <th>Status</th>
                <th>Last opened</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody id="crawlsTableBody">
              {% for crawl in crawls %}
              <tr data-crawl-id="{{ crawl.id }}" data-crawl-name="{{ crawl.name }}">
                <td class="font-medium">{{ crawl.name }}</td>
                <td class="text-fg-secondary truncate max-w-[280px]">{{ crawl.url }}</td>
                <td class="text-fg-muted">{{ crawl.page_count }}</td>
                <td>
                  <span class="pill pill-{{ 'success' if crawl.status == 'completed' else 'info' if crawl.status == 'in_progress' else 'warning' if crawl.status == 'paused' else 'error' }}">
                    {{ crawl.status }}
                  </span>
                </td>
                <td class="text-fg-muted">{{ crawl.last_opened_at or '—' }}</td>
                <td class="text-right">
                  <button class="open-btn inline-flex items-center bg-card text-ink border border-border-hairline px-2.5 py-1.5 rounded-md text-[12px] hover:bg-muted" data-crawl-id="{{ crawl.id }}">Open</button>
                  <button class="delete-btn inline-flex items-center bg-card text-error border px-2.5 py-1.5 rounded-md text-[12px] hover:bg-muted ml-1" data-crawl-id="{{ crawl.id }}" style="border-color: rgba(239,68,68,0.3);">Delete</button>
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
        {% else %}
        <div class="glass p-12 text-center">
          <p class="text-[14px] text-fg-muted">No saved crawls yet.</p>
          <a href="/" class="glow-primary mt-4 inline-flex items-center bg-primary text-primary-fg px-3 py-2 rounded-md text-[13px] font-medium hover:bg-primary-hover">
            Start your first crawl
          </a>
        </div>
        {% endif %}
      </section>
    </main>
  </div>
</body>
</html>
```

- [ ] **Step 3: Rebuild CSS**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
npm run build:css
```

- [ ] **Step 4: Manually verify**

Start Flask. Open `/dashboard`. Confirm:
- Left rail renders.
- Top header with title + count + search + "New crawl" primary.
- Table renders with rows; status pills colored per state.
- Empty state: glass card with CTA.
- Click "Open" → navigates to the crawl.
- Click "Delete" → prompts + removes row.

- [ ] **Step 5: Self-check — every JS-targeted selector still present**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
grep -cE 'id="crawlsTableBody"|id="searchInput"|id="newCrawlBtn"|id="crawlCount"|class="open-btn"|class="delete-btn"|data-crawl-id' web/templates/dashboard.html
```

Expected: ≥7.

- [ ] **Step 6: Commit**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
git add web/templates/dashboard.html
git commit -m "style(dashboard): apply design v2 tokens + rail"
```

---

## Task 8: Restyle `index.html` — shell, topbar, tabs, table

**Files:**
- Modify: `web/templates/index.html`

**Interfaces:**
- Consumes: rail partial, topbar partial.
- Keeps: every `id`/`data-*`/`onclick` `app.js` expects. **This is the biggest screen and the one with most JS coupling — proceed carefully.**

- [ ] **Step 1: Enumerate every selector `app.js` touches**

```bash
grep -nEo 'getElementById\("[a-zA-Z_-]+"\)|querySelector\("[^"]+"\)|querySelectorAll\("[^"]+"\)|dataset\.[a-zA-Z]+' /Users/admin/Documents/GitHub/LibreCrawl/web/static/js/app.js | sort -u > /tmp/appjs-selectors.txt
wc -l /tmp/appjs-selectors.txt
head -80 /tmp/appjs-selectors.txt
```

Keep this list open while editing.

- [ ] **Step 2: Replace `index.html` with the restyled shell**

Overwrite `/Users/admin/Documents/GitHub/LibreCrawl/web/templates/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LibreCrawl — SEO Spider</title>
  <link rel="stylesheet" href="/static/css/tw.css">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.28.1/cytoscape.min.js" defer></script>
</head>
<body class="font-sans bg-bg text-ink min-h-screen canvas-ambient">
  <div class="flex min-h-screen">
    {% include 'partials/_rail.html' %}

    <main class="flex-1 min-w-0 flex flex-col">
      {% include 'partials/_topbar.html' %}

      <section class="flex-1 min-h-0 flex">
        <div class="flex-1 min-w-0 flex flex-col">
          <nav id="tabsContainer" class="px-6 pt-3 border-b border-border-hairline flex items-center gap-1" aria-label="Result tabs">
            <button class="tab active" data-tab="overview" role="tab" aria-selected="true">Overview</button>
            <button class="tab" data-tab="internal" role="tab" aria-selected="false">Internal</button>
            <button class="tab" data-tab="external" role="tab" aria-selected="false">External</button>
            <button class="tab" data-tab="images" role="tab" aria-selected="false">Images</button>
            <button class="tab" data-tab="links" role="tab" aria-selected="false">Links</button>
            <button class="tab" data-tab="issues" role="tab" aria-selected="false">Issues</button>
            <button class="tab" data-tab="graph" role="tab" aria-selected="false">Graph</button>
          </nav>

          <div class="flex-1 min-h-0 overflow-auto">
            <div id="tab-overview" class="tab-panel p-6" role="tabpanel">
              <div id="overviewStats" class="grid grid-cols-2 md:grid-cols-4 gap-3"></div>
              <div id="overviewContent" class="mt-6"></div>
            </div>

            <div id="tab-internal" class="tab-panel hidden p-6" role="tabpanel">
              <div id="internalTableContainer"></div>
            </div>

            <div id="tab-external" class="tab-panel hidden p-6" role="tabpanel">
              <div id="externalTableContainer"></div>
            </div>

            <div id="tab-images" class="tab-panel hidden p-6" role="tabpanel">
              <div id="imagesTableContainer"></div>
            </div>

            <div id="tab-links" class="tab-panel hidden p-6" role="tabpanel">
              <div id="linksTableContainer"></div>
            </div>

            <div id="tab-issues" class="tab-panel hidden p-6" role="tabpanel">
              <div id="issuesTableContainer"></div>
            </div>

            <div id="tab-graph" class="tab-panel hidden p-6" role="tabpanel">
              <div id="cy" class="glass" style="height: 600px; position: relative;">
                <div class="graph-placeholder absolute inset-0 grid place-items-center text-fg-muted text-[13px]">
                  Run a crawl to see the link graph.
                </div>
              </div>
            </div>
          </div>
        </div>

        <aside id="detailPanel" class="hidden w-[360px] shrink-0 border-l border-border-hairline bg-bg-rail overflow-auto">
          <div id="detailPanelContent"></div>
        </aside>
      </section>

      <footer id="statusBar" class="px-6 py-2 border-t border-border-hairline bg-bg-rail text-[12px] text-fg-muted flex items-center gap-4">
        <span id="statusMessage">Ready</span>
        <span class="ml-auto" id="statusCounts"></span>
      </footer>
    </main>
  </div>

  <div id="toastContainer" class="fixed bottom-4 right-4 flex flex-col gap-2 z-50"></div>

  <span id="userInfo" class="hidden"></span>
</body>
</html>
```

**Important:** All `id`s `app.js` queries (`urlInput`, `startBtn`, `stopBtn`, `clearBtn`, `saveCrawlBtn`, `loadCrawlBtn`, `exportDropdownMenu`, `progressContainer`, `progressFill`, `progressText`, `tabsContainer`, `cy`, `detailPanel`, `detailPanelContent`, `statusBar`, `statusMessage`, `statusCounts`, `toastContainer`, `userInfo`) live either in the partials or directly in this template. **Re-grep `/tmp/appjs-selectors.txt` against this rewritten file and confirm every id is present.**

- [ ] **Step 3: Rebuild CSS**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
npm run build:css
```

- [ ] **Step 4: Verify every `app.js` selector still resolves**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
missing=0
while IFS= read -r sel; do
  id=$(echo "$sel" | grep -oE '"[a-zA-Z_-]+"' | tr -d '"' | head -1)
  [ -z "$id" ] && continue
  if ! grep -q "id=\"$id\"" web/templates/index.html web/templates/partials/_topbar.html web/templates/partials/_rail.html 2>/dev/null; then
    echo "MISSING: $id"
    missing=$((missing+1))
  fi
done < /tmp/appjs-selectors.txt
echo "missing: $missing"
```

Expected: `missing: 0`.

- [ ] **Step 5: Manually verify the full crawl flow**

Start Flask. Open `/`. Confirm:
- Rail renders on left with logo + nav + account pocket.
- Top context bar with URL input, Start, Stop, Clear, Export, Save, Load.
- Tab strip with 7 tabs.
- Click each tab → content area updates.
- Enter URL → click Start → progress bar fills with teal; tab switches to Overview; stats appear in cards.
- Click an Internal URL row → right detail panel opens.
- Click Graph tab → cytoscape canvas shows link graph.
- Click Export → dropdown opens.
- Click Stop / Clear / Load / Sign out → all behaviors intact.

- [ ] **Step 6: Self-check — Google Fonts link removed**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
grep -c 'fonts.googleapis.com' web/templates/index.html
```

Expected: 0.

- [ ] **Step 7: Commit**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
git add web/templates/index.html
git commit -m "style(index): apply design v2 shell + tabs + tables + rail"
```

---

## Task 9: Restyle `debug_memory.html`

**Files:**
- Modify: `web/templates/debug_memory.html`

**Interfaces:**
- Keeps: any data attributes or class names the existing page reads (it renders server-side stats; minimal JS coupling expected). Still — read it first.

- [ ] **Step 1: Inspect the template**

```bash
cat /Users/admin/Documents/GitHub/LibreCrawl/web/templates/debug_memory.html | head -60
```

- [ ] **Step 2: Replace `debug_memory.html`**

Overwrite `/Users/admin/Documents/GitHub/LibreCrawl/web/templates/debug_memory.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Memory — LibreCrawl debug</title>
  <link rel="stylesheet" href="/static/css/tw.css">
</head>
<body class="font-sans bg-bg text-ink min-h-screen canvas-ambient">
  <div class="flex min-h-screen">
    {% include 'partials/_rail.html' %}

    <main class="flex-1 min-w-0 flex flex-col">
      <header class="px-6 py-4 border-b border-border-hairline">
        <h1 class="text-[18px] font-semibold tracking-tight">Runtime memory</h1>
        <p class="text-[12px] text-fg-muted mt-0.5">Process and queue snapshot</p>
      </header>

      <section id="memoryStats" class="flex-1 px-6 py-6 overflow-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        {% block content %}{{ content | safe }}{% endblock %}
      </section>
    </main>
  </div>
</body>
</html>
```

**Note:** If the existing template does not pass a `content` variable from the route, the `{% block content %}{{ content | safe }}{% endblock %}` will render empty. In that case, do NOT use a block; instead, paste the original body markup verbatim inside `<section>` and restyle only the surrounding chrome. Match the existing render contract.

- [ ] **Step 3: Rebuild CSS + verify**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
npm run build:css
```

Open `/debug/memory`. Confirm stat cards render with the dark neutral palette, teal accents, tabular numerals.

- [ ] **Step 4: Commit**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
git add web/templates/debug_memory.html
git commit -m "style(debug): apply design v2 tokens + rail"
```

---

## Task 10: Restyle cytoscape graph theme (`visualization.js`)

**Files:**
- Modify: `web/static/js/visualization.js` (cytoscape theme object only)

**Interfaces:**
- Keeps: every function signature, every event handler. Only the color values inside the cytoscape `style` array change.

- [ ] **Step 1: Edit the cytoscape style block**

In `/Users/admin/Documents/GitHub/LibreCrawl/web/static/js/visualization.js`, replace the `style: [...]` array passed to `cytoscape({...})` with:

```javascript
        style: [
            {
                selector: 'node',
                style: {
                    'background-color': 'data(color)',
                    'label': 'data(label)',
                    'width': 'data(size)',
                    'height': 'data(size)',
                    'font-size': '12px',
                    'color': '#f0f0f0',
                    'text-outline-color': '#0f0f0f',
                    'text-outline-width': 2,
                    'text-valign': 'bottom',
                    'text-halign': 'center',
                    'text-margin-y': 5,
                    'overlay-opacity': 0,
                    'border-width': 2,
                    'border-color': '#1a1a1a'
                }
            },
            {
                selector: 'node:selected',
                style: {
                    'border-color': '#00c2b8',
                    'border-width': 3,
                    'overlay-opacity': 0
                }
            },
            {
                selector: 'edge',
                style: {
                    'width': 2,
                    'line-color': 'rgba(0, 194, 184, 0.45)',
                    'target-arrow-color': 'rgba(0, 194, 184, 0.45)',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier',
                    'arrow-scale': 1,
                    'opacity': 0.7
                }
            },
            {
                selector: 'edge:selected',
                style: {
                    'line-color': '#00c2b8',
                    'target-arrow-color': '#00c2b8',
                    'width': 3,
                    'opacity': 1
                }
            }
        ]
```

- [ ] **Step 2: Verify JS still loads without syntax errors**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
node --check web/static/js/visualization.js && echo "syntax ok"
```

Expected: prints `syntax ok`.

- [ ] **Step 3: Manually verify the graph tab**

Start Flask, run a small crawl, switch to the Graph tab. Confirm nodes/edges render in dark theme with teal accents.

- [ ] **Step 4: Commit**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
git add web/static/js/visualization.js
git commit -m "style(graph): restyle cytoscape theme to dark + teal"
```

---

## Task 11: Delete old `styles.css`, update README, wire CSS build into start script

**Files:**
- Delete: `web/static/css/styles.css`
- Modify: `README.md`, `start-librecrawl.sh`

- [ ] **Step 1: Remove the old stylesheet**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
git rm web/static/css/styles.css
```

- [ ] **Step 2: Update `start-librecrawl.sh` to build CSS before launching**

Edit `/Users/admin/Documents/GitHub/LibreCrawl/start-librecrawl.sh`. Immediately after the shebang and before the existing logic, add:

```bash
# Build Tailwind CSS for UI redesign v2
if [ -f package.json ]; then
  echo "Building Tailwind CSS..."
  npm run build:css || echo "Warning: CSS build failed; continuing with last build (if any)."
fi
```

- [ ] **Step 3: Add a "Rebuilding CSS" section to `README.md`**

Append to `/Users/admin/Documents/GitHub/LibreCrawl/README.md`:

```markdown
## Rebuilding CSS

This project uses [Tailwind CSS 4](https://tailwindcss.com/) compiled via the standalone `@tailwindcss/cli`. The source files live at:

- `web/static/css/tokens.css` — design tokens (colors, spacing, type) — **single source of truth**
- `web/static/css/tw-input.css` — Tailwind input
- `web/static/css/components.css` — signature-effect utilities (glass, rail, glow, ambient)
- `web/static/css/tw.css` — compiled output, gitignored

To rebuild CSS once:

```bash
npm run build:css
```

To watch during development:

```bash
npm run watch:css
```

`start-librecrawl.sh` rebuilds CSS automatically before launching. Inter is self-hosted under `web/static/fonts/` (SIL OFL 1.1, see `LICENSE-inter.md`).
```

- [ ] **Step 4: Commit**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
git add -A
git status
git commit -m "chore: remove legacy styles.css, wire css build into start script, document in readme"
```

---

## Task 12: Final regression sweep

**Files:** none modified; pure verification.

- [ ] **Step 1: Confirm no `fonts.googleapis.com` references anywhere**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
grep -rn 'fonts.googleapis.com' web/templates/ || echo "clean"
```

Expected: `clean`.

- [ ] **Step 2: Confirm no Python file changed**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
git diff main --stat -- '*.py' 'src/'
```

Expected: empty output.

- [ ] **Step 3: Confirm every JS file is unmodified except `visualization.js`**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
git diff main --stat -- 'web/static/js/*.js'
```

Expected: only `web/static/js/visualization.js` shows changes.

- [ ] **Step 4: Confirm no `id` was dropped from `index.html`**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
git show main:web/templates/index.html | grep -hEo 'id="[^"]+"' | sort -u > /tmp/index-ids-old.txt
grep -hEo 'id="[^"]+"' web/templates/index.html web/templates/partials/_topbar.html web/templates/partials/_rail.html | sort -u > /tmp/index-ids-new.txt
diff /tmp/index-ids-old.txt /tmp/index-ids-new.txt || echo "diff shown"
```

Expected: only additions (new ids), never removals.

- [ ] **Step 5: Build final CSS, start the app, full click-through**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
npm run build:css
./start-librecrawl.sh
```

Manually exercise every screen:
- `/login` — sign in
- `/` — start a small crawl, switch every tab, click a row, open graph, export CSV, save crawl
- `/dashboard` — open a saved crawl, delete one
- `/debug/memory` — view stats
- `/verification_result/success` and `.../fail` (or whatever routes exist)
- Sign out — back to `/login`

- [ ] **Step 6: Lighthouse spot-check**

Open Chrome DevTools → Lighthouse → run on `/`. Confirm:
- Performance score reasonable (≥80).
- Accessibility score ≥90.
- No broken font loads (Network panel: all `inter-latin-*.woff2` return 200).

- [ ] **Step 7: Tag the branch + push**

```bash
cd /Users/admin/Documents/GitHub/LibreCrawl
git tag design-v2-final
git push origin design-v2
```

---

## Self-Review

**1. Spec coverage:**
- §3 design tokens → Task 1 (tokens.css)
- §4 token → utility mapping → Task 1 (tw-input.css @theme block)
- §5.1 glass → Task 1 (components.css `.glass`) + Tasks 4/5/6/7/8 (consumed)
- §5.2 sidebar rail → Task 1 (components.css `.rail`, `.nav-row`) + Task 3 (partial) + Tasks 7/8/9 (consumed)
- §5.3 border-glow → Task 1 (components.css `.glow-primary`) + Tasks 3/4/5 (Start, auth submit)
- §5.4 ambient → Task 1 (components.css `.canvas-ambient`) + every page
- §6 layout per page → Tasks 4 (login), 5 (register), 6 (verification), 7 (dashboard), 8 (index), 9 (debug)
- §7 file-level change list → matches exactly
- §8 implementation order → matches task order (1→12)
- §9 verification → Task 12
- §10 risks (cytoscape JS edit) → Task 10
- §10 risks (Google Fonts removal) → Task 2 + Task 8 Step 6 + Task 12 Step 1
- §10 risks (JS selectors preserved) → Task 8 Step 4

**2. Placeholder scan:** No TBD/TODO/"implement later" anywhere. Every step has either code, a command, or an explicit verification.

**3. Type consistency:** Token names referenced consistently (`--bg`, `--card`, `--primary`, `--ink`, `--dim`, etc.) across `tokens.css`, `components.css`, `tw-input.css`, and every template.

---

## Plan Summary

Plan complete and saved to `docs/superpowers/plans/2026-07-24-ui-redesign-v2.md`.

**Execution approach:** Subagent-Driven (selected). Invoking `superpowers:subagent-driven-development` to dispatch a fresh subagent per task.