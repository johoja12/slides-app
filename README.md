# Slides app

A self-hosted, private slide library for HTML, PowerPoint and PDF presentations. The source was extracted from a larger infrastructure repository into this standalone project.

## Features

- Searchable, collapsible presentation folders with local-time modification dates.
- Name and date-modified sorting, remembered in the browser; filtering and expanded folders survive sorting.
- Persistent favorites, independent pins and a favorites-only library filter, with accessible sort buttons.
- Linked HTML/PPTX versions, original downloads and cached PowerPoint previews.
- Desktop/mobile presentation viewers and a slide-navigation drawer for supported canvas decks.
- Login-protected library with expiring, revocable links scoped to a single presentation.
- Search/filter/copy and bulk management of share links, preserving legacy URLs.
- Friendly error pages with matching reverse-proxy fallbacks.

## Run locally

Requires Docker Compose. The image includes LibreOffice, Poppler and compatible fonts for PPTX previews.

```bash
cp .env.example .env
mkdir -p library secrets state caddy-data caddy-config
# The application image runs as UID 1024 and GID 100.
# Grant that identity read access to library/secrets and write access to state.
sudo chown 1024:100 secrets state
docker compose build library
docker compose run --rm --no-deps --user 1024:100 \
  -v "$PWD/secrets:/secrets:rw" -v "$PWD/set-password.py:/app/set-password.py:ro" \
  library python /app/set-password.py
docker compose up -d
```

The initial username is `admin`; the password is prompted privately and must contain at least 14 characters. The default URL is `https://localhost:8447`. Caddy uses an internal CA; trust its root certificate in your browser for local development. Secure cookies require HTTPS. `.env.example` defines the hostname, bind address, port, public origin and trusted hosts. Set all consistently for a real domain; do not use wildcard trusted hosts.

For builds on a separate machine, build and transfer the image with `docker save`/`docker load` and use `docker compose up -d --no-build` on the target. Copy source/config files separately when using the supplied read-only application mounts. Do not overwrite existing runtime folders. Existing production settings remain outside this public repository.

## Add and present a deck

Create `library/<deck-name>/` and copy the complete HTML deck with relative assets, or add PPTX/PDF files. The catalog discovers folders on refresh. Use `index.html` for a share link's default HTML presentation. Hidden paths and symlinks are rejected. Keep filenames stable to preserve existing URLs.

Optional `metadata.json`:

```json
{"title":"Example presentation", "description":"A concise description", "formats":{"html":"index.html","pptx":"example.pptx"}}
```

Explicit `formats` pair matching HTML/PPTX files; single unambiguous candidates can be paired automatically. Downloading PPTX returns the original file. Previews are disposable cache files under `state/pptx`, keyed by original file identity; never replace source files with rendered derivatives.

Modification dates use the latest deck/supporting-asset modification time, excluding metadata, hidden files and symlinks. Preserve timestamps when copying decks if you want the original dates retained. Sorting supports A–Z, Z–A, newest first and oldest first.

Expand a folder to use **Favorite** or **Pin to top**. Favorites and pins are independent: pins stay above other folders, with the chosen sort applied within each group. **Favorites only** combines with text search. Buttons expose their selected state to assistive technology and support keyboard activation.

Preferences belong to the current single-admin installation and persist across browsers in the state SQLite database; they never modify originals or their dates and are absent from anonymous share responses. Identity follows the folder name: removed folders disappear from the catalog, renamed folders start with no preferences, and reusing a previous name restores its saved preferences. The sort and favorites-only filter are remembered separately in each browser.

## Share links and privacy

Sign in, select an expiry and create a share link. Anyone holding that token can view files in that presentation folder without login; they cannot browse other folders or the catalog. Revoke a link to disable future requests. Downloaded copies cannot be revoked. Manage share links supports searching, filters, copying and bulk revoke/delete; only expired/revoked records can be deleted.

Back up `library`, `secrets`, `state` and the Caddy data volume privately. Preserve `share_copy_secret` in `secrets/auth.json` across password changes and upgrades. The password helper rotates the session-signing secret, invalidating existing login sessions, but preserves share-copy material. Never commit runtime data or include bearer URLs in logs, referrers or issue reports.

