<script setup lang="ts">
import { ref, useId } from "vue";
import UiButton from "./UiButton.vue";
import UiStatus from "./UiStatus.vue";
defineProps<{ url: string; id?: string }>();
const unique = useId();
const field = ref<HTMLInputElement>();
const message = ref("");
async function copy() {
  field.value?.select();
  try {
    await navigator.clipboard.writeText(field.value?.value || "");
    message.value = "Link copied.";
  } catch {
    message.value = "Select and copy the link above.";
  }
}
</script>
<template>
  <div class="copy-link">
    <label :for="id || unique">Share URL</label
    ><input
      :id="id || unique"
      ref="field"
      :value="url"
      readonly
      aria-label="Share URL"
      @click="field?.select()"
    /><UiButton @click="copy">Copy link</UiButton
    ><UiStatus>{{ message }}</UiStatus>
  </div>
</template>
