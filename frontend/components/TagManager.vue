<script setup lang="ts">
import { computed, nextTick, ref, useId, watch } from "vue";
import type { LibraryData, LibraryDeck } from "../types";
import { errorMessage, formData, request, useCsrf } from "../composables/api";
import UiButton from "./UiButton.vue";
import UiDialog from "./UiDialog.vue";
import UiField from "./UiField.vue";
import UiStatus from "./UiStatus.vue";
const props = defineProps<{ open: boolean; decks: LibraryDeck[] }>();
const emit = defineEmits<{
  "update:open": [value: boolean];
  refreshed: [data: LibraryData];
  changed: [
    data: LibraryData,
    action: "rename" | "delete",
    old: string,
    replacement: string,
  ];
}>();
const csrf = useCsrf();
const renameId = useId();
let editingTrigger: HTMLElement | null = null;
const query = ref("");
const editing = ref("");
const action = ref<"rename" | "delete">("rename");
const replacement = ref("");
const busy = ref(false);
const message = ref("");
const error = ref(false);
const tags = computed(() => {
  const counts = new Map<string, number>();
  for (const deck of props.decks)
    for (const tag of deck.tags) counts.set(tag, (counts.get(tag) || 0) + 1);
  return [...counts]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => a.name.localeCompare(b.name));
});
const matches = computed(() =>
  tags.value.filter((tag) =>
    tag.name.includes(query.value.toLowerCase().trim()),
  ),
);
const affected = computed(() =>
  props.decks.filter((deck) => deck.tags.includes(editing.value)),
);
const normalized = computed(() =>
  replacement.value.normalize("NFKC").trim().replace(/\s+/g, " ").toLowerCase(),
);
const merging = computed(
  () =>
    normalized.value !== editing.value &&
    tags.value.some((tag) => tag.name === normalized.value),
);
const invalid = computed(
  () =>
    !normalized.value ||
    normalized.value.length > 48 ||
    /[,\x00-\x1f]/.test(normalized.value) ||
    normalized.value === editing.value,
);
watch(
  () => props.open,
  (open) => {
    if (open) {
      query.value = "";
      editing.value = "";
      message.value = "";
      error.value = false;
    }
  },
);
async function edit(
  name: string,
  next: "rename" | "delete",
  event: MouseEvent,
) {
  editingTrigger = event.currentTarget as HTMLElement;
  editing.value = name;
  action.value = next;
  replacement.value = name;
  message.value = "";
  error.value = false;
  await nextTick();
  document
    .getElementById(next === "rename" ? renameId : "cancel-tag-action")
    ?.focus();
}
function cancel() {
  if (!busy.value) {
    editing.value = "";
    message.value = "";
    editingTrigger?.focus();
  }
}
async function refresh() {
  busy.value = true;
  error.value = false;
  try {
    const data = await request<LibraryData>("/");
    emit("refreshed", data);
    editing.value = "";
    message.value = "Tag list refreshed.";
  } catch (failure) {
    message.value = errorMessage(failure);
    error.value = true;
  } finally {
    busy.value = false;
  }
}
async function save() {
  if (busy.value || (action.value === "rename" && invalid.value)) return;
  busy.value = true;
  message.value = "Saving…";
  error.value = false;
  const old = editing.value;
  let succeeded = false;
  try {
    const data = await request<
      LibraryData & { tag_change: { replacement: string | null } }
    >(
      "/tags",
      formData({
        csrf,
        action: action.value,
        tag: old,
        replacement: replacement.value,
      }),
    );
    const destination = data.tag_change.replacement || "";
    const wasMerging = merging.value;
    emit("changed", data, action.value, old, destination);
    message.value =
      action.value === "delete"
        ? `Removed “${old}” from the library.`
        : `“${old}” ${wasMerging ? "merged" : "renamed"} to “${destination}”.`;
    editing.value = "";
    query.value = "";
    succeeded = true;
  } catch (failure) {
    message.value = errorMessage(failure);
    error.value = true;
  } finally {
    busy.value = false;
    await nextTick();
    document
      .getElementById(
        succeeded
          ? "tag-search"
          : action.value === "rename"
            ? renameId
            : "cancel-tag-action",
      )
      ?.focus();
  }
}
</script>
<template>
  <UiDialog
    :open="open"
    title="Manage tags"
    @update:open="emit('update:open', $event)"
  >
    <p class="muted tag-manager-intro">
      {{ tags.length }} tags across {{ decks.length }} presentations. Changes
      apply to every deck using a tag.
    </p>
    <div class="tag-manager-search">
      <input
        id="tag-search"
        v-model="query"
        type="search"
        placeholder="Find a tag…"
        aria-label="Search tags"
        :disabled="busy"
      /><UiButton :disabled="busy" aria-label="Refresh tags" @click="refresh"
        >Refresh</UiButton
      >
    </div>
    <UiStatus id="tag-manager-status" :error="error">{{ message }}</UiStatus>
    <div v-if="!tags.length" class="tag-empty">
      <h3>No tags yet</h3>
      <p class="muted">
        Open a presentation and add its first tags. They’ll appear here for
        reuse and management.
      </p>
    </div>
    <p v-else-if="!matches.length" class="muted" role="status">
      No tags match “{{ query }}”.
    </p>
    <ul v-else class="tag-manager-list" aria-label="Library tags">
      <li
        v-for="tag in matches"
        :key="tag.name"
        class="tag-manager-row"
        :data-managed-tag="tag.name"
      >
        <div class="tag-manager-summary">
          <div>
            <strong>{{ tag.name }}</strong
            ><span class="muted tag-use-count"
              >{{ tag.count }}
              {{ tag.count === 1 ? "presentation" : "presentations" }}</span
            >
          </div>
          <div class="tag-manager-actions">
            <UiButton
              :aria-label="`Rename tag ${tag.name}`"
              :disabled="busy"
              @click="edit(tag.name, 'rename', $event)"
              >Rename</UiButton
            ><UiButton
              :aria-label="`Delete tag ${tag.name}`"
              :disabled="busy"
              @click="edit(tag.name, 'delete', $event)"
              >Delete</UiButton
            >
          </div>
        </div>
        <form
          v-if="editing === tag.name"
          class="tag-manager-edit"
          @submit.prevent="save"
        >
          <template v-if="action === 'rename'"
            ><UiField :id="renameId" label="New tag name"
              ><input
                :id="renameId"
                v-model="replacement"
                maxlength="48"
                :disabled="busy"
                required
                @keydown.esc.stop.prevent="cancel"
            /></UiField>
            <p class="tag-action-explanation">
              {{
                merging
                  ? `Merge “${tag.name}” into “${normalized}”. Existing assignments will be combined without duplicates.`
                  : `Rename this tag on ${affected.length} ${affected.length === 1 ? "presentation" : "presentations"}.`
              }}
            </p></template
          >
          <template v-else
            ><h3>Delete “{{ tag.name }}”?</h3>
            <p class="tag-action-explanation">
              This removes the tag from {{ affected.length }}
              {{ affected.length === 1 ? "presentation" : "presentations" }}.
              Presentation files remain intact.
            </p></template
          >
          <p class="muted affected-decks">
            {{ affected.map((deck) => deck.title).join(" · ") }}
          </p>
          <div class="actions">
            <UiButton id="cancel-tag-action" :disabled="busy" @click="cancel"
              >Cancel</UiButton
            ><UiButton
              type="submit"
              :variant="action === 'delete' ? 'danger' : 'primary'"
              :busy="busy"
              :disabled="action === 'rename' && invalid"
              >{{
                action === "delete"
                  ? "Delete tag"
                  : merging
                    ? "Merge tags"
                    : "Save name"
              }}</UiButton
            >
          </div>
        </form>
      </li>
    </ul>
  </UiDialog>
</template>
