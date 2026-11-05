<script setup lang="ts">
import { ref } from "vue";
import type { HistoryData } from "../types";
import {
  errorMessage,
  formData,
  localDate,
  request,
  useCsrf,
} from "../composables/api";
import AppHeader from "../components/AppHeader.vue";
import UiButton from "../components/UiButton.vue";
import UiStatus from "../components/UiStatus.vue";
const props = defineProps<{ data: HistoryData }>();
const state = ref(props.data),
  message = ref(""),
  busy = ref(false),
  csrf = useCsrf();
async function action(action: "snapshot" | "select", revision = "") {
  busy.value = true;
  message.value = "Saving…";
  try {
    state.value = await request<HistoryData>(
      location.pathname,
      formData({ csrf, action, revision, expected: state.value.selected }),
    );
    message.value = "Version history updated.";
  } catch (error) {
    message.value = errorMessage(error);
  } finally {
    busy.value = false;
  }
}
function presentation(name: string) {
  return !name.includes("/") && /\.(html|pptx|pdf)$/i.test(name);
}
</script>
<template>
  <AppHeader />
  <div class="page-heading">
    <p class="eyebrow">Version history</p>
    <h1>{{ state.entry.title }}</h1>
    <p class="muted">
      Restoring selects a revision. Original files and older revisions stay
      intact.
    </p>
    <a
      class="ui-button outline"
      :href="`/upload?deck=${encodeURIComponent(state.entry.name)}`"
      >Upload new revision</a
    >
  </div>
  <UiStatus>{{ message }}</UiStatus>
  <section class="card">
    <UiButton variant="primary" :busy="busy" @click="action('snapshot')"
      >Save a snapshot of the current deck</UiButton
    >
    <p class="muted">
      Capture the live folder before replacing files outside this app. Identical
      content reuses the same revision.
    </p>
  </section>
  <section v-if="state.live" class="card version-card">
    <h2>
      Live library folder {{ state.selected === "live" ? "· Current" : "" }}
    </h2>
    <p class="muted">Tracks the original read-only library folder.</p>
    <UiButton
      v-if="state.selected !== 'live'"
      :busy="busy"
      @click="action('select', 'live')"
      >Use live folder</UiButton
    >
  </section>
  <section
    v-for="revision in state.revisions"
    :key="revision.id"
    class="card version-card"
  >
    <h2>
      Revision {{ revision.id }}
      {{ state.selected === String(revision.id) ? "· Current" : "" }}
    </h2>
    <p class="muted">
      Saved
      <time :datetime="revision.created">{{
        localDate(revision.created)
      }}</time>
      · Content modified
      <time :datetime="revision.modified">{{
        localDate(revision.modified)
      }}</time>
    </p>
    <div class="version-files">
      <template v-for="file in revision.files" :key="file.name"
        ><a
          v-if="presentation(file.name)"
          class="ui-button outline"
          :href="file.url"
          >{{ file.name }} · {{ Math.round(file.bytes / 1024) }} KB ↗</a
        ></template
      >
    </div>
    <UiButton
      v-if="state.selected !== String(revision.id)"
      variant="primary"
      :busy="busy"
      @click="action('select', String(revision.id))"
      >Use this revision</UiButton
    >
  </section>
  <p v-if="!state.revisions.length" class="muted">
    No saved revisions yet. Save a snapshot to start this deck’s history.
  </p>
</template>
