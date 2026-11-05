# Roadmap

The roadmap is implemented. GitHub issues hold the original acceptance criteria; README.md documents supported formats, limits and behavior. Favorites shipped first; the remaining features share additive state storage and immutable revisions.

| Order | Feature | Goal |
|---|---|---|
| 1 | [Favorites and pinning](https://github.com/johoja12/slides-app/issues/1) | Keep frequently used presentations easy to find. |
| 2 | [Tags and filters](https://github.com/johoja12/slides-app/issues/2) | Organize decks by product, customer, audience and event. |
| 3 | [Library thumbnails](https://github.com/johoja12/slides-app/issues/3) | Recognize presentations before opening them. |
| 4 | [Version history](https://github.com/johoja12/slides-app/issues/4) | Retain revisions and make share-link version behavior explicit. |
| 5 | [Full-text search](https://github.com/johoja12/slides-app/issues/5) | Find slide content beyond folder titles and descriptions. |
| 6 | [Drag-and-drop uploads](https://github.com/johoja12/slides-app/issues/6) | Add safe presentation bundles and pair equivalent formats. |
| 7 | [Share activity](https://github.com/johoja12/slides-app/issues/7) | Show aggregate opens and last-opened dates without logging bearer URLs. |
| 8 | [Presenter view](https://github.com/johoja12/slides-app/issues/8) | Keep notes, timing and next-slide previews private to the presenter. |

Existing source files, authentication, share scopes, original downloads and read-only library access must remain protected. Changes that require writable originals or new data storage need an explicit design in the relevant issue.

The authenticated UI is now maintained as Vue 3/TypeScript components with a locked Vite build; see [frontend migration issue #9](https://github.com/johoja12/slides-app/issues/9) and the frontend development section in README.md. Public presentation URLs and the Flask/SQLite backend remain stable.
