<script setup lang="ts">
defineProps<{ error?: boolean }>();
</script>
<template>
  <p
    class="ui-status"
    :class="{ 'is-error': error }"
    role="status"
    aria-live="polite"
  >
    <slot />
  </p>
</template>
