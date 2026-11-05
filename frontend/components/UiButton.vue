<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: "primary" | "outline" | "danger";
    busy?: boolean;
    type?: "button" | "submit" | "reset";
  }>(),
  { variant: "outline", type: "button", busy: false },
);
</script>
<template>
  <button
    :type="type"
    class="ui-button"
    :class="[variant, { busy }]"
    :aria-busy="busy || undefined"
    :disabled="busy"
  >
    <slot />
  </button>
</template>
