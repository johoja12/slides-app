<script setup lang="ts">
defineProps<{ id: string; label: string; hint?: string }>();
</script>
<template>
  <div class="ui-field">
    <label :for="id">{{ label }}</label
    ><slot />
    <p v-if="hint" :id="`${id}-help`" class="muted">{{ hint }}</p>
  </div>
</template>
