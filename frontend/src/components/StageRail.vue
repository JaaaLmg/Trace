<script setup lang="ts">
import { computed } from "vue";
import { AlertCircle, Check, Circle } from "@lucide/vue";
import { useI18n } from "../i18n";
import type { RunStage, RunStatus, TraceStepOut } from "../types/api";

const props = defineProps<{
  status: RunStatus;
  stage: RunStage | null;
  traceSteps: TraceStepOut[];
}>();

const stages: RunStage[] = [
  "preparing",
  "analyzing",
  "planning",
  "generating",
  "executing",
  "reflecting",
  "reexecuting",
  "summarizing"
];

const { t } = useI18n();

const stageCounts = computed(() => {
  const counts = new Map<string, number>();
  props.traceSteps.forEach((step) => {
    const name = step.step_type === "reflection" ? "reflecting" : null;
    if (name) {
      counts.set(name, (counts.get(name) ?? 0) + 1);
    }
  });
  return counts;
});

function itemState(stage: RunStage): "done" | "current" | "failed" | "idle" {
  if (props.status === "failed" && props.stage === stage) {
    return "failed";
  }
  if (props.status === "running" && props.stage === stage) {
    return "current";
  }
  const currentIndex = props.stage ? stages.indexOf(props.stage) : -1;
  const stageIndex = stages.indexOf(stage);
  if (props.status === "completed" || (currentIndex > stageIndex && currentIndex >= 0)) {
    return "done";
  }
  return "idle";
}
</script>

<template>
  <div class="stage-rail" aria-label="Run stage rail">
    <div v-for="stageName in stages" :key="stageName" class="stage-item" :class="itemState(stageName)">
      <span class="stage-node">
        <Check v-if="itemState(stageName) === 'done'" :size="11" aria-hidden="true" />
        <AlertCircle v-else-if="itemState(stageName) === 'failed'" :size="11" aria-hidden="true" />
        <Circle v-else :size="9" aria-hidden="true" />
      </span>
      <span class="stage-label">{{ t(`stage.${stageName}`) }}</span>
      <span v-if="(stageCounts.get(stageName) ?? 0) > 1" class="stage-count">
        x{{ stageCounts.get(stageName) }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.stage-rail {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.stage-item {
  min-height: 24px;
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  color: var(--muted);
  font-size: 12px;
}

.stage-node {
  width: 14px;
  height: 14px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border-strong);
  border-radius: 50%;
  background: var(--panel);
}

.stage-item.done {
  color: var(--passed);
}

.stage-item.done .stage-node {
  border-color: var(--passed);
  background: var(--passed);
  color: #ffffff;
}

.stage-item.current {
  color: var(--running);
  font-weight: 700;
}

.stage-item.current .stage-node {
  border-color: var(--running);
  background: var(--running);
  color: #ffffff;
  animation: pulse 2.8s ease-in-out infinite;
}

.stage-item.failed {
  color: var(--failed);
  font-weight: 700;
}

.stage-item.failed .stage-node {
  border-color: var(--failed);
  background: var(--failed);
  color: #ffffff;
}

.stage-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stage-count {
  padding: 1px 6px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel);
  color: var(--muted-strong);
  font-family: var(--font-mono);
  font-size: 10px;
}
</style>
