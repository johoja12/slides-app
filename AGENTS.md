# Slides app

This is the authoritative source checkout for the private slide library. It was extracted from `home-mon/scripts/slides`; make app changes here. Keep `CLAUDE.md` for Claude Code.

## Working rules

- Read `README.md` before changing or deploying the app. Preserve existing unrelated work.
- Use conventional commit messages and commit completed, tested changes. Never force-push.
- This repository is public. Never commit presentations, credentials, `.env`, session/share databases, bearer URLs, real account exports, browser profiles, local agent settings or machine-specific infrastructure documentation. `.env.example` and proxy examples contain placeholders only.
- Migration or source edits do not implicitly authorize unrelated infrastructure changes. Deploy only within the user's requested scope; preserve the deployed library, secrets, state and Caddy volumes.
- The deployed installation is separate from this checkout. This extraction does not move customer files, rotate credentials, reset sessions, revoke shares or redeploy the service.

## App invariants

- Flask/Gunicorn serve a login-protected catalog behind Caddy HTTPS. PPTX previews use LibreOffice and Poppler.
- Public token links grant access to one deck only, never the catalog or neighboring decks. Check expiry/revocation on every asset/preview request.
- Preserve existing share-copy secrets, token hashes, old share URLs and additive SQLite migrations. Never log bearer URLs, passwords or cookies.
- Keep CSRF, login throttling, secure cookies, traversal/symlink rejection and friendly status-preserving error pages intact.
- Library originals stay read-only; generated previews belong in the state/cache directory. Do not execute presentation scripts during file inspection or server-side conversion.
- Use existing modification timestamps, not metadata rewrite or upload times, for date sorting. Preserve search filtering and expanded folders when sorting.
- Changes to copied public/proxy error pages must stay consistent with application errors; proxy examples must not introduce bearer-URL access logs.

## UI and UX

- Use semantic HTML5 with polished, deliberately styled controls that fit the app's visual design. Avoid unstyled browser-default boxes, dropdowns and widgets in user-facing flows.
- Prefer clear button groups, segmented controls and thoughtfully designed forms. Preserve native semantics, keyboard operation, visible focus, accessible names and selected/pressed states.
- Design for desktop and mobile with comfortable touch targets, useful empty/loading/error states and reduced-motion support. Verify changed controls in a real browser at both sizes.

## Validation commands

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python verify_features.py
.venv/bin/python verify_ui.py
.venv/bin/python -m py_compile app.py pptx_preview.py library_store.py library_features.py slide_content.py set-password.py refresh-thumbnails.py
# Validate Compose without printing any resolved secrets:
docker compose --env-file .env.example config --quiet
```

Use a temporary fixture library/config/database for tests; `verify.py` does this automatically. Test UI changes in a browser on desktop and mobile. Verify authentication, scoped share access, original downloads and meaningful changed behavior. Rebuild the image only when needed; mounted template/static changes can use a scoped graceful worker reload when deployment is requested.

## Roadmap

Follow-up features are tracked as GitHub issues. Do not implement the roadmap as part of repository migration. Keep issues focused, with acceptance criteria and prerequisites; prefer favorites, tags and thumbnails first, then version history.
