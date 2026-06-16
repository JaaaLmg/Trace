<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ArrowRight, RefreshCw } from "@lucide/vue";
import { getExperimentMetrics, listExperiments } from "../api/experiments";
import { demoExperimentMetrics } from "../demo/staticRunFixture";
import { useLatestRequest } from "../composables/useLatestRequest";
import { useI18n } from "../i18n";
import type { ExperimentDefinition, ExperimentMetricsResponse } from "../types/api";
import type { DataSource } from "../types/ui";

const props = defineProps<{
  dataSource: DataSource;
}>();

const emit = defineEmits<{
  navigate: [hash: string];
}>();

const { t } = useI18n();

const metrics = ref<ExperimentMetricsResponse | null>(null);
const experiments = ref<ExperimentDefinition[]>([]);
const selectedExperimentId = ref<string | null>(null);
const loading = ref(false);
const errorMessage = ref<string | null>(null);
const usingFallback = ref(false);

const comparisonRequest = useLatestRequest();

// Only completed experiments have aggregatable metrics; draft/running/failed
// experiments are not offered for comparison.
const completedExperiments = computed(() => experiments.value.filter((experiment) => experiment.status === "completed"));
const noCompleted = computed(
  () => props.dataSource === "api" && !loading.value && !metrics.value && experiments.value.length > 0
);

const bestRow = computed(() => {
  const rows = metrics.value?.rows ?? [];
  return rows.reduce<(typeof rows)[number] | null>((best, row) => {
    if (!best) {
      return row;
    }
    if (row.capture_rate_mean > best.capture_rate_mean) {
      return row;
    }
    if (row.capture_rate_mean === best.capture_rate_mean && row.false_positive_rate < best.false_positive_rate) {
      return row;
    }
    return best;
  }, null);
});

const bugVariantCount = computed(() => Object.keys(metrics.value?.capture_matrix ?? {}).length);

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function numberText(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return t("common.none");
  }
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);
}

function experimentHref(): string {
  return metrics.value ? `#/experiments/${metrics.value.experiment.id}` : "#/experiments";
}

async function loadComparison() {
  const requestSeq = comparisonRequest.next();
  loading.value = true;
  errorMessage.value = null;
  usingFallback.value = false;
  try {
    if (props.dataSource === "demo") {
      experiments.value = [demoExperimentMetrics.experiment];
      selectedExperimentId.value = demoExperimentMetrics.experiment.id;
      metrics.value = demoExperimentMetrics;
      usingFallback.value = true;
      return;
    }
    const list = await listExperiments();
    if (!comparisonRequest.isCurrent(requestSeq)) {
      return;
    }
    experiments.value = list;
    // Pick a completed experiment only; if none, show the "no completed" empty state.
    const selected = list.find((experiment) => experiment.status === "completed") ?? null;
    if (!selected) {
      selectedExperimentId.value = null;
      metrics.value = null;
      return;
    }
    selectedExperimentId.value = selected.id;
    const next = await getExperimentMetrics(selected.id);
    if (!comparisonRequest.isCurrent(requestSeq)) {
      return;
    }
    metrics.value = next;
  } catch (error) {
    if (!comparisonRequest.isCurrent(requestSeq)) {
      return;
    }
    metrics.value = demoExperimentMetrics;
    usingFallback.value = true;
    errorMessage.value = error instanceof Error ? error.message : t("comparison.fallbackReason");
  } finally {
    if (comparisonRequest.isCurrent(requestSeq)) {
      loading.value = false;
    }
  }
}

async function selectExperiment(experimentId: string) {
  if (props.dataSource !== "api" || experimentId === metrics.value?.experiment.id) {
    return;
  }
  const requestSeq = comparisonRequest.next();
  selectedExperimentId.value = experimentId;
  loading.value = true;
  errorMessage.value = null;
  usingFallback.value = false;
  try {
    const next = await getExperimentMetrics(experimentId);
    if (!comparisonRequest.isCurrent(requestSeq)) {
      return;
    }
    metrics.value = next;
  } catch (error) {
    if (!comparisonRequest.isCurrent(requestSeq)) {
      return;
    }
    metrics.value = demoExperimentMetrics;
    usingFallback.value = true;
    errorMessage.value = error instanceof Error ? error.message : t("comparison.fallbackReason");
  } finally {
    if (comparisonRequest.isCurrent(requestSeq)) {
      loading.value = false;
    }
  }
}

