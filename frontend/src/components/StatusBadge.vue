<script setup lang="ts">
import { AlertTriangle, CheckCircle2, Circle, Clock3, Loader2, XCircle } from "@lucide/vue";
import { useI18n } from "../i18n";

const props = defineProps<{
  value: string | null | undefined;
  tone?: "status" | "step";
  pulse?: boolean;
}>();

const { t } = useI18n();

function normalized(value: string | null | undefined): string {
  return (value ?? "unknown").toLowerCase();
}

function badgeClass(value: string | null | undefined): string {
  const status = normalized(value);
  if (["completed", "passed", "ok", "matched", "adopted"].includes(status)) {
    return "passed";
  }
  if (["queued", "running", "reflecting", "reflection"].includes(status)) {
    return "running";
  }
  if (["failed", "error", "cancelled", "unmatched", "rejected"].includes(status)) {
    return "failed";
  }
  if (["tool_call", "tool", "system", "skipped", "observation"].includes(status)) {
    return "tool";
  }
  if (["generation", "plan", "report"].includes(status)) {
    return "generation";
  }
  return "muted";
}

function readable(value: string | null | undefined): string {
  const status = normalized(value);
  const label = t(`status.${status}`);
  return label === `status.${status}` ? status : label;
}

const iconSize = 14;
</script>

<template>
  <span class="status-badge" :class="[badgeClass(props.value), { pulse: props.pulse }]">
    <CheckCircle2 v-if="badgeClass(props.value) === 'passed'" :size="iconSize" aria-hidden="true" />
    <Loader2 v-else-if="badgeClass(props.value) === 'running'" :size="iconSize" aria-hidden="true" />
    <XCircle v-else-if="badgeClass(props.value) === 'failed'" :size="iconSize" aria-hidden="true" />
    <Clock3 v-else-if="badgeClass(props.value) === 'tool'" :size="iconSize" aria-hidden="true" />
    <AlertTriangle v-else-if="badgeClass(props.value) === 'generation'" :size="iconSize" aria-hidden="true" />
    <Circle v-else :size="iconSize" aria-hidden="true" />
    <span>{{ readable(props.value) }}</span>
  </span>
</template>

<style scoped>
.status-badge {
  min-height: 28px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 4px 9px;
  border: 1px solid transparent;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  font-feature-settings: "tnum" 1;
  white-space: nowrap;
}

.status-badge.passed {
  border-color: rgba(47, 107, 63, 0.24);
  background: var(--passed-bg);
  color: var(--passed);
}

.status-badge.running {
  border-color: rgba(138, 90, 0, 0.24);
  background: var(--running-bg);
  color: var(--running);
}

.status-badge.failed {
  border-color: rgba(159, 58, 47, 0.24);
  background: var(--failed-bg);
  color: var(--failed);
}

.status-badge.tool {
  border-color: rgba(49, 95, 125, 0.24);
  background: var(--tool-bg);
  color: var(--tool);
}

.status-badge.generation {
  border-color: rgba(103, 80, 138, 0.24);
  background: var(--generation-bg);
  color: var(--generation);
}

.status-badge.muted {
  border-color: rgba(95, 90, 82, 0.18);
  background: rgba(95, 90, 82, 0.1);
  color: var(--muted-strong);
}

.status-badge.pulse svg {
  animation: pulse 2.8s ease-in-out infinite;
  border-radius: 999px;
}
</style>