`npm-advanced.conf` is an optional Nginx Proxy Manager example. Replace its example hostname/upstream and install `proxy-errors/` at the configured path. Keep access logs disabled for bearer routes, preserve error status codes and forward only trusted client-IP headers. Do not expose Gunicorn directly.

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python verify.py
docker compose --env-file .env.example config --quiet
```

The verification script creates temporary dummy presentations, credentials and databases. It checks authentication, CSRF, throttling, cookies, logout replay, path/symlink rejection, scoped sharing, expiry/revocation, bulk actions, PPTX previews, original downloads, linked formats, share copying and error pages. It never accesses a real deployment.

Optional browser regression checks (synthetic HTTPS server and temporary state only):

```bash
.venv/bin/pip install playwright
.venv/bin/playwright install chromium
.venv/bin/python verify_ui.py
```

These cover favorites/pins, all sort modes, search, expanded folders, reload persistence, failed saves, keyboard controls and desktop/mobile layout. They require `openssl` and save preview screenshots under `/tmp/slides-library-{desktop,mobile}.png`.

`refresh-thumbnails.py` is an optional local helper for canvas decks exposing the supported `slides`/`go` API. It requires Playwright and a Chromium browser; run `python refresh-thumbnails.py --help` for inputs. It writes derived files locally and checks that the source file has not changed.

## Development

Read `AGENTS.md`. Keep application changes in this repository and runtime configuration outside it. Feature follow-ups and acceptance criteria live in GitHub issues; see [ROADMAP.md](ROADMAP.md).

## Tags, previews and search

Expand a folder to edit private comma-separated tags. Tags use Unicode normalization, case folding and collapsed whitespace; each deck supports up to 20 tags of 48 characters. Selected tag filters use **AND** matching and combine with folder search, favorites and sorting. Manage tags opens a searchable list with presentation counts. Choose a tag to rename it, merge it into another existing tag, or review affected presentations before deleting it. Selected tag filters stay selected after a rename; clear them with Clear filters. The library initially shows up to eight commonly used tags, with Show all for the rest. Tag identity follows the stable folder URL name; removed decks disappear from filters, retained preferences return if that name is reused, and unused tags disappear automatically. These preferences never enter shared-deck responses.

Opening previews load only near the viewport. HTML uses a static text card without executing scripts; supported canvas decks can use source-hash-verified helper PNGs. Custom/canvas decks without those assets have an explicit fallback. PPTX reuses the conversion cache, and PDF renders only its first page with Poppler. Every request checks login or its deck-scoped share grant, including fixed revision, expiry and revocation. Source changes invalidate derived previews. No server-side browser or arbitrary HTML execution is used.

**Search slide content** indexes only top-level served HTML/PPTX/PDF presentation files from each selected current revision. HTML scripts, hidden elements and note/presenter elements are excluded; PPTX reads slide XML without macros or notes; PDF uses `pdftotext`. App presenter notes, hidden files, credentials and unrelated assets are never indexed. Searches match any query word, use FTS relevance ranking, show plain-text snippets and slide/page pointers, and paginate 20 results per page. Favorites and all selected tags narrow results. HTML has a document pointer; custom canvas text built only by JavaScript cannot be extracted statically. Changed/deleted files and selected revisions invalidate old results. Work is incremental within a request budget; a large or uncached library may ask you to search again while indexing continues. Corrupt/oversized files are skipped without revealing paths or parser errors. The index stays inside the private state database.

## Version history and uploads

The migration is additive: old folders stay read-only and existing links keep their token hashes, copy secrets, expiration and revocation. A deck receives a stable internal UUID when its first snapshot is saved. New immutable revisions copy visible regular files into `state/revisions/<revision-id>/`; paired HTML/PPTX/PDF filenames, original bytes, file timestamps and a content digest are retained. Hidden files and symlinks are excluded. Nothing retroactively recovers a folder revision that was overwritten before it was snapshotted.

**Version history** lets you capture the current folder, inspect/download prior files and select a current revision without overwriting originals. A live-folder option remains for legacy decks. Selecting a revision checks the previously displayed current version to prevent stale concurrent restores. Historical URLs carry the revision in their path, preserving relative-asset scope. External filesystem edits to a live folder are visible on refresh; save a snapshot before replacing originals outside the app. Deck URL names remain stable across uploads/restores; a filesystem rename creates a different identity.

New share links explicitly choose **Follow latest** (the selected current revision or live folder) or **Fixed snapshot**. Creating a fixed link snapshots the current files, or pins the historical revision being viewed. Old links behave as Follow latest. All assets, thumbnails, previews and original downloads stay within that grant's revision. A revision missing a paired format never borrows that format from another revision. Snapshots are retained until an operator deliberately archives/removes them outside the application; there is no destructive revision-delete flow.

**Upload** accepts drag-and-drop or a file picker for HTML bundles (ZIP), PPTX and PDF. New deck names never overwrite existing ones. Choose an existing deck under **New revision** to publish a replacement; its previous live contents are snapshotted first. New content is fully validated in a bounded `state/ingestion/` staging directory and atomically published into revision storage before the database selects it. The library mount remains read-only. Concurrent publishing is serialized, and a stale expected revision is rejected. An interrupted upload leaves the selected revision intact; after a lost success response check history before retrying. A failed transaction can leave an unreferenced revision directory, which is never served or reused as a valid revision; retain it until an operator reviews storage.

Limits: 100 MB uploaded, 300 MB expanded, 1,500 bundle files, 50 selected files, 100 MB per file, UTF-8 HTML up to 8 MB. ZIP paths reject traversal, hidden files, symlinks, special files, encryption and duplicate names. PPTX rejects macros, embedded objects and external resource relationships. File signatures and HTML resource paths are validated without running presentation code. HTML may intentionally reference public HTTP(S) resources at viewing time. ZIP entry modification dates and browser-provided source file dates are retained when available; metadata creation does not change date sorting. Top-level pairing is automatic for one file per format; ambiguous formats require exact filename choices. The app authors pairing metadata instead of trusting bundle metadata.

## Share activity and presenter tools

Authenticated share management shows observed visits and last-opened local time. A visit is a GET to the share's entry URL, deduplicated per browser/share for 30 minutes. Assets, thumbnails, direct file URLs, HEAD/prefetch requests and detected bots do not add visits. Cookie deletion, blocking or unrecognized bots can affect counts: these are observed requests, not verified people or proof of reading. Only internal share IDs, totals, timestamps and short-lived hashed random visitor identifiers are stored. No IP, raw token, bearer URL or user agent is persisted. Deduplication rows expire after 30 minutes and are pruned on eligible opens; aggregate totals remain until **Reset activity** or inactive share-history deletion. Existing proxy bearer-route log suppression is unchanged.

**Presenter tools** opens a private authenticated window with current/next preview, elapsed timer and separately stored notes (one line per slide). Supported formats are the existing canvas `slides`/`go` adapter and PPTX previews. Custom HTML without that API displays a limitation and keeps its own controls; PDF uses its native viewer. Only position/count messages travel over a random per-presentation browser channel; notes never travel to audience windows, anonymous responses, search or thumbnails. These app notes are separate from any notes already embedded in an original file: sharing/downloading an original always shares its original contents.

The presenter can open/reconnect the audience, use arrow/Page keys, reset the timer and request fullscreen. The audience is clean while presenter tools are open. Reloads preserve the channel, notes and local timer; heartbeats detect disconnection. Popup blocking gives an explicit retry message. Mobile uses stacked previews and touch buttons; devices without multi-window channel support can use ordinary audience navigation. Private notes require login on every load/save and CSRF on save; no anonymous presenter endpoint exists.

Additional verification:

```bash
.venv/bin/python verify_features.py
# Real converters with no network and temporary synthetic presentations:
docker run --rm --network none --read-only --memory 1g --cpus 2 \
  --tmpfs /tmp:rw,size=768m -v "$PWD:/app:ro" -w /app \
  local/slides-library:1 python verify_rendering.py
