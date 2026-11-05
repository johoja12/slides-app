<script setup lang="ts">
import { onBeforeUnmount, ref, useId, watch } from "vue";
import UiButton from "./UiButton.vue";
const props = defineProps<{
  open: boolean;
  title: string;
  returnFocus?: HTMLElement;
}>();
const emit = defineEmits<{ "update:open": [value: boolean] }>();
const dialog = ref<HTMLDialogElement>();
const id = useId();
let previous: HTMLElement | null = null;
watch(
  () => props.open,
  (open) => {
    if (open) {
      previous = props.returnFocus || (document.activeElement as HTMLElement);
      dialog.value?.showModal();
    } else if (dialog.value?.open) dialog.value.close();
  },
  { flush: "post" },
);
function close() {
  emit("update:open", false);
  previous?.focus();
}
onBeforeUnmount(() => dialog.value?.close());
</script>
<template>
  <Teleport to="body"
    ><dialog
      ref="dialog"
      class="ui-dialog"
      :aria-labelledby="id"
      @close="close"
      @cancel.prevent="emit('update:open', false)"
    >
      <header class="dialog-header">
        <h2 :id="id">{{ title }}</h2>
        <UiButton aria-label="Close dialog" @click="emit('update:open', false)"
          >✕</UiButton
        >
      </header>
      <slot v-if="open" /></dialog
  ></Teleport>
</template>
