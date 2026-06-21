<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Activity, ArrowLeft, Bot, Database, Download, FileText, Footprints, Play, RefreshCw } from "@lucide/vue";
import {
  cleanupExperiment,
  cleanupExperimentReplayCache,
  getExperiment,
  getExperimentArtifactInventory,
  getExperimentMetrics,
  getExperimentProgress,
  runExperiment,
  getExperimentReplayCache
} from "../api/experiments";
import CaptureMatrix from "../components/experiment/CaptureMatrix.vue";
import CleanRunTable from "../components/experiment/CleanRunTable.vue";
import EvaluationEventTimeline from "../components/experiment/EvaluationEventTimeline.vue";
import ExperimentMetricsTable from "../components/experiment/ExperimentMetricsTable.vue";
import ReplayEvidencePanel from "../components/experiment/ReplayEvidencePanel.vue";
import { demoExperimentMetrics } from "../demo/staticRunFixture";
import { useLatestRequest } from "../composables/useLatestRequest";
import { useI18n } from "../i18n";
import type { ArtifactContract, ExperimentDefinition, ExperimentMetricsResponse, ExperimentProgressOut, JsonObject } from "../types/api";
import type { DataSource } from "../types/ui";

const props = defineProps<{
  experimentId: string;
  dataSource: DataSource;
}>();

const emit = defineEmits<{
  navigate: [hash: string];
}>();

const { t } = useI18n();

const metrics = ref<ExperimentMetricsResponse | null>(null);
const experiment = ref<ExperimentDefinition | null>(null);
const loading = ref(false);
const errorMessage = ref<string | null>(null);
const selectedReplayId = ref<string | null>(null);
const cleanupMessage = ref<string | null>(null);
const lifecycle = ref<Record<string, unknown> | null>(null);
const cacheInfo = ref<Record<string, unknown> | null>(null);
const workspaceCleanupPreview = ref<CleanupResult | null>(null);
const cacheCleanupPreview = ref<CleanupResult | null>(null);
const progress = ref<ExperimentProgressOut | null>(null);
const progressError = ref<string | null>(null);
const starting = ref(false);
let progressTimer: number | null = null;

const terminalExperimentStatuses = new Set(["completed", "failed", "cancelled"]);
const activeExperimentStatuses = new Set(["queued", "running"]);
const startableExperimentStatuses = new Set(["draft"]);

type CleanupCandidate = {
  replay_id?: string;
  path?: string;
  status?: string;
  cache_status?: string;
  exists?: boolean | null;
  safe?: boolean;
  error?: string;
  source_replay_id?: string | null;
  reused_from_replay_id?: string | null;
};

type CleanupResult = {
  experiment_id?: string;
  dry_run?: boolean;
  keep_failed?: boolean;
  candidate_count?: number;
  deleted_count?: number;
  candidates?: CleanupCandidate[];
  deleted?: CleanupCandidate[];
};

const canStartExperiment = computed(() => {
  const status = experiment.value?.status ?? metrics.value?.experiment.status;
  return props.dataSource === "api" && Boolean(status && startableExperimentStatuses.has(status));
});

const progressPercent = computed(() => {
  const total = progress.value?.clean_runs_total_estimate ?? 0;
  if (total <= 0) {
    return progress.value && activeExperimentStatuses.has(progress.value.status) ? 8 : 0;
  }
  const completed = progress.value?.clean_runs_completed ?? 0;
  const raw = Math.round((completed / total) * 100);
  return Math.max(activeExperimentStatuses.has(progress.value?.status ?? "") ? 6 : 0, Math.min(raw, 100));
});

const progressVisible = computed(() => {
  const status = progress.value?.status ?? experiment.value?.status ?? metrics.value?.experiment.status;
  return props.dataSource === "api" && (activeExperimentStatuses.has(status ?? "") || (!metrics.value && Boolean(experiment.value)));
});

const progressStatusText = computed(() => {
  const status = progress.value?.status ?? experiment.value?.status;
  return status ? t(`status.${status}`) : t("common.unknown");
});