```

The application image and read-only mounts include `library_store.py`, `library_features.py` and `slide_content.py`. When upgrading an existing Compose installation, add these module mounts from the example (or rebuild the image) and recreate only the library service. Preserve the installation's origin/trusted hosts, state, secrets, presentation and Caddy mounts. Back up the SQLite database and existing source before deploying additive migrations; do not reset runtime state.

## Frontend development

The authenticated library, uploads, version history, content search, share management, private viewer and presenter tools use **Vue 3 + TypeScript**, compiled with **Vite**. Flask still owns routing, authorization, CSRF, files, conversion and SQLite. These are Vue components mounted into existing server routes; bookmarks, public links and browser navigation keep their URLs. Login, error pages, anonymous share shells and presentation-format adapters remain independent of the private UI.

Use Node 24 (the build image is pinned) or a compatible Node version satisfying `package.json`:

```bash
npm ci --include=dev
npm run format:check      # consistent component/source formatting
npm run build             # strict Vue/TypeScript checks and production assets
npm run dev               # rebuild assets on source changes for a local backend
```

Components live in `frontend/pages/` and `frontend/components/`; shared request, preference and presentation-channel logic lives in `frontend/composables/`. The reusable controls provide consistent touch targets, focus states, pressed states, modal focus management and loading/error feedback. State belongs to Vue components; do not add imperative page scripts back into Jinja templates.

Vite writes hashed JS/CSS and a manifest to `static/ui/`, which is generated and ignored by Git. Flask reads that manifest and serves assets locally. No CDN, production Node service, client-side router or additional database is required. The Docker multi-stage build installs the locked frontend dependencies, runs the type checker/build and copies only compiled assets into the Python runtime image. The Docker context explicitly excludes runtime data and includes the frontend sources and application modules.

Private page data is JSON-encoded into an authenticated bootstrap; it is never interpreted as a Vue template or inserted as raw HTML. Authenticated page routes also return their existing page data when requested with `Accept: application/json`, letting Vue reuse current mutation endpoints and CSRF checks. Anonymous presentation responses do not contain the private bootstrap or load the application bundle. Presenter channels transmit only primitive slide positions/counts, never notes.

Build before running the existing fixture tests:

```bash
npm ci --include=dev
npm run build
.venv/bin/python verify_features.py
.venv/bin/python verify_ui.py
```

For mounted-source deployments, run the production build before copying source. Publish the new hashed assets **before** changing templates/source, retain previous hashed assets for already-open tabs, and publish the manifest with the matching release. Reload only the application workers after the files are ready. Back up current application files and the manifest first; rollback restores the matching source/templates/manifest while retaining both asset generations. This migration does not require a database migration, credential rotation or runtime-state reset.

## Native PowerPoint animations

**Animated PPTX** appears beside each PowerPoint file in the library and in its private viewer. Choose a slide, find an object by name/text/ID, add effects and set their playback order. Export downloads a separate `*-animated.pptx` and saves its plan privately under `state/motion-plans/`. Originals, modification dates, revisions and public shares stay unchanged. Cached exports under `state/motion/` are disposable and limited to 32 files. Export requires login and CSRF; public share links do not grant access to the editor or generated files. Historical editor URLs use the historical file and its paired HTML.

Supported native effects are appear/disappear, fade in/out, wipe in, fly in, zoom in, finite movement paths and scaling. Steps can start on click, with the previous group or after the previous parallel group finishes, with durations/delays in milliseconds. Movement coordinates are offsets relative to slide width/height, starting at `[0,0]`; scale values multiply the original width/height. Appear/disappear change visibility instantly; their duration reserves time before a following step. Existing timelines on affected slides require explicit replacement; timelines on other slides are retained. The library's LibreOffice previews remain static. Actual animation appearance and playback must be checked in desktop PowerPoint Slide Show; package validation and LibreOffice rendering do not prove playback fidelity.

The adapter adds PresentationML timing to **existing native PPTX objects**. It does not reconstruct objects from a flattened picture or infer arbitrary JavaScript/canvas/WebGL motion. The existing HTML-to-PPTX generator is external to this repository; its integration point is the annotation/manifest contract below. Have it keep stable unique object names, export static editable objects, then call this postprocessor. Unknown effects, missing/ambiguous targets and stale source fingerprints produce errors instead of silent substitutions. This first version does not translate general CSS keyframes, easing curves, loops, Morph, media playback or arbitrary object-trigger interactions.

### Exporter contract

A linked UTF-8 HTML file can include declarative instructions. The server reads markup without executing scripts:

```html
<section data-pptx-slide="1">
  <h1 data-pptx-shape="Heading"
      data-pptx-animation="fade-in"
      data-pptx-animation-start="click"
      data-pptx-animation-duration="0.6s"
      data-pptx-animation-delay="100ms">Example heading</h1>
