<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import type { MotionData, MotionPlan, MotionShape, MotionStep } from "../types";
import {
  errorMessage,
  formData,
  pathFor,
  request,
  useCsrf,
} from "../composables/api";
import UiButton from "./UiButton.vue";
import UiDialog from "./UiDialog.vue";
import UiField from "./UiField.vue";
import UiOptions from "./UiOptions.vue";
import UiStatus from "./UiStatus.vue";
const props = defineProps<{
  name: string;
  filename: string;
  revision?: number | null;
}>();
const open = ref(false),
  data = ref<MotionData>(),
  steps = ref<MotionStep[]>([]),
  page = ref(1),
  query = ref(""),
  message = ref(""),
  busy = ref(false),
  failed = ref(false),
  replace = ref(false),
  draft = ref("");
const csrf = useCsrf();
const url = computed(() =>
  pathFor("motion", props.name, props.filename, props.revision),
);
const slide = computed(() =>
  data.value?.slides.find((slide) => slide.number === page.value),
);
const objects = computed(
  () =>
    slide.value?.shapes
      .filter((shape) =>
        `${shape.name} ${shape.text} #${shape.id}`
          .toLowerCase()
          .includes(query.value.toLowerCase()),
      )
      .slice(0, 150) || [],
);
const timeline = computed(() =>
  steps.value
    .map((step, index) => ({ step, index }))
    .filter((item) => item.step.slide === page.value),
);
const plan = computed<MotionPlan>(() => ({
  version: 1,
  source_sha256: data.value?.source_sha256 || "",
  replace_existing: replace.value,
  steps: steps.value,
}));
const effects = [
  { value: "appear", label: "Appear" },
  { value: "fade-in", label: "Fade in" },
  { value: "fade-out", label: "Fade out" },
  { value: "disappear", label: "Disappear" },
  { value: "wipe-in", label: "Wipe in" },
  { value: "fly-in", label: "Fly in" },
  { value: "zoom-in", label: "Zoom in" },
  { value: "move", label: "Move path" },
  { value: "scale", label: "Scale" },
];
let controller: AbortController | undefined;
watch(open, (value) => {
  if (value) void load();
  else controller?.abort();
});
async function load() {
  controller?.abort();
  controller = new AbortController();
  data.value = undefined;
  steps.value = [];
  busy.value = true;
  message.value = "Reading native PowerPoint objects…";
  failed.value = false;
  try {
    const result = await request<MotionData>(
      url.value,
      undefined,
      controller.signal,
    );
    data.value = result;
    steps.value = JSON.parse(JSON.stringify(result.plan.steps));
    replace.value = result.plan.replace_existing;
    page.value = 1;
    query.value = "";
    draft.value = JSON.stringify(plan.value, null, 2);
    message.value = result.plan.steps.length
      ? "Animation plan loaded."
      : "Choose a slide and add animations to its objects.";
  } catch (error) {
    if (!controller.signal.aborted) {
      message.value = errorMessage(error);
      failed.value = true;
    }
  } finally {
    busy.value = false;
  }
}
function add(shape: MotionShape) {
  steps.value.push({
    slide: page.value,
    target: { id: shape.id },
    effect: "fade-in",
    trigger: timeline.value.length ? "after" : "click",
    duration_ms: 600,
    delay_ms: 0,
  });
  message.value = "Animation added. Export to save this plan.";
}
function label(step: MotionStep) {
  const shape = data.value?.slides
    .find((slide) => slide.number === step.slide)
    ?.shapes.find((shape) =>
      "id" in step.target
        ? shape.id === step.target.id
        : "name" in step.target
          ? shape.name === step.target.name
          : shape.text === step.target.text,
    );
  return shape
    ? `${shape.name} · ${shape.text.slice(0, 65) || shape.type} (#${shape.id})`
    : "Unmapped object — reload or correct the manifest";
}
function setEffect(step: MotionStep, effect: string) {
  step.effect = effect;
  delete step.path;
  delete step.scale;
  delete step.direction;
  if (effect === "move")
    step.path = [
      [0, 0],
      [0.2, 0],
    ];
  if (effect === "scale") step.scale = [1.5, 1.5];
  if (effect === "fly-in" || effect === "wipe-in") step.direction = "right";
}
function reorder(index: number, offset: number) {
  const target = index + offset;
  if (
    target < 0 ||
    target >= steps.value.length ||
    steps.value[target].slide !== steps.value[index].slide
  )
    return;
  [steps.value[index], steps.value[target]] = [
    steps.value[target],
    steps.value[index],
  ];
}
function importJSON() {
  try {
    const value = JSON.parse(draft.value) as MotionPlan;
    if (
      value.version !== 1 ||
      value.source_sha256 !== data.value?.source_sha256 ||
      !Array.isArray(value.steps) ||
      value.steps.length > 1000 ||
      value.steps.some(
        (step) =>
          !step ||
          typeof step !== "object" ||
          !Number.isInteger(step.slide) ||
          !step.target ||
          typeof step.target !== "object" ||
          !effects.some((effect) => effect.value === step.effect) ||
          !["click", "with", "after"].includes(step.trigger) ||
          (step.effect === "scale" &&
            (!Array.isArray(step.scale) || step.scale.length !== 2)),
      )
    )
      throw Error(
        "Use version 1, the current source fingerprint and at most 1,000 steps.",
      );
    steps.value = value.steps;
    replace.value = value.replace_existing;
    message.value =
      "Manifest applied. Targets and effects are validated before export.";
    failed.value = false;
  } catch (error) {
    failed.value = true;
    message.value = errorMessage(error);
  }
}
async function exportFile() {
  busy.value = true;
  message.value = "Generating native PowerPoint animations…";
  failed.value = false;
  controller = new AbortController();
  try {
    const response = await fetch(url.value, {
      method: "POST",
      credentials: "same-origin",
      signal: controller.signal,
      headers: { Accept: "application/json" },
      body: formData({
        csrf,
        html_sha256: data.value?.html_sha256 || "",
        plan: JSON.stringify(plan.value),
      }),
    });
    if (
      !response.ok ||
      response.redirected ||
      !response.headers
        .get("Content-Type")
        ?.includes("presentationml.presentation")
    ) {
      let detail = "Your session may have expired. Refresh and sign in again.";
      if (response.headers.get("Content-Type")?.includes("application/json"))
        detail = (await response.json()).error || "Animated export failed.";
      throw Error(detail);
    }
    const blob = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = blob;
    link.download = props.filename.replace(/\.pptx$/i, "") + "-animated.pptx";
    link.click();
    setTimeout(() => URL.revokeObjectURL(blob), 30000);
    message.value =
      "Animated PowerPoint downloaded. Plan saved separately; original files are unchanged.";
  } catch (error) {
    if (!controller.signal.aborted) {
      message.value = errorMessage(error);
      failed.value = true;
    }
  } finally {
    busy.value = false;
  }
}
onBeforeUnmount(() => controller?.abort());
</script>
<template>
  <UiButton class="animated-export-trigger" @click="open = true"
    >Animated PPTX</UiButton
  ><UiDialog v-model:open="open" title="Native PowerPoint animations" wide>
    <p class="muted">
      {{ filename }} · Choose effects and playback order for your PowerPoint
      objects. Open the download in PowerPoint Slide Show to play animations;
      the library preview is static.
    </p>
    <UiStatus :error="failed" class="motion-status">{{ message }}</UiStatus>
    <template v-if="data"
      ><details
        v-if="data.warnings.length || data.import_issues.length"
        class="motion-source-notes"
        :open="!!data.import_issues.length"
      >
        <summary>Conversion notes</summary>
        <p v-for="warning in data.warnings" :key="warning" class="muted">
          {{ warning }}
        </p>
        <p
          v-for="issue in data.import_issues"
          :key="issue"
          class="motion-issue"
        >
          {{ issue }}
        </p>
      </details>
      <nav class="motion-slides" aria-label="Select animation slide">
        <UiButton
          v-for="slide in data.slides"
          :key="slide.number"
          :aria-pressed="page === slide.number"
          :disabled="busy"
          @click="
            page = slide.number;
            query = '';
          "
          >Slide {{ slide.number }}</UiButton
        >
      </nav>
      <div class="motion-workspace">
        <section class="motion-objects">
          <h3>Editable objects · Slide {{ page }}</h3>
          <input
            v-model="query"
            type="search"
            aria-label="Find PowerPoint objects"
            placeholder="Find text, object name or ID…"
          />
          <p class="muted">
            {{ slide?.shapes.length }} objects · Search to narrow the list.
          </p>
          <ul class="motion-object-list">
            <li v-for="shape in objects" :key="shape.id">
              <div>
                <strong>{{ shape.name || `Object ${shape.id}` }}</strong
                ><small
                  >{{ shape.text.slice(0, 120) || shape.type }} · #{{
                    shape.id
                  }}</small
                >
              </div>
              <UiButton
                :aria-label="`Animate object ${shape.id} on slide ${page}`"
                :disabled="busy || steps.length >= 1000"
                @click="add(shape)"
                >Add</UiButton
              >
            </li>
          </ul>
          <p v-if="!objects.length" class="muted">No objects match.</p>
        </section>
        <section class="motion-timeline">
          <h3>Animation steps · {{ timeline.length }}</h3>
          <p v-if="!timeline.length" class="muted">
            Add an object to begin. Order controls click groups and sequencing.
          </p>
          <ol class="motion-step-list">
            <li v-for="item in timeline" :key="item.index" class="motion-step">
              <strong>{{ label(item.step) }}</strong
              ><UiOptions
                label="Effect"
                :model-value="item.step.effect"
                :options="effects"
                @update:model-value="setEffect(item.step, $event)"
              /><UiOptions
                v-model="item.step.trigger"
                label="Start"
                :options="[
                  { value: 'click', label: 'On click' },
                  { value: 'with', label: 'With previous' },
                  { value: 'after', label: 'After previous' },
                ]"
              />
              <div class="motion-numbers">
                <UiField :id="`duration-${item.index}`" label="Duration (ms)"
                  ><input
                    :id="`duration-${item.index}`"
                    v-model.number="item.step.duration_ms"
                    type="number"
                    min="1"
                    max="60000" /></UiField
                ><UiField :id="`delay-${item.index}`" label="Delay (ms)"
                  ><input
                    :id="`delay-${item.index}`"
                    v-model.number="item.step.delay_ms"
                    type="number"
                    min="0"
                    max="60000"
                /></UiField>
              </div>
              <UiOptions
                v-if="item.step.direction"
                v-model="item.step.direction"
                label="Direction"
                :options="[
                  { value: 'right', label: 'Right' },
                  { value: 'left', label: 'Left' },
                  { value: 'up', label: 'Up' },
                  { value: 'down', label: 'Down' },
                ]"
              />
              <p v-if="item.step.effect === 'move'" class="muted">
                Default move: 20% of the slide width to the right. Edit path
                points in the manifest for custom routes.
              </p>
              <template v-if="item.step.effect === 'scale'"
                ><div class="motion-numbers">
                  <UiField
                    :id="`scale-x-${item.index}`"
                    label="Width multiplier"
                    ><input
                      :id="`scale-x-${item.index}`"
                      v-model.number="item.step.scale![0]"
                      type="number"
                      min="0.01"
                      max="10"
                      step="0.1" /></UiField
                  ><UiField
                    :id="`scale-y-${item.index}`"
                    label="Height multiplier"
                    ><input
                      :id="`scale-y-${item.index}`"
                      v-model.number="item.step.scale![1]"
                      type="number"
                      min="0.01"
                      max="10"
                      step="0.1"
                  /></UiField></div
              ></template>
              <div class="actions">
                <UiButton
                  :aria-label="`Move step ${item.index + 1} up`"
                  :disabled="busy || item.index === 0"
                  @click="reorder(item.index, -1)"
                  >↑</UiButton
                ><UiButton
                  :aria-label="`Move step ${item.index + 1} down`"
                  :disabled="busy || item.index === steps.length - 1"
                  @click="reorder(item.index, 1)"
                  >↓</UiButton
                ><UiButton
                  :aria-label="`Remove step ${item.index + 1}`"
                  :disabled="busy"
                  @click="steps.splice(item.index, 1)"
                  >Remove</UiButton
                >
              </div>
            </li>
          </ol>
        </section>
      </div>
      <label
        v-if="data.slides.some((slide) => slide.has_animation)"
        class="motion-replace"
        ><input v-model="replace" type="checkbox" />Replace existing timelines
        on selected slides</label
      >
      <details
        class="motion-manifest"
        @toggle="
          ($event.target as HTMLDetailsElement).open &&
          (draft = JSON.stringify(plan, null, 2))
        "
      >
        <summary>Exporter manifest / custom motion paths</summary>
        <p class="muted">
          This JSON is the conversion contract for your HTML-to-PPTX generator.
          Targets must resolve uniquely on their slide; paths start at [0,0] and
          use slide-relative offsets. Unsupported instructions produce errors.
        </p>
        <textarea
          v-model="draft"
          rows="10"
          maxlength="524288"
          aria-label="Animation manifest JSON"
        ></textarea
        ><UiButton :disabled="busy" @click="importJSON"
          >Apply manifest</UiButton
        >
      </details>
    </template>
    <div class="actions">
      <UiButton :disabled="busy" @click="load">Reload object map</UiButton
      ><UiButton
        variant="primary"
        :busy="busy"
        :disabled="!steps.length"
        @click="exportFile"
        >Download animated PowerPoint</UiButton
      >
    </div>
    <p class="muted">
      Reloading discards unsaved edits. A valid plan is saved when export
      succeeds.
    </p>
  </UiDialog>
</template>