onMounted(() => {
  void loadComparison();
});

watch(
  () => props.dataSource,
  () => {
    void loadComparison();
  }
);
</script>

<template>
  <main class="comparison-page app-page">
    <section class="comparison-head">
      <div>
        <p class="eyebrow">TRACE / COMPARISON</p>
        <h1>{{ t("comparison.title") }}</h1>
        <p>{{ t("comparison.subtitle") }}</p>
      </div>
      <div class="head-actions">
        <label v-if="props.dataSource === 'api' && completedExperiments.length > 1" class="experiment-select">
          <span>{{ t("comparison.pickExperiment") }}</span>
          <select :value="selectedExperimentId ?? ''" @change="selectExperiment(($event.target as HTMLSelectElement).value)">
            <option v-for="experiment in completedExperiments" :key="experiment.id" :value="experiment.id">
              {{ experiment.name }} ({{ t(`status.${experiment.status}`) }})
            </option>
          </select>
        </label>
        <button class="text-button" type="button" @click="loadComparison">
          <RefreshCw :size="16" aria-hidden="true" />
          {{ t("projects.refresh") }}
        </button>
        <button class="primary-action" type="button" @click="emit('navigate', experimentHref())">
          <ArrowRight :size="17" aria-hidden="true" />
          {{ t("comparison.openExperiment") }}
        </button>
      </div>
    </section>

    <p v-if="errorMessage" class="warning-banner">
      {{ t("comparison.apiFallback") }} {{ errorMessage }}
    </p>
    <p v-if="loading" class="mode-note">{{ t("comparison.loading") }}</p>

    <section v-if="metrics" class="source-strip">
      <article class="subtle-panel source-tile">
        <span>{{ t("experiments.source") }}</span>
        <strong>{{ usingFallback ? t("comparison.mockFallback") : metrics.data_source.label }}</strong>
      </article>
      <article class="subtle-panel source-tile">
        <span>{{ t("experiments.provider") }}</span>
        <strong>{{ metrics.data_source.provider_label ?? t("common.unknown") }}</strong>
        <small>{{ metrics.data_source.model_label ?? t("common.unknown") }}</small>
      </article>
      <article class="subtle-panel source-tile">
        <span>{{ t("experiments.repeat") }}</span>
        <strong>{{ metrics.experiment.repeat_count }}</strong>
        <small>{{ metrics.experiment.id }}</small>
      </article>
      <article class="subtle-panel source-tile">
        <span>{{ t("comparison.scope") }}</span>
        <strong>{{ bugVariantCount }}</strong>
        <small>{{ t("comparison.bugVariant") }}</small>
      </article>
    </section>

    <section v-if="metrics" class="comparison-summary">
      <article class="subtle-panel summary-panel">
        <span>{{ t("comparison.bestStrategy") }}</span>
        <strong>{{ bestRow?.strategy_name ?? t("common.none") }}</strong>
        <small v-if="bestRow">{{ percent(bestRow.capture_rate_mean) }} · {{ t("comparison.falsePositive") }} {{ percent(bestRow.false_positive_rate) }}</small>
      </article>
      <article class="subtle-panel summary-panel">
        <span>{{ t("experiments.strategies") }}</span>
        <strong>{{ metrics.rows.length }}</strong>
        <small>{{ metrics.experiment.strategy_version_ids.join(", ") }}</small>
      </article>
      <article class="subtle-panel summary-panel summary-wide">
        <span>{{ t("comparison.summaryOnly") }}</span>
        <strong>{{ t("comparison.openForEvidence") }}</strong>
        <button class="text-button" type="button" @click="emit('navigate', experimentHref())">
          <ArrowRight :size="15" aria-hidden="true" />
          {{ t("comparison.openExperiment") }}
        </button>
      </article>
    </section>

    <section v-if="metrics" class="table-shell comparison-table">
      <table>
        <thead>
          <tr>
            <th>{{ t("comparison.strategy") }}</th>
            <th>{{ t("comparison.capture") }}</th>
            <th>{{ t("comparison.falsePositive") }}</th>
            <th>{{ t("comparison.tokens") }}</th>
            <th>{{ t("comparison.toolCalls") }}</th>
            <th>{{ t("comparison.reflection") }}</th>
            <th>{{ t("experiments.costPerBug") }}</th>
            <th>{{ t("experiments.action") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in metrics.rows" :key="row.strategy_id">
            <td>
              <strong>{{ row.strategy_name }}</strong>
              <small class="block-mono">{{ row.strategy_id }}</small>
            </td>
            <td>{{ percent(row.capture_rate_mean) }} ({{ row.captured_mean }}/{{ row.total_in_scope }})</td>
            <td>{{ percent(row.false_positive_rate) }}</td>
            <td class="mono">{{ numberText(row.avg_tokens) }}</td>
            <td class="mono">{{ numberText(row.avg_tool_calls) }}</td>
            <td>{{ row.reflection_used ? t("common.yes") : t("common.no") }}</td>
            <td>{{ row.cost_per_captured_bug_status === "ok" ? numberText(row.cost_per_captured_bug) : t("experiments.noBugCaptured") }}</td>
            <td>
              <button class="text-button" type="button" @click="emit('navigate', experimentHref())">
                <ArrowRight :size="15" aria-hidden="true" />
                {{ t("comparison.viewEvidence") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="!loading && !metrics" class="empty-state subtle-panel">
      <h2>{{ noCompleted ? t("comparison.noCompletedTitle") : t("comparison.emptyTitle") }}</h2>
      <p>{{ noCompleted ? t("comparison.noCompletedBody") : t("comparison.emptyBody") }}</p>
      <button class="primary-action" type="button" @click="emit('navigate', '#/experiments')">
        <ArrowRight :size="17" aria-hidden="true" />
        {{ t("experiments.title") }}
      </button>
    </section>
  </main>
</template>

<style scoped>
.comparison-head {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
  padding: 18px 0 24px;
  border-bottom: 1px solid var(--border);
}

.comparison-head h1 {
  margin: 8px 0 10px;
}

.comparison-head p {
  max-width: 760px;
  font-family: var(--font-serif);
}

.head-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.experiment-select {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--muted);
}

.experiment-select span {
  font-family: var(--font-mono);
  text-transform: uppercase;
}

.experiment-select select {
  min-height: 32px;
  max-width: 240px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--ink);
  font-size: 13px;
}

.warning-banner {
  margin: 18px 0 0;
  padding: 10px 12px;
  border: 1px solid rgba(138, 90, 0, 0.2);
  border-radius: 7px;
  background: var(--running-bg);
  color: var(--running);
}

.source-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.source-tile,
.summary-panel {
  display: grid;
  gap: 3px;
  padding: 14px;
}

.source-tile span,
.summary-panel span,
.source-tile small,
.summary-panel small,
.block-mono {
  overflow-wrap: anywhere;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
}

.source-tile span,
.summary-panel span {
  text-transform: uppercase;
}

.summary-panel strong {
  overflow-wrap: anywhere;
  font-size: 20px;
  line-height: 1.25;
}

.summary-panel .text-button {
  justify-self: start;
  margin-top: 6px;
}

.comparison-summary {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 0.75fr) minmax(260px, 1fr);
  gap: 12px;
  margin-top: 12px;
}

.comparison-table {
  margin-top: 18px;
}

.empty-state {
  display: grid;
  gap: 16px;
  margin-top: 28px;
}

.empty-state {
  justify-items: start;
  padding: 22px;
}

@media (max-width: 900px) {
  .comparison-head,
  .source-strip,
  .comparison-summary {
    grid-template-columns: 1fr;
  }

  .comparison-head {
    display: grid;
  }
}
</style>