</section>
```

`data-pptx-shape` matches the PPTX object's exact unique name; `data-pptx-text` alternatively matches its complete normalized text. Multi-slide files require `data-pptx-slide` on the element or an ancestor. Explicit supported `data-pptx-animation` values and the equivalent entrance/exit classes are recognized; unrelated CSS is not interpreted. Optional `data-pptx-animation-direction` is `left`, `right`, `up` or `down` for fly/wipe (the direction of travel/reveal). `data-pptx-path='[[0,0],[0.2,0]]'` supplies move points and `data-pptx-scale='[1.5,1.5]'` supplies scaling. Choose `click`, `with` or `after` for start.

For programmatic exporters, use a version 1 JSON plan:

```json
{
  "version": 1,
  "source_sha256": "SHA256_OF_THE_STATIC_PPTX",
  "replace_existing": false,
  "steps": [
    {"slide": 1, "target": {"name": "Heading"}, "effect": "fade-in", "trigger": "click", "duration_ms": 600, "delay_ms": 0},
    {"slide": 1, "target": {"id": 3}, "effect": "move", "trigger": "after", "duration_ms": 900, "path": [[0,0],[0.2,0.1]]}
  ]
}
```

A target must contain exactly one of `id`, `name` or `text`. Numeric IDs are scoped to their slide and the exact source SHA-256. The editor's **Exporter manifest / custom motion paths** panel exposes the current fingerprint and plan. Inline plans can instead be embedded in a single `<script type="application/json" id="pptx-animations">…</script>` block; they cannot be mixed with element instructions. An inline plan using only semantic name/text selectors can omit the fingerprint and is rebound after static export; numeric bindings always require one. Script contents are parsed as JSON, never evaluated.

The standalone adapter has no extra Python dependencies:

```bash
python pptx_motion.py static.pptx --inspect > objects.json
python pptx_motion.py static.pptx --manifest animation-plan.json -o animated.pptx
# Or read annotations/inline JSON from the original HTML:
python pptx_motion.py static.pptx --html index.html -o animated.pptx
.venv/bin/python verify_motion.py
```

Limits include 100 MB PPTX, 300 MB expanded package, 500 slides, 20,000 total objects, 1,000 steps, 60-second duration/delay, 64 path points within ±2 slide dimensions and scale multipliers from 0.01 to 10. Signed/macro-enabled packages and unsafe XML/ZIP structures are rejected. Source and linked-HTML fingerprints prevent stale exports. Namespace declarations used by Office compatibility attributes are preserved, and untouched ZIP parts retain their original bytes. The adapter requires a separate output path.

This implementation adapts the native timing-tree approach of [pptx-motion-lite](https://github.com/yinzige/pptx-motion-lite), under its [MIT license](third_party/pptx-motion-lite-LICENSE.txt). Research also reviewed [dom-to-pptx](https://github.com/atharva9167j/dom-to-pptx), which offers DOM/CSS animation export, and its [Reveal fragment fork](https://github.com/halobiron/dom-to-pptx). They are not runtime dependencies. The adapter follows [PresentationML animation structures](https://learn.microsoft.com/en-us/office/open-xml/presentation/working-with-animation); a postprocessor preserves compatibility with the existing external static exporter.

For mounted deployments, add the `pptx_motion.py` read-only mount from `compose.yml`, copy the module alongside the other source files and recreate only the library service. Keep the installation's origin/trusted hosts and runtime volumes. New images include the module and its third-party license. Run `verify_motion.py`, the browser checks and the real rendering test above before deployment.


## One shared presentation player

The app injects the same player into every served HTML presentation and PowerPoint preview, including anonymous shares and historical revisions. **Slides** always opens the thumbnail picker on phones and desktops, with **First slide** and **Last slide** shortcuts. Previous/Next, slide totals, replay, animation playback, sources and fullscreen use one styled control set. Unsupported optional actions stay disabled. Native legacy navigation bars are hidden once their adapter is available; originals remain read-only.

The main counter tracks presentation slides. Animation builds appear separately as steps; Next can reveal a build without changing the slide counter. Keyboard navigation runs once even when an older deck also registers key handlers. The same position contract supports private presenter tools without sending notes to audience windows.

For new decks follow [SLIDE_AUTHORING.md](SLIDE_AUTHORING.md). Use the versioned `window.slidesDeck` content API or semantic `[data-slide]` sections; do not build another player into the presentation. Legacy canvas and policy-deck APIs remain supported. A plain HTML document has one page; unrecognized custom multi-slide engines need an adapter to expose their slide structure. The app cannot infer arbitrary navigation state from custom JavaScript.

Run `.venv/bin/python verify_player.py` for synthetic browser checks covering all adapters, identical controls, animation/slide counters, small phones, landscape, desktop, thumbnail navigation, share revocation and unchanged originals.
