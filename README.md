# Slides app

A self-hosted, private slide library for HTML, PowerPoint and PDF presentations. The source was extracted from a larger infrastructure repository into this standalone project.

## Features

- Searchable, collapsible presentation folders with local-time modification dates.
- Name and date-modified sorting, remembered in the browser; filtering and expanded folders survive sorting.
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

`refresh-thumbnails.py` is an optional local helper for canvas decks exposing the supported `slides`/`go` API. It requires Playwright and a Chromium browser; run `python refresh-thumbnails.py --help` for inputs. It writes derived files locally and checks that the source file has not changed.

## Development

Read `AGENTS.md`. Keep application changes in this repository and runtime configuration outside it. Feature follow-ups and acceptance criteria live in GitHub issues; see [ROADMAP.md](ROADMAP.md).
