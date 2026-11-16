# Slides provide content; the app provides the player

Create presentations for the slide library using its shared player. Do not embed a separate toolbar, counter, thumbnail drawer, fullscreen UI or keyboard/touch navigation handlers. The application supplies these controls for authenticated viewers, public shares and historical revisions. Preview the deck through the app when reviewing navigation.

## Simple decks

Use one semantic section per slide. The player supplies navigation automatically:

```html
<section data-slide data-title="Introduction"><h1>Introduction</h1></section>
<section data-slide data-title="Results"><h1>Results</h1></section>
```

Provide responsive content styles. A plain document without sections is a single page. For animations or custom layout, use the versioned content adapter below.

## Animated decks

Publish `window.slidesDeck` after loading the content. A minimal adapter is:

```html
<main data-slides-stage id="stage"></main>
<script>
const pages = [{title: 'Introduction'}, {title: 'Results'}];
let index = 0, step = 0;
function render() {
  // Render content for index/step into #stage. Do not render player controls.
  history.replaceState(null, '', `#${index + 1}.${step}`);
  dispatchEvent(new Event('slides-change'));
}
window.slidesDeck = {
  version: 1,
  titles: pages.map(page => page.title),
  thumbnails: ['assets/slide-1.png', 'assets/slide-2.png'],
  getState: () => ({index, count: pages.length, step, steps: 2}),
  go(n) { index = n; step = 0; render(); },
  next() {
    if (step < 1) step++;
    else { index = Math.min(pages.length - 1, index + 1); step = 0; }
    render();
  },
  previous() {
    if (step > 0) step--;
    else index = Math.max(0, index - 1);
    render();
  },
  replay() { step = 0; render(); },
};
render();
</script>
```

`index` is zero-based and `count` is the total number of presentation slides. `step` is zero-based and `steps` includes the initial state of the current slide. Never use animation build counts as the presentation count. Index/count are required integers; step/steps default to 0/1. During asynchronous initialization count can be zero; dispatch `slides-change` when ready.

Required methods are `getState()` and `go(index)`. Optional `next()` and `previous()` implement animation-aware navigation; the player otherwise advances by slide. Optional `replay()`, `play()` (toggle playback), `pause()` and `sources()` expose animation/source actions. Return `playing: true/false` in state for playback status. The player pauses playback when opening thumbnails if `pause()` is provided. Keep source dialogs content-only and accessible.

Optional `resize({top, bottom, width, height})` receives the usable viewport and toolbar insets, including after rotation/fullscreen. Without it, an element marked `data-slides-stage` is positioned inside the shared toolbars. Avoid fixed assumptions about screen size or navigation-bar heights. The simple-section adapter reserves toolbar space in the document flow.

Use plain-text titles and relative thumbnail paths. Keep thumbnails in the presentation bundle so revision and share scopes apply to them. Capture useful static previews with animations disabled; do not include credentials, notes, private admin screens or remote bearer URLs. Missing images fall back to numbered, titled cards so slide jumps remain available.

`slides-change` tells the player to refresh state; the app also polls for compatibility. Read and restore the initial URL fragment in your content adapter if deep links should preserve animation builds. The app owns position messages to presenter tools: never send notes or other private data over those channels.

## Existing decks

The library adapts its legacy canvas `slides`/`idx`/`go` convention and the older `policyDeck` API to the same player. These adapters preserve existing animation behavior while hiding old controls. New decks must use the documented content API rather than copy legacy player code. Preserve original files and publish a new immutable revision when changing a presentation; private deck contents never belong in this public app repository.

## Giving these rules to an app or agent

Repository agents read `AGENTS.md`, which points to this guide. External tools do not discover repository instructions automatically. Give them the public `/help` page or the plain Markdown at `/help/authoring.md` as part of their task, system instructions or integration context. A working content-only starter is available at `/help/starter.html`.

Tell the tool to create content for the app-owned shared player, expose `window.slidesDeck` version 1 for animations (or use `[data-slide]` sections), and omit custom navigation controls. Ask it to keep slide totals separate from animation steps and supply relative assets and thumbnails. Loading the deck in the app supplies the standard player; arbitrary JavaScript navigation cannot be inferred automatically.

## Review and publishing

Package the top-level HTML file with its relative images, styles, scripts and fonts. Bundle thumbnail images with the same presentation; the starter uses numbered cards until thumbnails are supplied. Preview through the app and check a small phone, landscape and desktop. Test Next through every animation build, previous/replay, first/last slide jumps, thumbnail selection and keyboard operation. Opening thumbnails must not advance the underlying presentation.

Use the authenticated upload flow to create a deck or publish a new immutable revision. This public guide does not grant upload or library access. Keep earlier revisions and original files intact; never include private notes, credentials or account exports in a presentation bundle. Shared presentation downloads contain the original presentation content, so do not embed material that should remain private to the presenter.

## HTML and PowerPoint animations

The content API controls animation inside an HTML presentation. A PowerPoint preview in the library is static. Native PowerPoint animation export is a separate conversion step: it maps explicit animation instructions to existing editable PPTX objects and downloads a separate animated file. It cannot reconstruct independent objects from a flattened screenshot or infer arbitrary canvas/JavaScript motion.

Use the Animated PPTX editor, HTML annotations or a versioned animation plan to bind effects to exact objects. Missing, ambiguous or stale mappings must be corrected before export. Keep the source PPTX unchanged and check the exported animation in desktop PowerPoint Slide Show; a static preview does not prove animation playback.
