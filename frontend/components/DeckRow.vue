<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import type { LibraryDeck } from "../types";
import {
  errorMessage,
  formData,
  localDate,
  pathFor,
  request,
  useCsrf,
} from "../composables/api";
import DeckPreview from "./DeckPreview.vue";
import ShareComposer from "./ShareComposer.vue";
import UiButton from "./UiButton.vue";
import UiField from "./UiField.vue";
const props = defineProps<{ deck: LibraryDeck; visible: boolean }>();
const emit = defineEmits<{
  preference: [field: "favorite" | "pinned", value: number];
  tags: [tags: string[]];
  status: [message: string];
}>();
const csrf = useCsrf(),
  open = ref(false),
  tags = ref(props.deck.tags.join(", ")),
  busy = ref("");
watch(
  () => props.deck.tags,
  (value) => {
    tags.value = value.join(", ");
  },
);
async function preference(field: "favorite" | "pinned", event: MouseEvent) {
  const button = event.currentTarget as HTMLButtonElement;
  busy.value = field;
  const value = props.deck[field] ? 0 : 1;
  try {
    const result = await request<Record<string, boolean>>(
      `/preferences/${encodeURIComponent(props.deck.name)}`,
      formData({ csrf, field, value }),
    );
    if (result[field] !== Boolean(value))
      throw new Error("Could not save your preference.");
    emit("preference", field, value);
    emit("status", "Preference saved.");
  } catch (error) {
    emit("status", "Could not save your preference. " + errorMessage(error));
  } finally {
    busy.value = "";
    await nextTick();
    if (props.visible) button.focus();
  }
}
async function saveTags() {
  busy.value = "tags";
  try {
    const data = await request<{ tags: string[] }>(
      `/tags/${encodeURIComponent(props.deck.name)}`,
      formData({ csrf, tags: tags.value }),
    );
    emit("tags", data.tags);
    emit("status", "Tags saved.");
  } catch (error) {
    emit("status", "Could not save tags. " + errorMessage(error));
  } finally {
    busy.value = "";
  }
}
</script>
<template>
  <details
    v-show="visible"
    class="folder-row"
    :open="open"
    :data-title="deck.title"
    :data-modified="deck.updated_iso"
    :data-favorite="deck.favorite"
    :data-pinned="deck.pinned"
    :data-tags="JSON.stringify(deck.tags)"
    @toggle="open = ($event.target as HTMLDetailsElement).open"
  >
    <summary>
      <span class="chevron" aria-hidden="true">›</span
      ><DeckPreview
        :url="deck.thumbnail"
        :title="deck.title"
        :format="deck.files[0]?.format || 'DECK'"
      />
      <div class="folder-info">
        <div class="folder-title">
          {{ deck.title
          }}<span v-if="deck.favorite" class="preference-badge">★ Favorite</span
          ><span v-if="deck.pinned" class="preference-badge">Pinned</span>
        </div>
        <div class="folder-subtitle">{{ deck.description }}</div>
        <div class="folder-updated">
          Last updated
          <time :datetime="deck.updated_iso">{{
            localDate(deck.updated_iso)
          }}</time>
        </div>
      </div>
      <span class="folder-formats">{{
        deck.files.map((file) => file.format).join(" · ")
      }}</span>
    </summary>
    <div class="folder-content">
      <a
        class="history-link"
        :href="`/history/${encodeURIComponent(deck.name)}`"
        >Version history ↗</a
      >
      <div class="tag-chips">
        <span v-for="tag in deck.tags" :key="tag" class="tag-chip">{{
          tag
        }}</span>
      </div>
      <div class="preference-controls">
        <UiButton
          v-for="field in ['favorite', 'pinned'] as const"
          :key="field"
          :data-preference="field"
          :aria-label="`${field === 'favorite' ? 'Favorite' : 'Pin to top'}: ${deck.title}`"
          :aria-pressed="!!deck[field]"
          :busy="busy === field"
          :disabled="!!busy"
          @click="preference(field, $event)"
          >{{ field === "favorite" ? "Favorite" : "Pin to top" }}</UiButton
        >
      </div>
      <form class="tag-editor" @submit.prevent="saveTags">
        <UiField
          :id="`tags-${deck.name}`"
          label="Private tags"
          hint="Comma separated; up to 20 tags."
          ><div class="tag-edit-fields">
            <input
              :id="`tags-${deck.name}`"
              v-model="tags"
              name="tags"
              maxlength="1000"
              placeholder="product, customer, event"
            /><UiButton type="submit" :busy="busy === 'tags'"
              >Save tags</UiButton
            >
          </div></UiField
        >
      </form>
      <div v-if="deck.linked_formats" class="file-row linked-presentation">
        <span class="file-format">DECK</span
        ><span class="file-name">{{ deck.title }}</span
        ><a
          class="file-action"
          :href="pathFor('view', deck.name, deck.format_files.html)"
          >View HTML →</a
        ><a
          class="file-action"
          :href="pathFor('view', deck.name, deck.format_files.pptx)"
          >View PPTX →</a
        ><a
          class="file-action"
          :href="pathFor('decks', deck.name, deck.format_files.pptx)"
          download
          >Download PPTX ↓</a
        >
      </div>
      <template v-for="file in deck.files" :key="file.name"
        ><div
          v-if="
            !deck.linked_formats ||
            ![deck.format_files.html, deck.format_files.pptx].includes(
              file.name,
            )
          "
          class="file-row"
        >
          <span class="file-format">{{ file.format }}</span
          ><a
            class="file-name"
            :href="file.preview_url || file.url"
            :target="file.format === 'PDF' ? '_blank' : undefined"
            rel="noopener"
            >{{ file.name }}</a
          ><a
            v-if="file.preview_url"
            class="file-action"
            :href="file.preview_url"
            >View PPTX →</a
          ><a
            class="file-action"
            :href="file.url"
            :download="file.format === 'PPTX' ? '' : undefined"
            :target="file.format === 'PDF' ? '_blank' : undefined"
            rel="noopener"
            >{{
              file.format === "HTML"
                ? "Present →"
                : file.format === "PDF"
                  ? "View ↗"
                  : "Download PPTX ↓"
            }}</a
          >
        </div></template
      >
      <ShareComposer :deck="deck.name" />
    </div>
  </details>
</template>
