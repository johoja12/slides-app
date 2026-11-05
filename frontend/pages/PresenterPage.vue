<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import type { PresenterData } from "../types";
import { errorMessage, formData, request, useCsrf } from "../composables/api";
import {
  frameNavigate,
  usePresentationChannel,
  validPosition,
} from "../composables/presentation";
import AppHeader from "../components/AppHeader.vue";
import UiButton from "../components/UiButton.vue";
import UiStatus from "../components/UiStatus.vue";
const props = defineProps<{ data: PresenterData }>();
const currentFrame = ref<HTMLIFrameElement>(),
  nextFrame = ref<HTMLIFrameElement>(),
  index = ref(0),
  count = ref(0),
  lastSeen = ref(0),
  connection = ref("Open the audience window and keep this window private."),
  notes = ref(props.data.notes),
  message = ref(""),
  busy = ref(false),
  elapsed = ref(0),
  csrf = useCsrf();
const timerKey = "slides-timer-" + props.data.channel;
let started = Date.now();
try {
  started = Number(sessionStorage.getItem(timerKey)) || started;
  sessionStorage.setItem(timerKey, String(started));
} catch {}
const bus = usePresentationChannel(props.data.channel, (value) => {
  if (!validPosition(value)) return;
  index.value = value.index;
  count.value = value.count;
  lastSeen.value = Date.now();
  connection.value = "Audience connected. Notes are private to this window.";
  previews();
});
const activeNote = computed(() => notes.value.split("\n")[index.value] || "");
const timer = computed(
  () =>
    `${String(Math.floor(elapsed.value / 60)).padStart(2, "0")}:${String(elapsed.value % 60).padStart(2, "0")}`,
);
function previews() {
  frameNavigate(currentFrame.value, index.value);
  frameNavigate(
    nextFrame.value,
    Math.min(index.value + 1, Math.max(0, count.value - 1)),
  );
}
function navigate(delta: number) {
  if (props.data.supported && count.value)
    bus.send({
      type: "navigate",
      index: Math.max(0, Math.min(count.value - 1, index.value + delta)),
    });
}
function audience() {
  const url = new URL(props.data.audience, location.origin);
  url.searchParams.set("channel", props.data.channel);
  url.searchParams.set("audience", "1");
  const opened = window.open(url, "slides-audience-" + props.data.channel);
  connection.value = opened
    ? "Waiting for audience…"
    : "Popup blocked. Allow popups for this site, then click Open audience again.";
}
function resetTimer() {
  started = Date.now();
  elapsed.value = 0;
  try {
    sessionStorage.setItem(timerKey, String(started));
  } catch {}
}
function fullscreen() {
  if (document.fullscreenElement) void document.exitFullscreen();
  else
    void document.documentElement.requestFullscreen?.().catch(() => {
      connection.value = "Fullscreen is unavailable in this browser.";
    });
}
function keyboard(event: KeyboardEvent) {
  if ((event.target as Element)?.closest("input,textarea,button")) return;
  if (["ArrowRight", "PageDown", "ArrowLeft", "PageUp"].includes(event.key)) {
    event.preventDefault();
    navigate(["ArrowRight", "PageDown"].includes(event.key) ? 1 : -1);
  }
}
async function saveNotes() {
  busy.value = true;
  message.value = "Saving…";
  try {
    await request(location.href, formData({ csrf, notes: notes.value }));
    message.value = "Notes saved.";
  } catch (error) {
    message.value = errorMessage(error);
  } finally {
    busy.value = false;
  }
}
let interval: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  window.addEventListener("keydown", keyboard);
  if (!bus.supported.value)
    connection.value =
      "This browser does not support multi-window controls. Use the audience’s own navigation.";
  interval = setInterval(() => {
    elapsed.value = Math.floor((Date.now() - started) / 1000);
    if (lastSeen.value && Date.now() - lastSeen.value > 7000)
      connection.value = "Audience disconnected. Reopen it to reconnect.";
    bus.send({ type: "hello" });
  }, 1000);
});
onBeforeUnmount(() => {
  clearInterval(interval);
  window.removeEventListener("keydown", keyboard);
});
</script>
<template>
  <AppHeader />
  <div class="page-heading">
    <span class="private-badge">Private presenter view</span>
    <h1>{{ data.entry.title }}</h1>
    <p class="muted">
      Notes stay in this authenticated window. Only slide positions are
      synchronized.
    </p>
    <p v-if="!data.supported" class="muted">
      This custom HTML deck does not expose supported controls; use its own
      audience navigation.
    </p>
  </div>
  <div class="presenter-toolbar">
    <UiButton id="open-audience" variant="primary" @click="audience"
      >Open / reconnect audience</UiButton
    ><UiButton
      id="previous"
      :disabled="!data.supported || !count"
      aria-label="Previous slide"
      @click="navigate(-1)"
      >← Previous</UiButton
    ><span id="position" role="status">{{
      count ? `${index + 1} / ${count}` : "Connecting…"
    }}</span
    ><UiButton
      id="next"
      :disabled="!data.supported || !count"
      aria-label="Next slide"
      @click="navigate(1)"
      >Next →</UiButton
    ><UiButton id="full-screen" @click="fullscreen">Full screen</UiButton
    ><span id="timer" aria-label="Elapsed time">{{ timer }}</span
    ><UiButton id="reset-timer" @click="resetTimer">Reset timer</UiButton>
  </div>
  <UiStatus id="connection">{{ connection }}</UiStatus>
  <div class="presenter-previews">
    <section>
      <h2>Current slide</h2>
      <iframe
        id="current-preview"
        ref="currentFrame"
        :src="data.source"
        title="Current slide preview"
        allow="fullscreen"
        @load="previews"
      ></iframe>
    </section>
    <section>
      <h2>Next slide</h2>
      <iframe
        id="next-preview"
        ref="nextFrame"
        :src="data.source"
        title="Next slide preview"
        @load="previews"
      ></iframe>
    </section>
  </div>
  <form id="notes-form" class="card" @submit.prevent="saveNotes">
    <label for="private-notes">Private notes</label>
    <p class="muted">
      One line per slide. Notes are stored separately from originals and shared
      responses.
    </p>
    <textarea
      id="private-notes"
      v-model="notes"
      name="notes"
      maxlength="12000"
      rows="6"
      placeholder="Slide 1 talking points&#10;Slide 2 talking points"
    ></textarea>
    <p id="active-note">{{ activeNote }}</p>
    <UiButton type="submit" variant="primary" :busy="busy"
      >Save private notes</UiButton
    ><UiStatus id="notes-status">{{ message }}</UiStatus>
  </form>
</template>
