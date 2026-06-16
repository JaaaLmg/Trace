<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ArrowRight, Beaker, Play, RefreshCw, ServerCrash } from "@lucide/vue";
import { listExperiments, runExperiment } from "../api/experiments";
import { demoExperimentMetrics } from "../demo/staticRunFixture";
import { useLatestRequest } from "../composables/useLatestRequest";
import { useI18n } from "../i18n";
import type { ExperimentDefinition } from "../types/api";
import type { DataSource } from "../types/ui";

const props = defineProps<{
  dataSource: DataSource;
}>();

const emit = defineEmits<{
  navigate: [hash: string];
}>();

const { t } = useI18n();

const experiments = ref<ExperimentDefinition[]>([]);
const loading = ref(false);
const startingId = ref<string | null>(null);
const errorMessage = ref<string | null>(null);

const listRequest = useLatestRequest();

const completedCount = computed(() => experiments.value.filter((experiment) => experiment.status === "completed").length);

// llm_override is only the override layer; the resolved final provider/model is
// frozen per clean run's strategy_snapshot (see Experiment Detail). On the list we
// show the override when present, otherwise "strategy default" — not "unknown".
function providerLabel(experiment: ExperimentDefinition): string {
  return experiment.llm_override?.provider ?? t("experiments.strategyDefault");
}

function modelLabel(experiment: ExperimentDefinition): string {
  return experiment.llm_override?.model ?? t("experiments.strategyDefault");
}

function formatDate(value: string | null): string {
  if (!value) {
    return t("common.none");
  }
  return new Date(value).toLocaleString();
}

function openExperiment(experimentId: string) {
  emit("navigate", `#/experiments/${experimentId}`);
}

async function loadExperiments() {
  const requestSeq = listRequest.next();
  loading.value = true;
  errorMessage.value = null;
  try {
    const next = props.dataSource === "demo" ? [demoExperimentMetrics.experiment] : await listExperiments();
    if (!listRequest.isCurrent(requestSeq)) {
      return;
    }
    experiments.value = next;
  } catch (error) {
    if (!listRequest.isCurrent(requestSeq)) {
      return;
    }
    experiments.value = [];
    errorMessage.value = error instanceof Error ? error.message : t("experiments.loadFailed");
  } finally {
    if (listRequest.isCurrent(requestSeq)) {
      loading.value = false;
    }
  }
}

async function startExperiment(experiment: ExperimentDefinition) {
  if (props.dataSource !== "api") {
    openExperiment(experiment.id);
    return;
  }
  startingId.value = experiment.id;
  errorMessage.value = null;
  try {
    const updated = await runExperiment(experiment.id);
    experiments.value = experiments.value.map((item) => (item.id === updated.id ? updated : item));
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t("experiments.startFailed");
  } finally {
    startingId.value = null;
  }
}

onMounted(() => {
  void loadExperiments();
});

watch(
  () => props.dataSource,
  () => {
    void loadExperiments();
  }
);
</script>

