<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useI18n } from "../i18n";
import type { TraceStepOut } from "../types/api";
import StatusBadge from "./StatusBadge.vue";

const props = defineProps<{
  steps: TraceStepOut[];
  selectedStepId: string | null;
  live?: boolean;
}>();

const emit = defineEmits<{
  select: [step: TraceStepOut];
}>();

const { t } = useI18n();
const listEl = ref<HTMLElement | null>(null);
const sortedSteps = computed(() => [...props.steps].sort((a, b) => a.step_index - b.step_index));

function stepTone(step: TraceStepOut): string {
  if (step.status === "error") {
    return "error";
  }
  return step.step_type;
}

async function scrollToBottom() {
  await nextTick();
  const el = listEl.value;
  if (!el) {
    return;
  }
  el.scrollTop = el.scrollHeight;
}

watch(
  () => {
    const steps = sortedSteps.value;
    return [steps.length, steps[steps.length - 1]?.id, props.live] as const;
  },
  () => {
    void scrollToBottom();
  }
);

onMounted(() => {
  void scrollToBottom();
});
</script>

<template>
  <section class="timeline-pane" aria-label="Trace Timeline">
    <div class="timeline-head">
      <div>
        <p class="eyebrow">{{ t("trace.eyebrow") }}</p>
        <h2>{{ t("trace.title") }}</h2>
      </div>
    </div>

    <div ref="listEl" class="timeline-list">
      <button
        v-for="step in sortedSteps"
        :key="step.id"
        type="button"
        class="trace-step"
        :class="{ selected: step.id === selectedStepId, error: step.status === 'error' }"
        @click="emit('select', step)"
      >
        <span class="step-index">{{ String(step.step_index).padStart(2, "0") }}</span>
        <span class="step-main">
          <span class="step-title">
            <StatusBadge :value="stepTone(step)" :pulse="step.step_type === 'reflection'" />
            <strong>{{ step.name }}</strong>
          </span>
          <span class="step-summary">
            {{ step.output_summary || step.input_summary || t("trace.emptySummary") }}
          </span>
        </span>
        <span class="step-meta">
          <span>{{ step.duration_ms ?? 0 }}ms</span>
          <span>{{ step.tokens ?? 0 }} tok</span>
        </span>
      </button>
      <div v-if="props.live" class="waiting-step" aria-live="polite">
        <span class="waiting-index">{{ String(sortedSteps.length + 1).padStart(2, "0") }}</span>
        <span class="waiting-main">
          <span class="waiting-dots" aria-hidden="true">
            <i></i>
            <i></i>
            <i></i>
          </span>
          <span>{{ t("trace.waiting") }}</span>
        </span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.timeline-pane {
  min-width: 0;
  padding: 18px 18px 22px;
  background: var(--panel);
}

.timeline-head {
  display: grid;
  grid-template-columns: minmax(220px, 0.62fr) minmax(260px, 1fr);
  gap: 18px;
  align-items: end;
  margin-bottom: 16px;
}

.timeline-note {
  color: var(--muted);
  font-family: var(--font-serif);
  font-size: 13px;
}

.timeline-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: min(72vh, 860px);
  overflow: auto;
  padding-right: 6px;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.trace-step {
  width: 100%;
  display: grid;
  grid-template-columns: 54px minmax(0, 1fr) auto;
  flex: 0 0 auto;
  gap: 12px;
  align-items: start;
  padding: 12px 10px;
  border: 1px solid transparent;
  border-bottom-color: var(--border);
  border-radius: 7px;
  background: transparent;
  text-align: left;
  animation: step-in 180ms ease-out both;
  transition:
    background-color var(--motion-fast) var(--ease-standard),
    border-color var(--motion-fast) var(--ease-standard),
    box-shadow var(--motion-fast) var(--ease-standard),
    transform var(--motion-fast) var(--ease-standard);
}

.trace-step.selected {
  border-color: var(--border-strong);
  background: rgba(251, 250, 247, 0.82);
}

.trace-step:hover:not(.selected) {
  border-color: var(--border);
  background: rgba(251, 250, 247, 0.72);
  box-shadow: 0 10px 22px rgba(36, 33, 29, 0.07);
  transform: translateY(-1px);
}

.trace-step.error {
  box-shadow: inset 3px 0 0 var(--failed);
}

.step-index {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 12px;
  font-feature-settings: "tnum" 1;
}

.step-main {
  min-width: 0;
}

.step-title {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
}

.step-title strong {
  overflow: hidden;
  color: var(--ink);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-summary {
  display: block;
  color: var(--muted-strong);
  font-family: var(--font-serif);
  font-size: 13px;
  line-height: 1.65;
}

.step-meta {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  white-space: nowrap;
}

.waiting-step {
  display: grid;
  grid-template-columns: 54px minmax(0, 1fr);
  flex: 0 0 auto;
  gap: 12px;
  align-items: center;
  padding: 12px 10px;
  border: 1px dashed var(--border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.58);
  color: var(--muted-strong);
}

.waiting-index {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 12px;
}

.waiting-main {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}

.waiting-dots {
  display: inline-flex;
  gap: 4px;
}

.waiting-dots i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--tool);
  animation: waiting-bounce 900ms ease-in-out infinite;
}

.waiting-dots i:nth-child(2) {
  animation-delay: 120ms;
}

.waiting-dots i:nth-child(3) {
  animation-delay: 240ms;
}

@keyframes waiting-bounce {
  0%,
  80%,
  100% {
    opacity: 0.38;
    transform: translateY(0);
  }

  40% {
    opacity: 1;
    transform: translateY(-3px);
  }
}

@media (max-width: 760px) {
  .timeline-head {
    grid-template-columns: 1fr;
  }

  .trace-step {
    grid-template-columns: 42px minmax(0, 1fr);
  }

  .step-meta {
    grid-column: 2;
    justify-content: flex-start;
  }

  .waiting-step {
    grid-template-columns: 42px minmax(0, 1fr);
  }
}
</style>
