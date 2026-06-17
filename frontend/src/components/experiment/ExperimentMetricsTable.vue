<script setup lang="ts">
import { useI18n } from "../../i18n";
import type { ExperimentMetricRow } from "../../types/api";

defineProps<{
  rows: ExperimentMetricRow[];
}>();

const { t } = useI18n();

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function numberText(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return t("common.none");
  }
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);
}

function metricStatus(row: ExperimentMetricRow): string {
  if (row.metric_status === "invalid_test_set") {
    return `${t("comparison.metricStatusInvalid")} (${row.invalid_test_set_count})`;
  }
  if (row.metric_status === "evaluable_zero_capture") {
    return t("comparison.metricStatusZero");
  }
  return t("comparison.metricStatusOk");
}

function costText(row: ExperimentMetricRow): string {
  if (row.metric_status === "invalid_test_set") {
    return t("comparison.metricStatusInvalid");
  }
  return row.cost_per_captured_bug_status === "ok" ? numberText(row.cost_per_captured_bug) : t("experiments.noBugCaptured");
}
</script>

<template>
  <section class="section-stack">
    <div>
      <p class="eyebrow">METRICS</p>
      <h2>{{ t("comparison.title") }}</h2>
    </div>
    <div class="table-shell">
      <table>
        <thead>
          <tr>
            <th>{{ t("comparison.strategy") }}</th>
            <th>{{ t("comparison.capture") }}</th>
            <th>{{ t("comparison.falsePositive") }}</th>
            <th>{{ t("comparison.metricStatus") }}</th>
            <th>{{ t("experiments.stddev") }}</th>
            <th>{{ t("comparison.tokens") }}</th>
            <th>{{ t("comparison.toolCalls") }}</th>
            <th>{{ t("experiments.costPerBug") }}</th>
            <th>{{ t("experiments.model") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.strategy_id">
            <td>
              <strong>{{ row.strategy_name }}</strong>
              <small class="block-mono">{{ row.strategy_id }}</small>
            </td>
            <td>{{ percent(row.capture_rate_mean) }} ({{ row.captured_mean }}/{{ row.total_in_scope }})</td>
            <td>{{ percent(row.false_positive_rate) }}</td>
            <td>
              <span :class="['metric-status', row.metric_status]">{{ metricStatus(row) }}</span>
            </td>
            <td>{{ numberText(row.capture_rate_std) }}</td>
            <td class="mono">{{ numberText(row.avg_tokens) }}</td>
            <td class="mono">{{ numberText(row.avg_tool_calls) }}</td>
            <td>{{ costText(row) }}</td>
            <td>
              <span class="model-cell">
                <strong>{{ row.llm_display.provider }}</strong>
                <small>{{ row.llm_display.model }}</small>
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.section-stack {
  display: grid;
  gap: 14px;
  margin-top: 18px;
}

.model-cell {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.model-cell small,
.block-mono {
  overflow-wrap: anywhere;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
}

.metric-status {
  display: inline-flex;
  min-height: 22px;
  align-items: center;
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--pass-bg);
  color: var(--pass);
  font-family: var(--font-mono);
  font-size: 11px;
}

.metric-status.invalid_test_set {
  background: var(--fail-bg);
  color: var(--fail);
}

.metric-status.evaluable_zero_capture {
  background: var(--running-bg);
  color: var(--running);
}
</style>
