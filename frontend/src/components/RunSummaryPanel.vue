<script setup lang="ts">
import { computed } from "vue";
import { AlertTriangle, Database, GitBranch, Timer } from "@lucide/vue";
import { useI18n } from "../i18n";
import type { RunBundle } from "../types/api";
import StageRail from "./StageRail.vue";
import StatusBadge from "./StatusBadge.vue";

const props = defineProps<{
  bundle: RunBundle;
}>();

const { t } = useI18n();
const run = computed(() => props.bundle.run);

const pytest = computed(() => {
  const summary = run.value.pytest_summary;
  return {
    passed: Number(summary.passed ?? 0),
    failed: Number(summary.failed ?? 0),
    skipped: Number(summary.skipped ?? 0),
    collected: Number(summary.collected ?? 0)
  };
});

const modelName = computed(() => {
  const snapshot = run.value.strategy_snapshot;
  return String(snapshot.model_name ?? props.bundle.strategy?.model_name ?? "unknown");
});

const strategyName = computed(() => {
  const snapshot = run.value.strategy_snapshot;
  return String(snapshot.name ?? props.bundle.strategy?.name ?? run.value.strategy_version_id);
});
</script>

<template>
  <aside class="summary-rail" aria-label="Run Summary">
    <div class="summary-block">
      <p class="summary-label">{{ t("summary.status") }}</p>
      <div class="status-line">
        <StatusBadge :value="run.status" :pulse="run.status === 'running'" />
        <span v-if="run.stage" class="stage-pill">{{ run.stage }}</span>
      </div>
      <p v-if="run.error_message" class="error-message">
        <AlertTriangle :size="14" aria-hidden="true" />
        {{ run.error_message }}
      </p>
    </div>

    <div class="summary-block">
      <p class="summary-label">{{ t("summary.strategy") }}</p>
      <p class="summary-value">{{ strategyName }}</p>
      <p class="summary-muted">
        <GitBranch :size="13" aria-hidden="true" />
        {{ modelName }}
      </p>
    </div>

    <div class="summary-block">
      <p class="summary-label">{{ t("summary.pytest") }}</p>
      <div class="metric-grid">
        <div class="metric">
          <strong>{{ pytest.passed }}</strong>
          <span>{{ t("summary.passed") }}</span>
        </div>
        <div class="metric failed">
          <strong>{{ pytest.failed }}</strong>
          <span>{{ t("summary.failed") }}</span>
        </div>
        <div class="metric">
          <strong>{{ pytest.collected }}</strong>
          <span>{{ t("summary.collected") }}</span>
        </div>
        <div class="metric">
          <strong>{{ pytest.skipped }}</strong>
          <span>{{ t("summary.skipped") }}</span>
        </div>
      </div>
    </div>

    <div class="summary-block">
      <p class="summary-label">{{ t("summary.workload") }}</p>
      <div class="metric-grid">
        <div class="metric">
          <strong>{{ run.total_tokens }}</strong>
          <span>tokens</span>
        </div>
        <div class="metric">
          <strong>{{ run.tool_call_count }}</strong>
          <span>{{ t("summary.toolCalls") }}</span>
        </div>
      </div>
      <p class="summary-muted footnote">
        <Timer :size="13" aria-hidden="true" />
        {{ t("summary.costNote") }}
      </p>
    </div>

    <div class="summary-block">
      <p class="summary-label">{{ t("summary.stages") }}</p>
      <StageRail :status="run.status" :stage="run.stage" :trace-steps="bundle.traceSteps" />
    </div>

    <div class="summary-block">
      <p class="summary-label">{{ t("summary.anchor") }}</p>
      <p class="summary-muted">
        <Database :size="13" aria-hidden="true" />
        {{ run.project_snapshot_id }}
      </p>
      <p class="summary-muted mono">{{ run.id }}</p>
    </div>
  </aside>
</template>

<style scoped>
.summary-rail {
  position: relative;
  padding: 18px;
  border-right: 1px solid var(--border);
  background: rgba(251, 250, 247, 0.92);
}

.summary-block + .summary-block {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--border);
}

.summary-label {
  margin: 0 0 8px;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
}

.summary-value {
  color: var(--ink);
  font-weight: 700;
}

.summary-muted {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  margin-top: 7px;
  color: var(--muted);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.status-line {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.stage-pill {
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel);
  color: var(--muted-strong);
  font-family: var(--font-mono);
  font-size: 11px;
}

.error-message {
  display: flex;
  gap: 6px;
  margin-top: 10px;
  color: var(--failed);
  font-size: 12px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.metric {
  min-height: 66px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.64);
}

.metric strong {
  display: block;
  color: var(--ink);
  font-family: var(--font-serif);
  font-size: 23px;
  line-height: 1.1;
  font-feature-settings: "tnum" 1;
}

.metric span {
  color: var(--muted);
  font-size: 12px;
}

.metric.failed strong {
  color: var(--failed);
}

.footnote {
  align-items: flex-start;
}

@media (max-width: 1200px) {
  .summary-rail {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
    border-right: 0;
    border-bottom: 1px solid var(--border);
  }

  .summary-block + .summary-block {
    margin-top: 0;
    padding-top: 0;
    border-top: 0;
  }
}

@media (max-width: 760px) {
  .summary-rail {
    grid-template-columns: 1fr;
  }
}
</style>
