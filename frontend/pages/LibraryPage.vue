<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import type { LibraryData, SortMode } from "../types";
import { errorMessage, formData, request, useCsrf } from "../composables/api";
import { readPreference, writePreference } from "../composables/storage";
import AppHeader from "../components/AppHeader.vue";
import DeckRow from "../components/DeckRow.vue";
import UiButton from "../components/UiButton.vue";
import UiField from "../components/UiField.vue";
import UiStatus from "../components/UiStatus.vue";
const props = defineProps<{ data: LibraryData }>();
const decks = ref(props.data.entries),
  search = ref(""),
  message = ref(""),
  csrf = useCsrf();
const modes: { value: SortMode; label: string; aria: string }[] = [
  { value: "name-asc", label: "Name A–Z", aria: "Name A to Z" },
  { value: "name-desc", label: "Z–A", aria: "Name Z to A" },
  {
    value: "modified-desc",
    label: "Newest",
    aria: "Date modified newest first",
  },
  {
    value: "modified-asc",
    label: "Oldest",
    aria: "Date modified oldest first",
  },
];
// Keep the previous browser's plain-string sort preference compatible.
function savedSort(): SortMode {
  try {
    const value = localStorage.getItem("slides-library-sort");
    if (modes.some((mode) => mode.value === value)) return value as SortMode;
  } catch {}
  return "name-asc";
}
const sort = ref<SortMode>(savedSort());
const favorites = ref(
  readPreference(
    "slides-library-favorites-only",
    false,
    (v): v is boolean => typeof v === "boolean",
  ),
);
const selectedTags = ref(
  readPreference(
    "slides-library-tags",
    [],
    (v): v is string[] =>
      Array.isArray(v) && v.every((tag) => typeof tag === "string"),
  ),
);
const allTags = computed(() =>
  [...new Set(decks.value.flatMap((deck) => deck.tags))].sort(),
);
const collator = new Intl.Collator(undefined, {
  numeric: true,
  sensitivity: "base",
});
const sorted = computed(() =>
  [...decks.value].sort((a, b) => {
    const pin = b.pinned - a.pinned;
    if (pin) return pin;
    const byName = collator.compare(a.title, b.title);
    if (sort.value.startsWith("modified-")) {
      const delta = Date.parse(a.updated_iso) - Date.parse(b.updated_iso);
      return delta ? (sort.value === "modified-desc" ? -delta : delta) : byName;
    }
    return sort.value === "name-desc" ? -byName : byName;
  }),
);
function visible(deck: LibraryData["entries"][number]): boolean {
  return (
    (!favorites.value || !!deck.favorite) &&
    `${deck.title} ${deck.description}`
      .toLowerCase()
      .includes(search.value.toLowerCase()) &&
    selectedTags.value.every((tag) => deck.tags.includes(tag))
  );
}
const visibleCount = computed(() => decks.value.filter(visible).length);
watch(sort, (value) => {
  try {
    localStorage.setItem("slides-library-sort", value);
  } catch {}
});
watch(favorites, (value) =>
  writePreference("slides-library-favorites-only", value),
);
watch(selectedTags, (value) => writePreference("slides-library-tags", value), {
  deep: true,
});
watch(
  allTags,
  (available) => {
    selectedTags.value = selectedTags.value.filter((tag) =>
      available.includes(tag),
    );
  },
  { immediate: true },
);
function toggleTag(tag: string) {
  selectedTags.value = selectedTags.value.includes(tag)
    ? selectedTags.value.filter((value) => value !== tag)
    : [...selectedTags.value, tag];
}
async function preference(
  name: string,
  field: "favorite" | "pinned",
  value: number,
) {
  const deck = decks.value.find((deck) => deck.name === name);
  if (deck) {
    deck[field] = value;
    if (!visible(deck)) {
      await nextTick();
      document.querySelector<HTMLButtonElement>("#favorites-only")?.focus();
    }
  }
}
const oldTag = ref(""),
  newTag = ref(""),
  tagBusy = ref(false);
async function manageTags(action: "rename" | "delete") {
  if (!oldTag.value.trim() || (action === "rename" && !newTag.value.trim())) {
    message.value = "Enter the existing tag and its replacement when renaming.";
    return;
  }
  tagBusy.value = true;
  try {
    await request(
      "/tags",
      formData({ csrf, action, tag: oldTag.value, replacement: newTag.value }),
    );
    const data = await request<LibraryData>("/");
    decks.value = data.entries;
    message.value = "Tags updated.";
  } catch (error) {
    message.value = errorMessage(error);
  } finally {
    tagBusy.value = false;
  }
}
</script>
<template>
  <AppHeader library />
  <div class="page-heading">
    <h1>Slide library</h1>
    <p class="muted">
      {{ data.count }} folders · Open a folder to view its files.
    </p>
  </div>
  <div class="library-controls">
    <input
      id="search"
      v-model="search"
      class="search"
      type="search"
      placeholder="Find a folder…"
      aria-label="Find a presentation"
    /><UiButton
      id="favorites-only"
      class="filter-button"
      :aria-pressed="favorites"
      @click="favorites = !favorites"
      >★ Favorites only</UiButton
    >
    <div class="library-sort" role="group" aria-label="Sort presentations">
      <span class="muted">Sort by</span>
      <div v-for="start in [0, 2]" :key="start" class="sort-group">
        <UiButton
          v-for="mode in modes.slice(start, start + 2)"
          :key="mode.value"
          class="sort-button"
          :data-sort="mode.value"
          :aria-label="mode.aria"
          :aria-pressed="sort === mode.value"
          @click="sort = mode.value"
          >{{ mode.label }}</UiButton
        >
      </div>
    </div>
  </div>
  <div
    id="tag-filters"
    class="tag-filter-list"
    role="group"
    aria-label="Filter by tags (match all selected tags)"
  >
    <UiButton
      v-for="tag in allTags"
      :key="tag"
      class="tag-filter"
      :data-tag="tag"
      :aria-pressed="selectedTags.includes(tag)"
      @click="toggleTag(tag)"
      >{{ tag }}</UiButton
    >
  </div>
  <details class="tag-management">
    <summary>Manage tags</summary>
    <form class="card compact-card" @submit.prevent="manageTags('rename')">
      <UiField id="old-tag" label="Existing tag"
        ><input id="old-tag" v-model="oldTag" required /></UiField
      ><UiField id="new-tag" label="New name (for rename)"
        ><input id="new-tag" v-model="newTag"
      /></UiField>
      <div class="actions">
        <UiButton type="submit" :busy="tagBusy">Rename everywhere</UiButton
        ><UiButton :busy="tagBusy" @click="manageTags('delete')"
          >Remove everywhere</UiButton
        >
      </div>
    </form>
  </details>
  <UiStatus id="preference-status">{{ message }}</UiStatus>
  <section class="folder-list" aria-label="Presentation folders">
    <DeckRow
      v-for="deck in sorted"
      :key="deck.name"
      :deck="deck"
      :visible="visible(deck)"
      @preference="(field, value) => preference(deck.name, field, value)"
      @tags="(tags) => (deck.tags = tags)"
      @status="message = $event"
    />
  </section>
  <p v-show="!visibleCount" id="empty" class="muted">
    No folders match your filters.
  </p>
</template>
