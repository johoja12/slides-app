<script setup lang="ts">
import { ref } from "vue";
import type { SharesData } from "../types";
import { errorMessage, formData, request, useCsrf } from "../composables/api";
import UiOptions from "./UiOptions.vue";
import UiButton from "./UiButton.vue";
import UiStatus from "./UiStatus.vue";
import UiDialog from "./UiDialog.vue";
import CopyLink from "./CopyLink.vue";
const props = defineProps<{ deck: string; revision?: number | null }>();
const csrf = useCsrf();
const days = ref("7"),
  version = ref("latest"),
  busy = ref(false),
  message = ref(""),
  link = ref(""),
  showLink = ref(false);
const trigger = ref<HTMLElement>();
const emit = defineEmits<{ created: [] }>();
const expiryOptions = [
  { value: "1", label: "1 day" },
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "0", label: "No expiry" },
];
const versionOptions = [
  { value: "latest", label: "Follow latest" },
  { value: "fixed", label: "Fixed snapshot" },
];
async function create(event: SubmitEvent) {
  trigger.value =
    event.submitter instanceof HTMLElement ? event.submitter : undefined;
  busy.value = true;
  message.value = "Creating link…";
  try {
    const data = await request<SharesData>(
      "/shares",
      formData({
        csrf,
        deck: props.deck,
        days: days.value,
        version: version.value,
        revision: props.revision || "",
      }),
    );
    if (!data.link)
      throw new Error(
        "The link could not be created. Check share management before retrying.",
      );
    link.value = data.link;
    showLink.value = true;
    message.value = "Link ready.";
    emit("created");
  } catch (error) {
    message.value =
      errorMessage(error) +
      " Check Manage share links before retrying if the connection was interrupted.";
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <form class="share-form" @submit.prevent="create">
    <UiOptions
      v-model="days"
      label="Link expires"
      :options="expiryOptions"
    /><UiOptions
      v-model="version"
      label="Version"
      :options="versionOptions"
    /><UiButton type="submit" :busy="busy">{{
      busy ? "Creating…" : "Share link ↗"
    }}</UiButton
    ><UiStatus>{{ message }}</UiStatus>
  </form>
  <UiDialog
    v-model:open="showLink"
    :return-focus="trigger"
    title="Your link is ready"
    ><p class="muted">
      Anyone holding this link can view this presentation. Keep it private.
    </p>
    <CopyLink :url="link" :id="`share-link-${deck}`" /><a
      href="/shares"
      class="text-link"
      >Manage share links</a
    ></UiDialog
  >
</template>
