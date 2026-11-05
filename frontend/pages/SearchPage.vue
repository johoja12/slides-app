<script setup lang="ts">
import { ref } from "vue";
import type { SearchData } from "../types";
import { errorMessage, request } from "../composables/api";
import AppHeader from "../components/AppHeader.vue";
import UiButton from "../components/UiButton.vue";
import UiField from "../components/UiField.vue";
import UiStatus from "../components/UiStatus.vue";
const props = defineProps<{ data: SearchData }>();
const state = ref(props.data),
  query = ref(props.data.query),
  tags = ref([...props.data.tags]),
  favorites = ref(props.data.favorites),
  busy = ref(false),
  message = ref("");
function toggleTag(tag: string) {
  tags.value = tags.value.includes(tag)
    ? tags.value.filter((value) => value !== tag)
    : [...tags.value, tag];
}
function url(page: number) {
  const params = new URLSearchParams({
    q: query.value,
    page: String(page),
    favorites: favorites.value ? "1" : "0",
  });
  tags.value.forEach((tag) => params.append("tag", tag));
  return "/search?" + params;
}
async function search(page = 1) {
  busy.value = true;
  message.value = "Searching…";
  try {
    const target = url(page);
    state.value = await request<SearchData>(target);
    history.replaceState(null, "", target);
    message.value = "";
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
    <h1>Search inside slides</h1>
    <p class="muted">
      Search visible HTML text, PowerPoint slides and PDF pages. Private
      presenter notes are excluded.
    </p>
  </div>
  <form class="card" @submit.prevent="search()">
    <UiField id="content-query" label="Words to find"
      ><input
        id="content-query"
        v-model="query"
        type="search"
        maxlength="200"
        placeholder="Find a phrase or topic"
    /></UiField>
    <div class="search-filters">
      <UiButton :aria-pressed="favorites" @click="favorites = !favorites"
        >★ Favorites only</UiButton
      ><UiButton
        v-for="tag in state.all_tags"
        :key="tag"
        :aria-pressed="tags.includes(tag)"
        @click="toggleTag(tag)"
        >{{ tag }}</UiButton
      >
    </div>
    <p class="muted">
      Selected tags match all tags. Query words match any word, ranked by
      relevance.
    </p>
    <UiButton type="submit" variant="primary" :busy="busy"
      >Search content</UiButton
    >
  </form>
  <UiStatus>{{ message }}</UiStatus>
  <p v-if="state.pending" class="muted" role="status">
    The library is still being indexed. Search again to continue; stale results
    are hidden.
  </p>
  <p role="status">{{ state.total }} matching slide/page results</p>
  <article
    v-for="result in state.results"
    :key="result.url"
    class="card search-result"
  >
    <a :href="result.url"
      ><h2>{{ result.title }}</h2></a
    >
    <p class="muted">{{ result.filename }} · Slide/page {{ result.page }}</p>
    <p>{{ result.snippet }}</p>
  </article>
  <p v-if="state.query && !state.results.length" class="muted">
    No matching content. Try another word or remove a filter.
  </p>
  <nav class="pagination" aria-label="Search pages">
    <UiButton v-if="state.page > 1" :busy="busy" @click="search(state.page - 1)"
      >← Previous</UiButton
    ><UiButton
      v-if="state.page * 20 < state.total"
      :busy="busy"
      @click="search(state.page + 1)"
      >Next →</UiButton
    >
  </nav>
</template>
