<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
const props = defineProps<{ url: string; title: string; format: string }>();
const image = ref<HTMLImageElement>(),
  source = ref("");
let observer: IntersectionObserver | undefined,
  timer: ReturnType<typeof setTimeout> | undefined;
const controller = new AbortController();
async function load(attempt = 0) {
  try {
    const response = await fetch(props.url, {
      signal: controller.signal,
      credentials: "same-origin",
    });
    if (
      !response.ok ||
      response.redirected ||
      !response.headers.get("Content-Type")?.startsWith("image/")
    )
      return;
    const old = source.value;
    source.value = URL.createObjectURL(await response.blob());
    if (old) URL.revokeObjectURL(old);
    if (
      response.headers.get("X-Preview-State") === "processing" &&
      attempt < 25
    )
      timer = setTimeout(() => load(attempt + 1), 2000);
  } catch {
    /* Keep the explicit format fallback visible. */
  }
}
onMounted(() => {
  observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        observer?.disconnect();
        void load();
      }
    },
    { rootMargin: "160px" },
  );
  if (image.value) observer.observe(image.value);
});
onBeforeUnmount(() => {
  observer?.disconnect();
  controller.abort();
  clearTimeout(timer);
  if (source.value) URL.revokeObjectURL(source.value);
});
</script>
<template>
  <span class="deck-preview"
    ><img
      ref="image"
      :src="source || undefined"
      :data-thumbnail="url"
      loading="lazy"
      width="160"
      height="90"
      :alt="`Opening preview for ${title}`"
    /><span class="preview-fallback" aria-hidden="true">{{
      format
    }}</span></span
  >
</template>
