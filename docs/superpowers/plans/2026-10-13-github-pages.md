# GitHub Pages online acceptance Implementation Plan

> **For agentic workers:** Use subagent-driven-development for the bounded exporter task; the main agent owns browser integration and deployment. User has approved GitHub Pages and requested direct execution.

**Goal:** Publish the existing nine-chapter resource hall at the repository's GitHub Pages URL, with usable browsing, literal full-text search, source traceability, and no local server dependency.

**Architecture:** Reuse the existing renderer, sanitization, content and metadata. Export static JSON (and gzip copies), actual HTML entry points for all chapter routes, and browser-side search shards. Keep the Flask application working unchanged in local mode. Static preview uses verified cached PDF copies when explicitly exported, otherwise clear official-original links; never claim that missing originals are hosted.

**Tech Stack:** Python export command, native ES modules, unittest/Node, Playwright CLI, GitHub Actions/Pages.

## Approved boundaries and prerequisites

- [x] Pages enabled in workflow mode; expected host is `https://tuz1206.github.io/airworthiness/` (not yet deployed).
- [x] Administrator added `feat/offline-resource-hall` to the `github-pages` environment branch allowlist; main retained. Verified through GitHub API, no protection bypass or merge.
- [x] Continue the existing clean feature checkout; no new worktree requested. Baseline commit `aa698cd`, prior full suite 240 passed.
- [x] No legal text, hashes, source IDs, glossary evidence or professional review states may change. No AI/Neo4j, custom domain, secret exposure, or new public tunnel.

## 1. Static export (isolated worker)

Files: create `src/airworthiness/static_export.py`, `tests/test_static_export.py`.

- [x] Write failing tests for missing export module, nine chapter entry points, safe base paths/output directories, JSON/gzip equality, no secrets/cache/database copied, and unchanged document text/review states.
- [x] Implement `export_site(root, output, base_path='/airworthiness', include_originals=False)` and CLI `python -m airworthiness.static_export --root . --output output/pages/airworthiness --base-path /airworthiness`.
- [x] Contract: `data/overview.json`, `data/quality.json`, `data/resources.json` (`{items:[public records]}`), `data/chapters/chNN.json`, `data/documents/CHNN-SNNN.json`, `data/search/chNN.json` (`[{source_id,search_text,plain}]`). All JSON gets a byte-equivalent `.gz` companion.
- [x] Export `index.html`, `quality/index.html`, `chapters/chNN/index.html`, `.nojekyll`, safe 404 page, and static JS/CSS only. Add HTML meta `airworthiness-mode=static` and `airworthiness-base=/airworthiness` to the rendered existing template. Prefix root links/assets and use slash-ended directory routes so reload/deep links work.
- [x] Documents always have `original_available=false`, `originals=[]`, `original_url=''`. Optional verified static copies use `originals/CHNN-SNNN/0.pdf` (or corresponding index) and `static_originals` entries; keep server originals separate. Cap each optional PDF at 20 MiB; over-limit/unavailable files use official links. Do not publish entire cache or arbitrary files.
- [x] Export metadata and build manifest includes counts, timestamp, source commit if available, original count; only write into a new/empty destination, no recursive deletion.
- [x] Run `python -m unittest tests.test_static_export -v`; worker recorded red/green evidence; main independently reran all 21 exporter tests successfully.

## 2. Browser static adapter (main agent)

Files: create `hall-static.js`, `tests/test_static_frontend.py`; modify `hall-core.js`, `hall-app.js`, `hall-home.js`, `hall-document-view.js` and narrow reader original mapping if needed.

- [x] Node regression tests first: base path idempotence, directory routes, slash/hash/query preservation, Chinese literal search, filters/pagination, invalid inputs, no arbitrary endpoint fetching. Five expected failures before implementation, then passed.
- [x] Add `sitePath` / `routePath` helpers, static-mode detection from meta, base-safe links and SPA navigation. Local routes remain unchanged; local PDF mode visually rechecked.
- [x] `staticRequest(path, basePath, signal)` serves API shapes from fixed JSON paths. Search loads chapter shards only when a nonempty query is present; no-query lists load only small resource metadata. Use gzip with browser DecompressionStream when available, plain JSON fallback, abort-safe caching and bounded parallel requests.
- [x] Search uses literal whitespace-normalized strings, not AI, SQL or regex queries; snippets retain original characters. Sort deterministically by chapter/source (not SQLite BM25). Surface network failures, never show partial search as complete.
- [x] Online labels/error text explain snapshot, first-search download and official-original fallback; static mode must not tell remote visitors to start localhost.
- [x] Preserve body anchors and sanitizer; no external arbitrary PDF iframe. Hosted static PDF paths must be exact same-origin fixed patterns; additional regression test red/green passed.

## 3. Deployment and verification

Files: create `.github/workflows/pages.yml`; modify README with actual deployment/maintenance instructions.

- [x] Workflow triggers on feature-branch push/manual dispatch, validates/tests/builds static output, uses official Pages artifact and deployment actions, minimal permissions, and `github-pages` environment. No production environment protection bypass.
- [x] Real export: 189 documents / 9 chapters / 445 files / 185,935,675 bytes, no hosted originals. Existing static preview verified desktop/mobile (390px) without horizontal overflow; literal search returned 65 results, chapter-3 filter 5, page 2 showed 21–40. Article CH02-S006 official PDF links and CH03-S001 clause 25.571 direct URL plus refresh passed; quality view passed. No JS errors; initial favicon-only 404. Final CSP shell covered by fixtures; public browser check remains below.
- [x] Run full unittest suite, node syntax checks, `git diff --check`, independent review and unchanged-data check. Push the existing feature branch without merging (publication verification below).
- [ ] Observe successful Pages deployment, fetch public home/deep links/JSON, and exercise public site in a real browser. Only then deliver the actual URL. If environment authorization remains missing, report the exact required admin step with built artifacts preserved.

### Verification before first publish

- 241 existing/reader tests passed in 379.324s, and 26 static exporter/frontend tests passed in 19.311s (267 total).
- Node syntax checks, `git diff --check`, and `git diff --exit-code -- data` passed.
- Source validation: 189 records, zero errors; existing CH04-S010 missing-date warning remains for professional verification.
- Independent frontend/workflow spec review and final code-quality review passed with no Critical/Important findings; reviewer independently passed 31 targeted tests.
- Minor follow-up: static JSON cache lives for the browser document lifetime. After a new deployment, or a malformed snapshot corrected on the server, fully reload the page to fetch new data; an in-page retry can retain old successful JSON. This does not block first publication.