const currentStrategyText = computed(() => {
  if (!progress.value) {
    return t("common.none");
  }
  const index = progress.value.current_strategy_index;
  const total = progress.value.strategy_count;
  const id = progress.value.current_strategy_version_id;
  if (!index || !total) {
    return id ?? t("common.none");
  }
  return `${index} / ${total}${id ? ` · ${id}` : ""}`;
});

const currentStepText = computed(() => {
  const step = progress.value?.latest_trace_step;
  if (!step) {
    return progress.value?.run_stage ?? t("experiments.preparing");
  }
  return step.tool_name ? `${step.name} · ${step.tool_name}` : step.name;
});

const currentUnitText = computed(() => {
  if (!progress.value) {
    return t("common.none");
  }
  const task = progress.value.current_eval_task_id ?? t("experiments.taskPending");
  const repeat =
    progress.value.current_repeat_index === null || progress.value.current_repeat_index === undefined
      ? t("experiments.repeatPending")
      : `${t("experiments.repeatShort")} ${progress.value.current_repeat_index + 1} / ${progress.value.repeat_count}`;
  return `${task} · ${repeat}`;
});

const metricsRequest = useLatestRequest();

function formatDate(value: string | null): string {
  if (!value) {
    return t("common.none");
  }
  return new Date(value).toLocaleString();
}

function selectReplay(replayId: string) {
  selectedReplayId.value = replayId;
}

function openCleanRun(runId: string) {
  emit("navigate", `#/runs/${runId}`);
}

async function loadMetrics(options: { preserveReplaySelection?: boolean } = {}) {
  const previousReplayId = selectedReplayId.value;
  const requestSeq = metricsRequest.next();
  loading.value = true;
  errorMessage.value = null;
  if (!options.preserveReplaySelection) {
    selectedReplayId.value = null;
  }
  try {
    const [nextExperiment, nextMetrics] =
      props.dataSource === "demo"
        ? [demoExperimentMetrics.experiment, demoExperimentMetrics]
        : await Promise.all([getExperiment(props.experimentId), getExperimentMetrics(props.experimentId)]);
    if (!metricsRequest.isCurrent(requestSeq)) {
      return;
    }
    experiment.value = nextExperiment;
    metrics.value = nextMetrics;
    if (options.preserveReplaySelection && previousReplayId) {
      const replayExists = nextMetrics.replay_runs.some((replay) => replay.id === previousReplayId);
      selectedReplayId.value = replayExists ? previousReplayId : null;
    }
  } catch (error) {
    if (!metricsRequest.isCurrent(requestSeq)) {
      return;
    }
    metrics.value = null;
    errorMessage.value = error instanceof Error ? error.message : t("experiments.metricsFailed");
    if (props.dataSource === "api") {
      try {
        experiment.value = await getExperiment(props.experimentId);
      } catch {
        experiment.value = null;
      }
    }
  } finally {
    if (metricsRequest.isCurrent(requestSeq)) {
      loading.value = false;
    }
  }
}

function countText(values: Record<string, number> | undefined): string {
  if (!values) {
    return t("common.none");
  }
  const pairs = Object.entries(values);
  return pairs.length ? pairs.map(([key, value]) => `${key}: ${value}`).join(" / ") : t("common.none");
}

function candidateText(value: string | null | undefined): string {
  return value ?? t("common.none");
}

function candidateStatusText(value: string | null | undefined): string {
  return value ?? t("common.unknown");
}

function candidateExistsText(value: boolean | null | undefined): string {
  if (value === true) {
    return t("common.yes");
  }
  if (value === false) {
    return t("common.no");
  }
  return t("common.unknown");
}

