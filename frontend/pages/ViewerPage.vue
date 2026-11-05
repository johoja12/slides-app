<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import type { ViewerData } from "../types";
import {
  usePresentationChannel,
  validPosition,
} from "../composables/presentation";
import type { Position } from "../composables/presentation";
import ShareComposer from "../components/ShareComposer.vue";
import UiButton from "../components/UiButton.vue";
import UiDialog from "../components/UiDialog.vue";
const props = defineProps<{ data: ViewerData }>();
const frame = ref<HTMLIFrameElement>(),
  sharing = ref(false),
  audience = ref(new URLSearchParams(location.search).get("audience") === "1"),
  popupMessage = ref("");
const param = new URLSearchParams(location.search).get("channel");
const channel = /^[a-zA-Z0-9_-]{24,80}$/.test(param || "")
  ? param!
  : crypto.randomUUID().replaceAll("-", "");
const presenterURL = computed(() => {
  const url = new URL(props.data.presenter_url, location.origin);
  url.searchParams.set("channel", channel);
  return url.href;
});
const source = props.data.source + location.hash;
const position = ref<Position>({ type: "position", index: 0, count: 0 });
const bus = usePresentationChannel(channel, (value) => {
  if (value.type === "navigate")
    frame.value?.contentWindow?.postMessage(
      { type: "slides-navigate", index: value.index },
      location.origin,
    );
  if (value.type === "hello") {
    if (validPosition(position.value)) bus.send(position.value);
    frame.value?.contentWindow?.postMessage(
      { type: "slides-request-position" },
      location.origin,
    );
  }
});
function receive(event: MessageEvent) {
  if (
    event.origin !== location.origin ||
    event.source !== frame.value?.contentWindow ||
    event.data?.type !== "slides-position"
  )
    return;
  const value = { ...event.data, type: "position" };
  if (validPosition(value)) {
    position.value = value;
    bus.send(value);
  }
}
let frameWindow: Window | null | undefined;
function syncHash() {
  try {
    history.replaceState(
      null,
      "",
      location.pathname +
        location.search +
        (frame.value?.contentWindow?.location.hash || ""),
    );
  } catch {
    /* A custom deck may have navigated off-origin. */
  }
}
function loaded() {
  try {
    frameWindow?.removeEventListener("hashchange", syncHash);
  } catch {}
  frameWindow = frame.value?.contentWindow;
  try {
    frameWindow?.addEventListener("hashchange", syncHash);
    syncHash();
  } catch {}
}
function openPresenter(event: MouseEvent) {
  const popup = window.open(presenterURL.value, "slides-presenter-" + channel);
  if (popup) {
    event.preventDefault();
    audience.value = true;
    const url = new URL(location.href);
    url.searchParams.set("channel", channel);
    url.searchParams.set("audience", "1");
    history.replaceState(null, "", url);
  } else {
    event.preventDefault();
    popupMessage.value =
      "Popup blocked. Allow popups or open Presenter tools in a new tab.";
  }
}
function formatURL(value: string | undefined) {
  if (!value) return "";
  try {
    const hash = frame.value?.contentWindow?.location.hash || "";
    return value + (/^#\d+$/.test(hash) ? hash : "");
  } catch {
    return value;
  }
}
onMounted(() => {
  document.body.classList.add("viewer-page");
  window.addEventListener("message", receive);
});
onBeforeUnmount(() => {
  window.removeEventListener("message", receive);
  frameWindow?.removeEventListener("hashchange", syncHash);
  document.body.classList.remove("viewer-page");
});
</script>
<template>
  <div class="presentation-viewer" :class="{ audience }">
    <nav v-if="!audience" aria-label="Presentation navigation">
      <a href="/" target="_top">← Back to library</a
      ><span class="viewer-title">{{ data.title }}</span>
      <div v-if="data.formats.html && data.formats.pptx" class="format-switch">
        <a
          class="format-link"
          :href="formatURL(data.formats.html)"
          :aria-current="data.active_format === 'html' ? 'page' : undefined"
          >HTML</a
        ><a
          class="format-link"
          :href="formatURL(data.formats.pptx)"
          :aria-current="data.active_format === 'pptx' ? 'page' : undefined"
          >PowerPoint</a
        ><a
          v-if="data.active_format === 'html'"
          :href="data.formats.download_pptx"
          download
          >Download PPTX ↓</a
        >
      </div>
      <a id="presenter-link" :href="presenterURL" @click="openPresenter"
        >Presenter tools ↗</a
      ><UiButton id="open-share" @click="sharing = true">Share</UiButton>
      <p v-if="popupMessage" role="status">{{ popupMessage }}</p>
    </nav>
    <iframe
      ref="frame"
      :src="source"
      :title="`${data.title} presentation`"
      allow="fullscreen"
      allowfullscreen
      @load="loaded"
    ></iframe>
  </div>
  <UiDialog v-model:open="sharing" title="Share this deck"
    ><p class="muted">
      Anyone with the link can view this deck without signing in. Choose latest
      or a fixed snapshot.
    </p>
    <ShareComposer :deck="data.name" :revision="data.revision"
  /></UiDialog>
</template>