<template>
  <main class="experiment-page app-page">
    <section class="experiment-head">
      <div>
        <p class="eyebrow">TRACE / EXPERIMENTS</p>
        <h1>{{ t("experiments.title") }}</h1>
        <p>{{ t("experiments.subtitle") }}</p>
      </div>
      <div class="head-actions">
        <button class="text-button" type="button" @click="loadExperiments">
          <RefreshCw :size="16" aria-hidden="true" />
          {{ t("projects.refresh") }}
        </button>
      </div>
    </section>

    <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

    <section class="summary-strip">
      <article class="subtle-panel summary-tile">
        <span>{{ t("experiments.total") }}</span>
        <strong>{{ experiments.length }}</strong>
      </article>
      <article class="subtle-panel summary-tile">
        <span>{{ t("experiments.completed") }}</span>
        <strong>{{ completedCount }}</strong>
      </article>
      <article class="subtle-panel summary-tile">
        <span>{{ t("experiments.source") }}</span>
        <strong>{{ props.dataSource === "demo" ? t("app.demo") : t("app.api") }}</strong>
      </article>
    </section>

    <section class="table-shell experiment-table">
      <table>
        <thead>
          <tr>
            <th>{{ t("experiments.name") }}</th>
            <th>{{ t("experiments.dataset") }}</th>
            <th>{{ t("experiments.status") }}</th>
            <th>{{ t("experiments.strategies") }}</th>
            <th>{{ t("experiments.repeat") }}</th>
            <th>{{ t("experiments.model") }}</th>
            <th>{{ t("experiments.time") }}</th>
            <th>{{ t("experiments.action") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="experiment in experiments" :key="experiment.id">
            <td>
              <button class="link-button" type="button" @click="openExperiment(experiment.id)">
                <Beaker :size="16" aria-hidden="true" />
                <span>
                  <strong>{{ experiment.name }}</strong>
                  <small>{{ experiment.id }}</small>
                </span>
              </button>
            </td>
            <td class="mono">{{ experiment.dataset_id }}</td>
            <td>
              <span class="status-pill" :data-status="experiment.status">{{ t(`status.${experiment.status}`) }}</span>
            </td>
            <td>{{ experiment.strategy_version_ids.length }}</td>
            <td>{{ experiment.repeat_count }}</td>
            <td>
              <span class="model-cell">
                <strong>{{ providerLabel(experiment) }}</strong>
                <small>{{ modelLabel(experiment) }}</small>
              </span>
            </td>
            <td>
              <span class="time-cell">
                <small>{{ t("experiments.started") }}: {{ formatDate(experiment.started_at) }}</small>
                <small>{{ t("experiments.finished") }}: {{ formatDate(experiment.finished_at) }}</small>
              </span>
            </td>
            <td>
              <span class="row-actions">
                <button class="text-button" type="button" @click="openExperiment(experiment.id)">
                  <ArrowRight :size="15" aria-hidden="true" />
                  {{ t("experiments.open") }}
                </button>
                <button
                  v-if="props.dataSource === 'api' && ['draft', 'queued', 'cancelled'].includes(experiment.status)"
                  class="text-button"
                  type="button"
                  :disabled="startingId === experiment.id"
                  @click="startExperiment(experiment)"
                >
                  <Play :size="15" aria-hidden="true" />
                  {{ startingId === experiment.id ? t("experiments.starting") : t("run.start") }}
                </button>
              </span>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!loading && experiments.length === 0" class="empty-state">
        <ServerCrash :size="24" aria-hidden="true" />
        <h2>{{ t("experiments.emptyTitle") }}</h2>
        <p>{{ t("experiments.emptyBody") }}</p>
      </div>
      <p v-if="loading" class="mode-note">{{ t("experiments.loading") }}</p>
    </section>
  </main>
</template>

<style scoped>
.experiment-head {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
  padding: 18px 0 24px;
  border-bottom: 1px solid var(--border);
}

.experiment-head h1 {
  margin: 8px 0 10px;
}

.experiment-head p {
  max-width: 760px;
  font-family: var(--font-serif);
}

.head-actions,
.row-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.summary-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.summary-tile {
  display: grid;
  gap: 3px;
  padding: 14px;
}

.summary-tile span,
.time-cell small,
.model-cell small {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
}

.summary-tile strong {
  font-size: 24px;
  line-height: 1.2;
}

.experiment-table {
  margin-top: 18px;
}

.link-button {
  display: inline-flex;
  align-items: flex-start;
  gap: 8px;
  padding: 0;
  border: 0;
  background: transparent;
  text-align: left;
}

.link-button:hover {
  background: transparent;
  color: var(--ink);
}

.link-button span,
.model-cell,
.time-cell {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.link-button small,
.time-cell small {
  overflow-wrap: anywhere;
}

.status-pill {
  display: inline-flex;
  min-height: 24px;
  align-items: center;
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel-soft);
  color: var(--muted-strong);
  font-size: 12px;
  font-weight: 700;
}

.status-pill[data-status="completed"] {
  border-color: rgba(47, 107, 63, 0.24);
  background: var(--passed-bg);
  color: var(--passed);
}

.status-pill[data-status="running"],
.status-pill[data-status="queued"] {
  border-color: rgba(138, 90, 0, 0.2);
  background: var(--running-bg);
  color: var(--running);
}

.status-pill[data-status="failed"],
.status-pill[data-status="cancelled"] {
  border-color: rgba(159, 58, 47, 0.24);
  background: var(--failed-bg);
  color: var(--failed);
}

.empty-state {
  display: grid;
  gap: 10px;
  justify-items: center;
  padding: 34px;
  text-align: center;
}

@media (max-width: 900px) {
  .experiment-head,
  .summary-strip {
    grid-template-columns: 1fr;
  }

  .experiment-head {
    display: grid;
  }
}
</style>
