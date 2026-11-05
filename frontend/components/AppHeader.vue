<script setup lang="ts">
import { useCsrf } from "../composables/api";
import UiButton from "./UiButton.vue";
defineProps<{ library?: boolean }>();
const csrf = useCsrf();
</script>
<template>
  <header class="top app-header">
    <a class="brand" href="/"
      ><span class="mark" aria-hidden="true">▰</span>Slides</a
    >
    <nav v-if="library" class="app-nav" aria-label="Library navigation">
      <a href="/search">Search slide content</a
      ><a class="ui-button outline" href="/upload">+ Upload</a
      ><a href="/shares">Manage share links</a>
    </nav>
    <a v-else href="/">← Back to library</a>
    <form action="/logout" method="post">
      <input type="hidden" name="csrf" :value="csrf" /><UiButton type="submit"
        >Sign out</UiButton
      >
    </form>
  </header>
</template>
