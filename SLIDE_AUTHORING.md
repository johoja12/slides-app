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