function jsonText(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

function downloadMetricsJson() {
  if (!metrics.value) {
    return;
  }
  const blob = new Blob([JSON.stringify(metrics.value, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${metrics.value.experiment.id}.metrics.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function reportLikeArtifacts(): ArtifactContract[] {
  const artifacts = metrics.value?.artifacts ?? [];
  return artifacts.filter((artifact) =>
    artifact.artifact_type === "report_json" ||
    artifact.artifact_type === "report_markdown" ||
    artifact.artifact_type === "experiment_metrics"
  );
}

function firstRunIdForReport(): string | null {
  return metrics.value?.clean_runs[0]?.clean_run_id ?? null;
}

function openFirstRunReport() {
  const runId = firstRunIdForReport();
  if (runId) {
    emit("navigate", `#/runs/${runId}`);
  }
}

async function startExperiment() {
  if (!canStartExperiment.value || starting.value) {
    return;
  }
  starting.value = true;
  errorMessage.value = null;
  try {
    const updated = await runExperiment(props.experimentId);
    experiment.value = updated;
    if (metrics.value) {
      metrics.value = { ...metrics.value, experiment: updated };
    }
    await loadProgress();
    startProgressPolling();
    await loadMetrics({ preserveReplaySelection: true });
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t("experiments.startFailed");
  } finally {
    starting.value = false;
  }
}

async function runCleanup(dryRun: boolean) {
  if (props.dataSource !== "api") {
    return;
  }
  cleanupMessage.value = null;
  try {
    if (!dryRun && !workspaceCleanupPreview.value) {
      cleanupMessage.value = t("experiments.cleanupPreviewRequired");
      return;
    }
    if (!dryRun && !window.confirm(t("experiments.cleanupConfirm"))) {
      return;
    }
    const result = (await cleanupExperiment(props.experimentId, { dry_run: dryRun, keep_failed: true })) as CleanupResult;
    if (dryRun) {
      workspaceCleanupPreview.value = result;
    }
    cleanupMessage.value = dryRun
      ? t("experiments.cleanupDryRunMessage", { count: String(result.candidate_count ?? 0) })
      : t("experiments.cleanupCompletedMessage", { count: String(result.deleted_count ?? 0) });
    if (!dryRun) {
      workspaceCleanupPreview.value = null;
      await loadMetrics();
      await loadLifecycle();
    }
  } catch (error) {
    cleanupMessage.value = error instanceof Error ? error.message : t("experiments.cleanupFailed");
  }
}

function stopProgressPolling() {
  if (progressTimer !== null) {
    window.clearInterval(progressTimer);
    progressTimer = null;
  }
}

async function loadProgress({ refreshMetricsOnTerminal = false } = {}) {
  if (props.dataSource !== "api") {
    progress.value = null;
    return;
  }
  try {
    const nextProgress = await getExperimentProgress(props.experimentId);
    progress.value = nextProgress;
    progressError.value = null;
    if (terminalExperimentStatuses.has(nextProgress.status)) {
      stopProgressPolling();
      if (refreshMetricsOnTerminal) {
        await loadMetrics({ preserveReplaySelection: true });
      }
    }
  } catch (error) {
    progressError.value = error instanceof Error ? error.message : "Progress load failed.";
  }
}

function startProgressPolling() {
  stopProgressPolling();
  if (props.dataSource !== "api") {
    return;
  }
  void loadProgress();
  progressTimer = window.setInterval(() => {
    void loadProgress({ refreshMetricsOnTerminal: true });
  }, 2500);
}

async function loadLifecycle() {
  if (props.dataSource !== "api") {
    return;
  }
  try {
    const [inventory, cache] = await Promise.all([
      getExperimentArtifactInventory(props.experimentId),
      getExperimentReplayCache(props.experimentId)
    ]);
    lifecycle.value = inventory;
    cacheInfo.value = cache;
  } catch (error) {
    cleanupMessage.value = error instanceof Error ? error.message : t("experiments.lifecycleLoadFailed");
  }
}

async function runCacheCleanup(dryRun: boolean) {
  if (props.dataSource !== "api") {
    return;
  }
  try {
    if (!dryRun && !cacheCleanupPreview.value) {
      cleanupMessage.value = t("experiments.cacheCleanupPreviewRequired");
      return;
    }
    if (!dryRun && !window.confirm(t("experiments.cacheCleanupConfirm"))) {
      return;
    }
    const result = (await cleanupExperimentReplayCache(props.experimentId, { dry_run: dryRun })) as CleanupResult;
    if (dryRun) {
      cacheCleanupPreview.value = result;
    }
    cleanupMessage.value = dryRun
      ? t("experiments.cacheCleanupDryRunMessage", { count: String(result.candidate_count ?? 0) })
      : t("experiments.cacheCleanupCompletedMessage", { count: String(result.deleted_count ?? 0) });
    if (!dryRun) {
      cacheCleanupPreview.value = null;
    }
    await loadLifecycle();
  } catch (error) {
    cleanupMessage.value = error instanceof Error ? error.message : t("experiments.cacheCleanupFailed");
  }
}

onMounted(() => {
  void loadMetrics();
  void loadLifecycle();
  startProgressPolling();
});

watch(
  () => [props.experimentId, props.dataSource],
  () => {
    progress.value = null;
    progressError.value = null;
    void loadMetrics();
    void loadLifecycle();
    startProgressPolling();
  }
);

onBeforeUnmount(() => {
  stopProgressPolling();
});
</script>

<template>
  <main class="experiment-detail app-page">
    <section class="detail-head">
      <button class="text-button" type="button" @click="emit('navigate', '#/experiments')">
        <ArrowLeft :size="16" aria-hidden="true" />
        {{ t("experiments.back") }}
      </button>
      <button
        v-if="canStartExperiment"
        class="text-button"
        type="button"
        :disabled="starting"
        @click="startExperiment"
      >
        <Play :size="16" aria-hidden="true" />
        {{ starting ? t("experiments.starting") : t("run.start") }}
      </button>
      <button class="text-button" type="button" @click="() => loadMetrics()">
        <RefreshCw :size="16" aria-hidden="true" />
        {{ t("projects.refresh") }}
      </button>
    </section>

    <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>
    <p v-if="cleanupMessage" class="mode-note">{{ cleanupMessage }}</p>
    <p v-if="progressError" class="mode-note">{{ progressError }}</p>
    <p v-if="loading" class="mode-note">{{ t("experiments.loadingMetrics") }}</p>

    <section v-if="progressVisible" class="progress-band subtle-panel" aria-live="polite">
      <div class="progress-main">
        <div class="progress-title">
          <span class="live-dot" aria-hidden="true"></span>
          <span>{{ progressStatusText }}</span>
          <small>{{ formatDate(progress?.updated_at ?? null) }}</small>
        </div>
        <div class="progress-bar" aria-hidden="true">
          <span :style="{ width: `${progressPercent}%` }"></span>
        </div>
      </div>
      <div class="progress-grid">
        <article>
          <Activity :size="16" aria-hidden="true" />
          <span>{{ t("experiments.progressStrategy") }}</span>
          <strong>{{ currentStrategyText }}</strong>
        </article>
        <article>
          <Bot :size="16" aria-hidden="true" />
          <span>{{ t("experiments.progressAgent") }}</span>
          <strong>{{ progress?.run_stage ?? progress?.run_status ?? t("experiments.preparing") }}</strong>
        </article>
        <article>
          <Footprints :size="16" aria-hidden="true" />
          <span>{{ t("experiments.progressStep") }}</span>
          <strong>{{ currentStepText }}</strong>
        </article>
        <article>
          <Database :size="16" aria-hidden="true" />
          <span>{{ t("experiments.progressUnit") }}</span>
          <strong>{{ currentUnitText }}</strong>
        </article>
      </div>
      <div class="progress-counts">
        <span>{{ progress?.clean_runs_completed ?? 0 }} / {{ progress?.clean_runs_total_estimate ?? 0 }} {{ t("experiments.cleanRunsProgress") }}</span>
        <span>{{ progress?.replay_runs_completed ?? 0 }} {{ t("experiments.replayDone") }}</span>
        <span>{{ progress?.replay_runs_running ?? 0 }} {{ t("experiments.replayActive") }}</span>
      </div>
    </section>

    <section v-if="!metrics && experiment" class="hero-band subtle-panel">
      <div>
        <p class="eyebrow">TRACE / EXPERIMENT DETAIL</p>
        <h1>{{ experiment.name }}</h1>
        <p>{{ experiment.error_message || t("experiments.detailSubtitle") }}</p>
      </div>
      <div class="source-card">
        <Database :size="18" aria-hidden="true" />
        <span>
          <strong>{{ t(`status.${experiment.status}`) }}</strong>
          <small>{{ experiment.runtime_profile_id ?? t("common.none") }}</small>
        </span>
      </div>
    </section>

    <template v-if="metrics">
      <section class="hero-band subtle-panel">
        <div>
          <p class="eyebrow">TRACE / EXPERIMENT DETAIL</p>
          <h1>{{ metrics.experiment.name }}</h1>
          <p>{{ t("experiments.detailSubtitle") }}</p>
        </div>
        <div class="source-card">
          <Database :size="18" aria-hidden="true" />
          <span>
            <strong>{{ metrics.data_source.kind === "real_llm" ? t("experiments.realLlm") : t("experiments.mockSource") }}</strong>
            <small>{{ metrics.data_source.label }} · {{ metrics.data_source.generated_by }}</small>
          </span>
        </div>
      </section>

      <section class="metadata-grid">
        <article class="subtle-panel meta-tile">
          <span>{{ t("experiments.provider") }}</span>
          <strong>{{ metrics.data_source.provider_label ?? t("common.unknown") }}</strong>
          <small>{{ metrics.data_source.model_label ?? t("common.unknown") }}</small>
        </article>
        <article class="subtle-panel meta-tile">
          <span>{{ t("experiments.repeat") }}</span>
          <strong>{{ metrics.experiment.repeat_count }}</strong>
          <button class="inline-link" type="button" @click="emit('navigate', `#/datasets/${metrics.experiment.dataset_id}`)">
            {{ metrics.experiment.dataset_id }}
          </button>
        </article>
        <article class="subtle-panel meta-tile">
          <span>{{ t("experiments.generatedAt") }}</span>
          <strong>{{ formatDate(metrics.generated_at) }}</strong>
          <small>{{ t(`status.${metrics.experiment.status}`) }}</small>
        </article>
        <article class="subtle-panel meta-tile">
          <span>{{ t("experiments.cleanRuns") }}</span>
          <strong>{{ metrics.clean_runs.length }}</strong>
          <small>{{ metrics.replay_runs.length }} {{ t("experiments.replays") }}</small>
        </article>
      </section>

      <section class="runtime-band subtle-panel">
        <article>
          <span>{{ t("experiments.executors") }}</span>
          <strong>{{ countText(metrics.runtime_execution.executor_kind_distribution) }}</strong>
        </article>
        <article>
          <span>{{ t("experiments.replayCache") }}</span>
          <strong>{{ countText(metrics.runtime_execution.replay_cache_counts) }}</strong>
        </article>
        <article>
          <span>{{ t("experiments.setup") }}</span>
          <strong>{{ countText(metrics.runtime_execution.setup_status_counts) }}</strong>
        </article>
        <article>
          <span>{{ t("experiments.replayWork") }}</span>
          <strong>{{ metrics.runtime_execution.observed_replay_count }} {{ t("experiments.replayObserved") }} / {{ metrics.runtime_execution.reused_replay_count }} {{ t("experiments.replayReused") }}</strong>
        </article>
        <article>
          <span>{{ t("experiments.retries") }}</span>
          <strong>
            {{ String(metrics.runtime_execution.retries?.retried_replay_count ?? 0) }} {{ t("experiments.retryReplays") }} /
            {{ String(metrics.runtime_execution.retries?.retry_attempts ?? 0) }} {{ t("experiments.retryAttempts") }}
          </strong>
        </article>
        <div v-if="props.dataSource === 'api'" class="cleanup-actions">
          <button class="text-button" type="button" @click="runCleanup(true)">{{ t("experiments.previewWorkspaceCleanup") }}</button>
          <button class="text-button danger-action" type="button" :disabled="!workspaceCleanupPreview" @click="runCleanup(false)">{{ t("experiments.deleteWorkspaceCandidates") }}</button>
          <button class="text-button" type="button" @click="runCacheCleanup(true)">{{ t("experiments.previewReplayCacheCleanup") }}</button>
          <button class="text-button danger-action" type="button" :disabled="!cacheCleanupPreview" @click="runCacheCleanup(false)">{{ t("experiments.deleteCacheCandidates") }}</button>
        </div>
      </section>

      <section v-if="workspaceCleanupPreview || cacheCleanupPreview" class="cleanup-preview-grid">
        <article v-if="workspaceCleanupPreview" class="subtle-panel cleanup-preview">
          <div class="cleanup-preview-head">
            <span>{{ t("experiments.workspaceCleanupCandidates") }}</span>
            <strong>{{ workspaceCleanupPreview.candidate_count ?? 0 }}</strong>
          </div>
          <table>
            <thead>
              <tr>
                <th>{{ t("experiments.replay") }}</th>
                <th>{{ t("experiments.status") }}</th>
                <th>{{ t("experiments.exists") }}</th>
                <th>{{ t("experiments.path") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="candidate in workspaceCleanupPreview.candidates ?? []" :key="candidate.replay_id ?? candidate.path">
                <td class="mono">{{ candidateText(candidate.replay_id) }}</td>
                <td>{{ candidateStatusText(candidate.status) }}</td>
                <td>{{ candidateExistsText(candidate.exists) }}</td>
                <td class="mono">{{ candidateText(candidate.path) }}</td>
              </tr>
            </tbody>
          </table>
        </article>
        <article v-if="cacheCleanupPreview" class="subtle-panel cleanup-preview">
          <div class="cleanup-preview-head">
            <span>{{ t("experiments.replayCacheCleanupCandidates") }}</span>
            <strong>{{ cacheCleanupPreview.candidate_count ?? 0 }}</strong>
          </div>
          <table>
            <thead>
              <tr>
                <th>{{ t("experiments.replay") }}</th>
                <th>{{ t("experiments.cache") }}</th>
                <th>{{ t("experiments.exists") }}</th>
                <th>{{ t("experiments.path") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="candidate in cacheCleanupPreview.candidates ?? []" :key="candidate.replay_id ?? candidate.path">
                <td class="mono">{{ candidateText(candidate.replay_id) }}</td>
                <td>{{ candidateStatusText(candidate.cache_status ?? candidate.status) }}</td>
                <td>{{ candidateExistsText(candidate.exists) }}</td>
                <td class="mono">{{ candidateText(candidate.path) }}</td>
              </tr>
            </tbody>
          </table>
        </article>
      </section>

      <section v-if="props.dataSource === 'api'" class="lifecycle-grid">
        <article class="subtle-panel lifecycle-tile">
          <span>{{ t("experiments.artifactInventory") }}</span>
          <strong>{{ String(lifecycle?.artifact_count ?? metrics.runtime_execution.artifact_inventory?.artifact_count ?? 0) }}</strong>
          <small>{{ String(lifecycle?.artifact_bytes ?? metrics.runtime_execution.artifact_inventory?.artifact_bytes ?? 0) }} bytes</small>
        </article>
        <article class="subtle-panel lifecycle-tile">
          <span>{{ t("experiments.workspaces") }}</span>
          <strong>{{ String(lifecycle?.workspace_count ?? metrics.runtime_execution.artifact_inventory?.workspace_count ?? 0) }}</strong>
          <small>{{ String(lifecycle?.workspace_bytes ?? metrics.runtime_execution.artifact_inventory?.workspace_bytes ?? 0) }} bytes</small>
        </article>
        <article class="subtle-panel lifecycle-tile">
          <span>{{ t("experiments.replayCacheEntries") }}</span>
          <strong>{{ String((cacheInfo?.entries as unknown[] | undefined)?.length ?? 0) }}</strong>
          <small>{{ countText(metrics.runtime_execution.replay_cache_counts) }}</small>
        </article>
      </section>

      <section class="report-export-panel subtle-panel">
        <div>
          <p class="eyebrow">{{ t("experiments.reportExport") }}</p>
          <h2>{{ t("experiments.reportExportTitle") }}</h2>
          <p>{{ t("experiments.reportExportBody") }}</p>
        </div>
        <div class="report-actions">
          <button class="text-button" type="button" @click="downloadMetricsJson">
            <Download :size="15" aria-hidden="true" />
            {{ t("experiments.downloadMetricsJson") }}
          </button>
          <button class="text-button" type="button" :disabled="!firstRunIdForReport()" @click="openFirstRunReport">
            <FileText :size="15" aria-hidden="true" />
            {{ t("experiments.openFirstRunReport") }}
          </button>
        </div>
        <div class="report-grid">
          <article>
            <span>{{ t("experiments.dataset") }}</span>
            <button class="inline-link" type="button" @click="emit('navigate', `#/datasets/${metrics.experiment.dataset_id}`)">
              {{ metrics.experiment.dataset_id }}
            </button>
          </article>
          <article>
            <span>{{ t("experiments.metricStates") }}</span>
            <strong>{{ metrics.rows.map((row) => `${row.strategy_id}:${row.metric_status}`).join(" / ") }}</strong>
          </article>
          <article>
            <span>{{ t("experiments.artifacts") }}</span>
            <strong>{{ reportLikeArtifacts().length ? reportLikeArtifacts().map((artifact) => artifact.artifact_type).join(", ") : t("experiments.runLevelReportsOnly") }}</strong>
          </article>
        </div>
        <details class="json-details">
          <summary>{{ t("experiments.runtimeExecutionJson") }}</summary>
          <pre>{{ jsonText(metrics.runtime_execution as JsonObject) }}</pre>
        </details>
      </section>

      <ExperimentMetricsTable :rows="metrics.rows" />
      <CaptureMatrix
        :rows="metrics.rows"
        :capture-matrix="metrics.capture_matrix"
        :capture-matrix-counts="metrics.capture_matrix_counts"
      />
      <EvaluationEventTimeline
        :evaluation-events="metrics.evaluation_events ?? []"
        :reflection-event-backfeed="metrics.reflection_event_backfeed ?? []"
      />
      <CleanRunTable :clean-runs="metrics.clean_runs" @open-run="openCleanRun" />
      <ReplayEvidencePanel
        :replay-runs="metrics.replay_runs"
        :replay-results="metrics.experiment_replay_runs"
        :selected-replay-id="selectedReplayId"
        @select="selectReplay"
      />
    </template>
  </main>
</template>

<style scoped>
.detail-head,
.hero-band,
.progress-band,
.metadata-grid,
.lifecycle-grid {
  margin-top: 18px;
}

.progress-band {
  display: grid;
  gap: 14px;
  padding: 16px;
}

.progress-main {
  display: grid;
  gap: 10px;
}

.progress-title {
  display: flex;
  align-items: center;
  gap: 9px;
  color: var(--ink);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}

.progress-title small {
  margin-left: auto;
  color: var(--muted);
  font-size: 11px;
  font-weight: 600;
  text-transform: none;
}

.live-dot {
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: #18a558;
  box-shadow: 0 0 0 0 rgba(24, 165, 88, 0.32);
  animation: live-pulse 1.6s ease-out infinite;
}

.progress-bar {
  position: relative;
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(28, 38, 52, 0.08);
}

.progress-bar span {
  position: absolute;
  inset: 0 auto 0 0;
  min-width: 8px;
  border-radius: inherit;
  background: linear-gradient(90deg, #1b8a5a, #2d7fb8, #7562a8);
  transition: width 280ms ease;
}

.progress-bar span::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.42), transparent);
  animation: progress-sheen 1.8s linear infinite;
}

.progress-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.progress-grid article {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 3px 8px;
  align-items: center;
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.46);
}

.progress-grid svg {
  color: var(--tool);
}

.progress-grid span {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
}

.progress-grid strong {
  grid-column: 1 / -1;
  min-height: 18px;
  overflow-wrap: anywhere;
  font-size: 13px;
}

.progress-counts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
}

.progress-counts span {
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: rgba(251, 250, 247, 0.62);
}

.runtime-band {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr)) auto;
  gap: 12px;
  align-items: start;
  margin-top: 18px;
  padding: 14px;
}

.runtime-band article {
  display: grid;
  gap: 3px;
}

.runtime-band span {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
}

.runtime-band strong {
  overflow-wrap: anywhere;
  font-size: 13px;
}

.cleanup-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.detail-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.hero-band {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 18px;
}

.hero-band h1 {
  margin: 8px 0 10px;
}

.hero-band p {
  max-width: 760px;
  font-family: var(--font-serif);
}

.source-card {
  width: min(360px, 100%);
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(251, 250, 247, 0.78);
}

.source-card span {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.source-card small,
.meta-tile small {
  overflow-wrap: anywhere;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
}

.metadata-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.lifecycle-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.cleanup-preview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.cleanup-preview {
  display: grid;
  gap: 10px;
  padding: 14px;
  overflow-x: auto;
}

.cleanup-preview-head,
.report-export-panel,
.report-actions {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  justify-content: space-between;
}

.cleanup-preview-head span,
.report-grid span {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
}

.danger-action {
  color: var(--failed);
}

.report-export-panel {
  display: grid;
  margin-top: 18px;
  padding: 16px;
}

.report-export-panel h2 {
  margin-top: 4px;
  font-size: 18px;
}

.report-export-panel p {
  max-width: 760px;
  color: var(--muted-strong);
}

.report-actions {
  justify-content: flex-start;
  flex-wrap: wrap;
}

.report-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.report-grid article {
  display: grid;
  gap: 4px;
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.52);
}

.report-grid strong {
  overflow-wrap: anywhere;
  font-size: 13px;
}

.json-details {
  display: grid;
  gap: 8px;
}

.json-details summary {
  cursor: pointer;
  color: var(--tool);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
}

.json-details pre {
  max-height: 260px;
  overflow: auto;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.68);
  font-size: 11px;
}

.lifecycle-tile {
  display: grid;
  gap: 3px;
  padding: 14px;
}

.lifecycle-tile span {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
}

.lifecycle-tile small {
  overflow-wrap: anywhere;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
}

.meta-tile {
  display: grid;
  gap: 3px;
  padding: 14px;
}

.meta-tile span {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
}

.meta-tile strong {
  overflow-wrap: anywhere;
  font-size: 20px;
}

.meta-tile small {
  overflow-wrap: anywhere;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
}

.inline-link {
  justify-self: start;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--tool);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  overflow-wrap: anywhere;
  text-align: left;
}

.inline-link:hover {
  background: transparent;
  color: var(--ink);
  text-decoration: underline;
}

@media (max-width: 1080px) {
  .hero-band,
  .progress-grid,
  .metadata-grid,
  .lifecycle-grid,
  .cleanup-preview-grid,
  .report-grid {
    grid-template-columns: 1fr;
  }

  .runtime-band {
    grid-template-columns: 1fr;
  }

  .hero-band {
    display: grid;
  }
}

@keyframes live-pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(24, 165, 88, 0.32);
  }
  72% {
    box-shadow: 0 0 0 9px rgba(24, 165, 88, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(24, 165, 88, 0);
  }
}

@keyframes progress-sheen {
  from {
    transform: translateX(-100%);
  }
  to {
    transform: translateX(100%);
  }
}
</style>
