<script setup lang="ts">
import { computed } from "vue";
import type { TraceStepOut } from "../types/api";
import StatusBadge from "./StatusBadge.vue";

const props = defineProps<{
  steps: TraceStepOut[];
  selectedStepId: string | null;
}>();

const emit = defineEmits<{
  select: [step: TraceStepOut];
}>();

const sortedSteps = computed(() => [...props.steps].sort((a, b) => a.step_index - b.step_index));

function stepTone(step: TraceStepOut): string {
  if (step.status === "error") {
    return "error";
  }
  return step.step_type;
}
</script>

<template>
  <section class="timeline-pane" aria-label="Trace Timeline">
    <div class="timeline-head">
      <div>
        <p class="eyebrow">过程轨迹</p>
        <h2>Agent Trace Timeline</h2>
      </div>
      <p class="timeline-note">
        按 <code>step_index</code> 展示真实顺序。pytest 失败保留证据，不等于系统 run failed。
      </p>
    </div>

    <div class="timeline-list">
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
            {{ step.output_summary || step.input_summary || "No summary recorded." }}
          </span>
        </span>
        <span class="step-meta">
          <span>{{ step.duration_ms ?? 0 }}ms</span>
          <span>{{ step.tokens ?? 0 }} tok</span>
        </span>
      </button>
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
  display: grid;
  gap: 10px;
}

.trace-step {
  width: 100%;
  display: grid;
  grid-template-columns: 54px minmax(0, 1fr) auto;
  gap: 12px;
  align-items: start;
  padding: 12px 0;
  border: 0;
  border-bottom: 1px solid var(--border);
  border-radius: 0;
  background: transparent;
  text-align: left;
  animation: step-in 180ms ease-out both;
}

.trace-step.selected {
  padding-inline: 10px;
  border: 1px solid var(--border-strong);
  border-radius: 7px;
  background: rgba(251, 250, 247, 0.82);
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
}
</style>
