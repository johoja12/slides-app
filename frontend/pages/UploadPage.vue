<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import type { UploadData } from "../types";
import { useCsrf } from "../composables/api";
import AppHeader from "../components/AppHeader.vue";
import UiButton from "../components/UiButton.vue";
import UiField from "../components/UiField.vue";
import UiOptions from "../components/UiOptions.vue";
import UiStatus from "../components/UiStatus.vue";
const props = defineProps<{ data: UploadData }>();
const csrf = useCsrf(),
  name = ref(props.data.deck),
  title = ref(""),
  mode = ref(props.data.deck ? "revision" : "new"),
  files = ref<File[]>([]),
  dragging = ref(false),
  busy = ref(false),
  progress = ref(0),
  message = ref(""),
  pairing = ref({ html: "", pptx: "", pdf: "" }),
  input = ref<HTMLInputElement>();
const selected = computed(() =>
  props.data.entries.find((deck) => deck.name === name.value),
);
let xhr: XMLHttpRequest | undefined;
function changed(event: Event) {
  files.value = Array.from((event.target as HTMLInputElement).files || []);
}
function dropped(event: DragEvent) {
  dragging.value = false;
  files.value = Array.from(event.dataTransfer?.files || []);
  if (input.value && event.dataTransfer)
    input.value.files = event.dataTransfer.files;
}
function publish() {
  if (!files.value.length) {
    message.value = "Choose at least one presentation file or ZIP.";
    return;
  }
  if (
    files.value.reduce((sum, file) => sum + file.size, 0) >
    100 * 1024 * 1024
  ) {
    message.value = "Choose files totaling at most 100 MB.";
    return;
  }
  if (mode.value === "revision" && !selected.value) {
    message.value = "Choose an existing deck for the new revision.";
    return;
  }
  const body = new FormData();
  for (const [key, value] of Object.entries({
    csrf,
    name: name.value,
    title: title.value,
    mode: mode.value,
    expected: selected.value?.revision || "live",
    ...pairing.value,
    last_modified: JSON.stringify(
      Object.fromEntries(
        files.value.map((file) => [file.name, file.lastModified / 1000]),
      ),
    ),
  }))
    body.append(key, String(value));
  for (const file of files.value) body.append("files", file);
  busy.value = true;
  progress.value = 0;
  message.value = "Uploading…";
  xhr = new XMLHttpRequest();
  xhr.open("POST", "/upload");
  xhr.setRequestHeader("Accept", "application/json");
  xhr.upload.onprogress = (event) => {
    if (event.lengthComputable)
      progress.value = (event.loaded / event.total) * 100;
    message.value =
      progress.value >= 100 ? "Validating and publishing…" : "Uploading…";
  };
  xhr.onload = () => {
    busy.value = false;
    try {
      const result = JSON.parse(xhr!.responseText);
      if (xhr!.status === 200 && typeof result.url === "string") {
        location.assign(result.url);
        return;
      }
      message.value =
        result.error || "Could not publish. Reload before retrying.";
    } catch {
      message.value =
        "Your session may have expired. Refresh and sign in again.";
    }
  };
  xhr.onerror = () => {
    busy.value = false;
    message.value =
      "Connection interrupted. Check version history before retrying; publishing may have completed.";
  };
  xhr.send(body);
}
onBeforeUnmount(() => xhr?.abort());
</script>
<template>
  <AppHeader />
  <div class="page-heading">
    <h1>Add a presentation</h1>
    <p class="muted">
      Upload HTML with relative assets in a ZIP, PowerPoint or PDF. Published
      revisions keep your originals intact.
    </p>
  </div>
  <form id="upload-form" class="card upload-card" @submit.prevent="publish">
    <UiOptions
      v-model="mode"
      label="Upload destination"
      :options="[
        { value: 'new', label: 'New presentation' },
        { value: 'revision', label: 'New revision' },
      ]"
    />
    <UiField
      id="deck-name"
      label="Deck name"
      hint="Stable URL name: lowercase letters, digits and hyphens."
      ><input
        id="deck-name"
        v-model="name"
        name="name"
        required
        pattern="[a-z0-9][a-z0-9-]{0,79}"
        placeholder="quarterly-update"
        aria-describedby="deck-name-help"
    /></UiField>
    <div
      v-if="mode === 'revision'"
      class="existing-decks"
      role="group"
      aria-label="Existing decks"
    >
      <UiButton
        v-for="deck in data.entries"
        :key="deck.name"
        :aria-pressed="name === deck.name"
        @click="name = deck.name"
        >{{ deck.title }}</UiButton
      >
    </div>
    <UiField id="deck-title" label="Display title"
      ><input
        id="deck-title"
        v-model="title"
        maxlength="200"
        placeholder="Quarterly update"
    /></UiField>
    <div
      id="drop-zone"
      class="drop-zone"
      :class="{ dragging }"
      @dragenter.prevent="dragging = true"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="dropped"
    >
      <p>Drop presentation files or ZIP bundles here</p>
      <label class="ui-button primary" for="deck-files">Choose files</label
      ><input
        id="deck-files"
        ref="input"
        type="file"
        name="files"
        multiple
        accept=".html,.pptx,.pdf,.zip"
        @change="changed"
      />
      <p class="muted">100 MB upload · 300 MB expanded · 1,500 files</p>
      <p id="file-list" role="status">
        {{ files.map((file) => file.name).join(", ") }}
      </p>
    </div>
    <details>
      <summary>Pair equivalent formats</summary>
      <p class="muted">
        One file per format is paired automatically. Enter the exact top-level
        filename if the bundle contains several candidates.
      </p>
      <UiField
        v-for="kind in ['html', 'pptx', 'pdf'] as const"
        :id="`pair-${kind}`"
        :key="kind"
        :label="`${kind.toUpperCase()} filename`"
        ><input
          :id="`pair-${kind}`"
          v-model="pairing[kind]"
          :placeholder="`example.${kind}`"
      /></UiField>
    </details>
    <progress
      v-if="busy"
      id="upload-progress"
      max="100"
      :value="progress"
      aria-label="Upload progress"
    ></progress
    ><UiStatus id="upload-status">{{ message }}</UiStatus
    ><UiButton id="publish" type="submit" variant="primary" :busy="busy">{{
      busy ? "Publishing…" : "Upload and publish"
    }}</UiButton>
  </form>
</template>
