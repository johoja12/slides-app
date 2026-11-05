<script setup lang="ts">
import { computed, ref } from "vue";
import type { Share, SharesData } from "../types";
import {
  errorMessage,
  formData,
  localDate,
  request,
  useCsrf,
} from "../composables/api";
import AppHeader from "../components/AppHeader.vue";
import CopyLink from "../components/CopyLink.vue";
import UiButton from "../components/UiButton.vue";
import UiDialog from "../components/UiDialog.vue";
import UiOptions from "../components/UiOptions.vue";
import UiStatus from "../components/UiStatus.vue";
const props = defineProps<{ data: SharesData }>();
const rows = ref(props.data.rows),
  search = ref(""),
  status = ref(""),
  deck = ref(""),
  selected = ref(new Set<number>()),
  message = ref(""),
  busy = ref(false),
  copyUrl = ref(""),
  copyOpen = ref(false),
  confirmOpen = ref(false),
  pending = ref<{ action: "revoke" | "delete"; ids: number[] }>(),
  csrf = useCsrf();
const decks = computed(() =>
  [...new Set(rows.value.map((row) => row.title))].sort(),
);
const visible = computed(() =>
  rows.value.filter(
    (row) =>
      (!status.value || row.status === status.value) &&
      (!deck.value || row.title === deck.value) &&
      `${row.title} ${row.deck} #${row.id} ${row.created} ${row.expires} ${row.status} ${localDate(row.created_iso)}`
        .toLowerCase()
        .includes(search.value.trim().toLowerCase()),
  ),
);
const chosen = computed(() =>
  rows.value.filter((row) => selected.value.has(row.id)),
);
const hiddenCount = computed(
  () => chosen.value.filter((row) => !visible.value.includes(row)).length,
);
const allVisible = computed(
  () =>
    !!visible.value.length &&
    visible.value.every((row) => selected.value.has(row.id)),
);
const partialVisible = computed(
  () =>
    !allVisible.value &&
    visible.value.some((row) => selected.value.has(row.id)),
);
function toggle(id: number) {
  if (selected.value.has(id)) selected.value.delete(id);
  else selected.value.add(id);
}
function toggleAll() {
  const remove = allVisible.value;
  visible.value.forEach((row) =>
    remove ? selected.value.delete(row.id) : selected.value.add(row.id),
  );
}
async function refresh() {
  const data = await request<SharesData>("/shares");
  rows.value = data.rows;
  selected.value = new Set(
    [...selected.value].filter((id) => rows.value.some((row) => row.id === id)),
  );
}
function confirm(action: "revoke" | "delete", ids = [...selected.value]) {
  pending.value = { action, ids };
  confirmOpen.value = true;
}
async function apply() {
  if (!pending.value) return;
  busy.value = true;
  try {
    const value = pending.value;
    await request(
      "/shares/bulk",
      formData({ csrf, action: value.action, ids: value.ids.map(String) }),
    );
    await refresh();
    message.value =
      value.action === "revoke"
        ? "Selected active links revoked."
        : "Selected inactive records deleted.";
    confirmOpen.value = false;
  } catch (error) {
    message.value = errorMessage(error);
  } finally {
    busy.value = false;
  }
}
async function copy(row: Share) {
  busy.value = true;
  try {
    const result = await request<{ url: string }>(
      `/shares/${row.id}/copy`,
      formData({ csrf }),
    );
    try {
      await navigator.clipboard.writeText(result.url);
      message.value = `Link #${row.id} copied.`;
    } catch {
      copyUrl.value = result.url;
      copyOpen.value = true;
      message.value = "Copy the link from the dialog.";
    }
  } catch (error) {
    message.value = errorMessage(error);
  } finally {
    busy.value = false;
  }
}
async function reset(row: Share) {
  busy.value = true;
  try {
    await request(`/shares/${row.id}/activity/reset`, formData({ csrf }));
    await refresh();
    message.value = "Activity reset.";
  } catch (error) {
    message.value = errorMessage(error);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <AppHeader />
  <div class="page-heading">
    <h1>Share links</h1>
    <p class="muted">Manage access to shared presentations.</p>
  </div>
  <section v-if="data.link" class="card link-ready">
    <h2>Your link is ready</h2>
    <CopyLink :url="data.link" id="share-link" />
  </section>
  <div class="filters">
    <input
      id="share-search"
      v-model="search"
      type="search"
      placeholder="Search deck, link ID or date…"
      aria-label="Search share links"
    /><UiOptions
      v-model="status"
      label="Status"
      :options="[
        { value: '', label: 'All statuses' },
        { value: 'Active', label: 'Active' },
        { value: 'Expired', label: 'Expired' },
        { value: 'Revoked', label: 'Revoked' },
      ]"
    />
  </div>
  <details class="deck-filters">
    <summary>Filter by presentation {{ deck ? "· " + deck : "" }}</summary>
    <div class="tag-filter-list">
      <UiButton :aria-pressed="!deck" @click="deck = ''">All decks</UiButton
      ><UiButton
        v-for="title in decks"
        :key="title"
        :aria-pressed="deck === title"
        @click="deck = title"
        >{{ title }}</UiButton
      >
    </div>
  </details>
  <UiStatus id="copy-feedback">{{ message }}</UiStatus>
  <div class="bulkbar">
    <span id="selection" class="selection" role="status"
      >{{ chosen.length }} selected{{
        hiddenCount ? ` (${hiddenCount} hidden by filters)` : ""
      }}</span
    ><UiButton
      id="clear-selection"
      :disabled="!chosen.length"
      @click="selected.clear()"
      >Clear selection</UiButton
    ><UiButton
      id="bulk-revoke"
      :disabled="!chosen.some((row) => row.active) || busy"
      @click="confirm('revoke')"
      >Revoke selected</UiButton
    ><UiButton
      id="bulk-delete"
      :disabled="!chosen.length || chosen.some((row) => row.active) || busy"
      @click="confirm('delete')"
      >Delete inactive selected</UiButton
    >
  </div>
  <div
    class="table-wrap"
    role="region"
    aria-label="Share link records"
    tabindex="0"
  >
    <table aria-label="Share links">
      <thead>
        <tr>
          <th>
            <input
              id="select-visible"
              type="checkbox"
              :checked="allVisible"
              :indeterminate="partialVisible"
              :disabled="!visible.length"
              aria-label="Select all visible links"
              @change="toggleAll"
            />
          </th>
          <th>Presentation / link</th>
          <th>Version / activity</th>
          <th>Status</th>
          <th>Created</th>
          <th>Expires</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody id="share-rows">
        <tr
          v-for="row in visible"
          :key="row.id"
          :data-status="row.status"
          :data-deck="row.title"
        >
          <td>
            <input
              class="row-check"
              type="checkbox"
              :checked="selected.has(row.id)"
              :aria-label="`Select link ${row.id}`"
              @change="toggle(row.id)"
            />
          </td>
          <td class="deck-cell">
            <strong>{{ row.title }}</strong
            ><small>Link #{{ row.id }}</small>
          </td>
          <td>
            <span>{{
              row.revision ? `Revision ${row.revision}` : "Follows latest"
            }}</span
            ><small>{{ row.views }} observed visits</small
            ><time v-if="row.last_opened" :datetime="row.last_opened">{{
              localDate(row.last_opened)
            }}</time
            ><small v-else>Never opened</small
            ><UiButton class="row-action" :disabled="busy" @click="reset(row)"
              >Reset activity</UiButton
            >
          </td>
          <td>
            <span class="share-status" :class="row.status.toLowerCase()">{{
              row.status
            }}</span>
          </td>
          <td class="date">
            <time :datetime="row.created_iso">{{
              localDate(row.created_iso)
            }}</time>
          </td>
          <td class="date">
            <time v-if="row.expires_iso" :datetime="row.expires_iso">{{
              localDate(row.expires_iso)
            }}</time
            ><span v-else>No expiry</span>
          </td>
          <td>
            <div v-if="row.active" class="row-actions">
              <UiButton
                class="copy-existing row-action"
                :data-id="row.id"
                :disabled="busy"
                @click="copy(row)"
                >Copy link</UiButton
              ><UiButton
                class="row-action"
                :disabled="busy"
                @click="confirm('revoke', [row.id])"
                >Revoke link</UiButton
              >
            </div>
            <span v-else class="muted">—</span>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="!visible.length" id="empty-result" class="muted empty-result">
      No links match your filters.
    </p>
  </div>
  <p id="results" class="muted">
    {{ visible.length }} of {{ rows.length }} links
  </p>
  <p class="muted">
    Select all applies to visible rows. Selections stay selected when filters
    change. Delete removes expired or revoked link history.
  </p>
  <p class="muted">
    Observed visits count entry-link opens once per browser and share within 30
    minutes. Assets and detected bots do not count. Counts do not prove identity
    or reading. Totals remain until reset or history deletion.
  </p>
  <UiDialog
    v-model:open="confirmOpen"
    :title="
      pending?.action === 'delete'
        ? 'Delete inactive records?'
        : 'Revoke selected links?'
    "
    ><p>
      {{
        pending?.action === "delete"
          ? "This removes the selected inactive history records. This cannot be undone."
          : "Anyone using the selected active links will lose access."
      }}
    </p>
    <p>{{ pending?.ids.length }} selected link(s)</p>
    <div class="actions">
      <UiButton :disabled="busy" @click="confirmOpen = false">Cancel</UiButton
      ><UiButton variant="danger" :busy="busy" @click="apply">{{
        pending?.action === "delete" ? "Delete records" : "Revoke links"
      }}</UiButton>
    </div>
    <UiStatus>{{ message }}</UiStatus></UiDialog
  ><UiDialog v-model:open="copyOpen" title="Share link"
    ><CopyLink :url="copyUrl"
  /></UiDialog>
</template>
