<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { Play, RefreshCw, RotateCcw, Square, Wifi, WifiOff } from "@lucide/vue";
import { cancelRun, createRun, getRunBundle, retryRun } from "../api/runs";
import ArtifactsList from "../components/ArtifactsList.vue";
import PytestResultsTable from "../components/PytestResultsTable.vue";
import ReportPaper from "../components/ReportPaper.vue";
import RunSummaryPanel from "../components/RunSummaryPanel.vue";
import StatusBadge from "../components/StatusBadge.vue";
import TopicTabs from "../components/TopicTabs.vue";
import TraceStepDetail from "../components/TraceStepDetail.vue";
import TraceTimeline from "../components/TraceTimeline.vue";
import { useLatestRequest } from "../composables/useLatestRequest";
import { useI18n } from "../i18n";
import { staticRunFixture } from "../demo/staticRunFixture";
import type { RunBundle, TraceStepOut } from "../types/api";
import type { DataSource, TopicTab } from "../types/ui";

type RunTab = "overview" | "trace" | "report" | "pytest" | "artifacts";

const props = defineProps<{
  runId: string;
  dataSource: DataSource;
}>();

const emit = defineEmits<{
  navigate: [hash: string];
}>();

const activeTab = ref<RunTab>("trace");
const bundle = ref<RunBundle | null>(null);
const selectedStepId = ref<string | null>(null);
const drawerOpen = ref(false);
const loading = ref(false);
const isStale = ref(false);
const isPollingRefresh = ref(false);
const errorMessage = ref<string | null>(null);
const { t } = useI18n();
let poller: number | null = null;
const bundleRequest = useLatestRequest();

const tabs = computed<TopicTab[]>(() => [
  { key: "overview", label: t("run.overview") },
  { key: "trace", label: t("run.trace"), count: bundle.value?.traceSteps.length ?? 0 },
  { key: "report", label: t("run.report") },
  { key: "pytest", label: t("run.pytest"), count: bundle.value?.pytestResults.length ?? 0 },
  { key: "artifacts", label: t("run.artifacts"), count: bundle.value?.artifacts.length ?? 0 }
]);

const selectedStep = computed(() => {
  if (!bundle.value) {
    return null;
  }
  if (!selectedStepId.value) {
    return null;
  }
  return bundle.value.traceSteps.find((step) => step.id === selectedStepId.value) ?? null;
});

const run = computed(() => bundle.value?.run ?? null);
const canPoll = computed(() => props.dataSource === "api" && ["queued", "running"].includes(run.value?.status ?? ""));
const isRunActive = computed(() => ["queued", "running"].includes(run.value?.status ?? ""));

function cloneDemoBundle(): RunBundle {
  return structuredClone(staticRunFixture);
}

let backgroundLoadInFlight = false;

function keepSelectedStepIfPresent(nextBundle: RunBundle) {
  const current = selectedStepId.value;
  if (!current) {
    return;
  }
  if (!nextBundle.traceSteps.some((step) => step.id === current)) {
    selectedStepId.value = null;
    drawerOpen.value = false;
  }
}

async function loadBundle(options: { background?: boolean } = {}) {
  const background = options.background === true && bundle.value !== null;
  if (background && (loading.value || backgroundLoadInFlight)) {
    return;
  }
  const requestSeq = bundleRequest.next();
  if (background) {
    backgroundLoadInFlight = true;
    isPollingRefresh.value = true;
  }
  loading.value = true;
  errorMessage.value = null;
  try {
    const nextBundle = props.dataSource === "demo" ? cloneDemoBundle() : await getRunBundle(props.runId);
    if (!bundleRequest.isCurrent(requestSeq)) {
      return;
    }
    bundle.value = nextBundle;
    keepSelectedStepIfPresent(nextBundle);
  } catch (error) {
    if (!bundleRequest.isCurrent(requestSeq)) {
      return;
    }
    errorMessage.value = error instanceof Error ? error.message : t("run.loadFailed");
  } finally {
    if (background) {
      backgroundLoadInFlight = false;
    }
    if (bundleRequest.isCurrent(requestSeq)) {
      loading.value = false;
      isPollingRefresh.value = false;
    }
  }
}

function stopPolling() {
  if (poller !== null) {
    window.clearInterval(poller);
    poller = null;
  }
}

function configurePolling() {
  stopPolling();
  if (canPoll.value) {
    poller = window.setInterval(() => {
      void loadBundle({ background: true });
    }, 1500);
  }
}

async function refresh() {
  await loadBundle();
}

function appendDemoRetryStep() {
  if (!bundle.value) {
    return;
  }
  const nextIndex = bundle.value.traceSteps.length + 1;
  const step: TraceStepOut = {
    id: `step-${String(nextIndex).padStart(2, "0")}`,
    run_id: bundle.value.run.id,
    attempt_id: null,
    step_index: nextIndex,
    step_type: "system",
    name: "retry_run_queued",
    input_summary: "User requested run retry in demo fixture mode.",
    output_summary: "New retry run returned queued state; stale content was replaced without blanking the page.",
    tool_name: null,
    payload: {
      retry_of_run_id: bundle.value.run.id,
      new_run_id: "run-demo-react-retry-001",
      status_after: "queued"
    },
    tokens: null,
    duration_ms: 31,
    status: "ok",
    error: null,
    created_at: new Date().toISOString()
  };
  bundle.value.traceSteps = [...bundle.value.traceSteps, step];
  selectedStepId.value = step.id;
}

async function retryCurrentRun() {
  if (!bundle.value) {
    return;
  }
  isStale.value = true;
  try {
    if (props.dataSource === "api") {
      const newRun = await retryRun(bundle.value.run.id);
      emit("navigate", `#/runs/${newRun.id}`);
      return;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 900));
    appendDemoRetryStep();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t("run.retryFailed");
  } finally {
    isStale.value = false;
  }
}

async function cancelCurrentRun() {
  if (!bundle.value) {
    return;
  }
  if (props.dataSource === "api") {
    try {
      const cancelled = await cancelRun(bundle.value.run.id);
      bundle.value.run = cancelled;
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : t("run.cancelFailed");
    }
    return;
  }
  bundle.value.run.status = "cancelled";
  bundle.value.run.stage = null;
}

async function startRunFromCurrentPlan() {
  if (!bundle.value) {
    return;
  }
  if (props.dataSource !== "api") {
    await retryCurrentRun();
    return;
  }
  try {
    const newRun = await createRun(bundle.value.run.test_plan_id, {
      snapshot_id: bundle.value.run.project_snapshot_id,
      strategy_version_id: bundle.value.run.strategy_version_id,
      budget_override: { allow_reflection: true },
      output_options: { save_full_trace: true }
    });
    emit("navigate", `#/runs/${newRun.id}`);
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t("run.creationFailed");
  }
}

function selectTab(key: string) {
  activeTab.value = key as RunTab;
}

watch(
  () => [props.runId, props.dataSource],
  () => {
    selectedStepId.value = null;
    drawerOpen.value = false;
    void loadBundle();
  },
  { immediate: true }
);

watch(canPoll, configurePolling, { immediate: true });

onBeforeUnmount(stopPolling);
</script>

<template>
  <main class="run-page app-page">
    <section
      class="console-shell"
      :class="{ 'drawer-closed': !drawerOpen, 'is-stale': isStale, 'is-polling': isPollingRefresh || (loading && bundle) }"
    >
      <div class="console-top">
        <div class="brand-line">
          <img class="brand-mark" src="/trace-logo-icon.svg" alt="TRACE" />
          <div class="brand-meta">
            <strong>{{ t("run.title") }}</strong>
            <span>{{ run?.id ?? props.runId }}</span>
          </div>
        </div>

        <div class="top-meta">
          <span class="source-pill">
            <Wifi v-if="props.dataSource === 'api'" :size="14" aria-hidden="true" />
            <WifiOff v-else :size="14" aria-hidden="true" />
            {{ props.dataSource === "api" ? t("app.api") : t("app.demo") }}
          </span>
          <StatusBadge :value="run?.status ?? (loading ? 'running' : 'unknown')" :pulse="run?.status === 'running'" />
        </div>

        <div class="top-actions">
          <button class="icon-button" type="button" :title="t('run.refresh')" @click="refresh">
            <RefreshCw :size="17" aria-hidden="true" />
            <span class="sr-only">{{ t("run.refresh") }}</span>
          </button>
          <button class="primary-action" type="button" @click="startRunFromCurrentPlan">
            <Play :size="17" aria-hidden="true" />
            {{ t("run.start") }}
          </button>
          <button class="icon-button" type="button" :title="t('run.retry')" @click="retryCurrentRun">
            <RotateCcw :size="17" aria-hidden="true" />
            <span class="sr-only">{{ t("run.retry") }}</span>
          </button>
          <button class="icon-button" type="button" :title="t('run.cancel')" :disabled="run?.status !== 'running'" @click="cancelCurrentRun">
            <Square :size="17" aria-hidden="true" />
            <span class="sr-only">{{ t("run.cancel") }}</span>
          </button>
        </div>
      </div>

      <div class="stale-progress" aria-hidden="true"></div>

      <template v-if="bundle">
        <RunSummaryPanel :bundle="bundle" />

        <section class="main-pane">
          <TopicTabs :tabs="tabs" :active="activeTab" @select="selectTab" />

          <div v-if="errorMessage" class="error-banner">{{ errorMessage }}</div>
          <div v-if="isRunActive" class="live-status" aria-live="polite">
            <span class="live-spinner" aria-hidden="true"></span>
            <span>{{ t("run.waitingForStep") }}</span>
          </div>

          <div v-if="activeTab === 'overview'" class="overview-pane">
            <div class="overview-grid">
              <article>
                <p class="eyebrow">{{ t("run.statusScope") }}</p>
                <h3>{{ t("run.statusBody") }}</h3>
                <p>
                  <code>{{ bundle.run.status }}</code>
                </p>
              </article>
              <article>
                <p class="eyebrow">{{ t("run.strategySnapshot") }}</p>
                <h3>{{ bundle.strategy?.name ?? bundle.run.strategy_version_id }}</h3>
                <p>{{ t("run.strategyBody") }}</p>
              </article>
            </div>

            <div class="table-shell">
              <table>
                <thead>
                  <tr>
                    <th>{{ t("run.event") }}</th>
                    <th>{{ t("run.stage") }}</th>
                    <th>{{ t("run.before") }}</th>
                    <th>{{ t("run.after") }}</th>
                    <th>{{ t("run.message") }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="event in bundle.events" :key="event.id">
                    <td class="mono">{{ event.event_type }}</td>
                    <td>{{ event.stage ?? t("common.none") }}</td>
                    <td>{{ event.status_before ?? t("common.none") }}</td>
                    <td>{{ event.status_after ?? t("common.none") }}</td>
                    <td>{{ event.message ?? "" }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <TraceTimeline
            v-else-if="activeTab === 'trace'"
            :steps="bundle.traceSteps"
            :selected-step-id="selectedStepId"
            :live="isRunActive"
            @select="
              selectedStepId = $event.id;
              drawerOpen = true;
            "
          />
          <ReportPaper v-else-if="activeTab === 'report'" :report="bundle.report" />
          <PytestResultsTable v-else-if="activeTab === 'pytest'" :results="bundle.pytestResults" />
          <ArtifactsList v-else :artifacts="bundle.artifacts" />
        </section>

        <TraceStepDetail :step="selectedStep" :open="drawerOpen" @close="drawerOpen = false" />
      </template>

      <div v-else class="loading-state">
        <p class="eyebrow">TRACE</p>
        <h2>{{ loading ? t("run.loading") : t("run.noData") }}</h2>
        <p>{{ errorMessage ?? t("run.noDataHint") }}</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.console-shell {
  position: relative;
  display: grid;
  grid-template-columns: minmax(220px, 260px) minmax(560px, 1fr) minmax(520px, 0.92fr);
  gap: 0;
  min-height: 720px;
  overflow: hidden;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  background: var(--panel);
  box-shadow: var(--shadow);
  transition: grid-template-columns var(--motion-base) var(--ease-standard);
}

.console-shell.drawer-closed {
  grid-template-columns: minmax(220px, 260px) minmax(560px, 1fr) 0;
}

.console-shell.is-stale :deep(.summary-rail),
.console-shell.is-stale .main-pane,
.console-shell.is-stale :deep(.detail-drawer) {
  opacity: 0.5;
  pointer-events: none;
  transition: opacity var(--motion-base) var(--ease-standard);
}

.stale-progress {
  position: absolute;
  z-index: 6;
  top: 63px;
  left: 0;
  width: 100%;
  height: 2px;
  overflow: hidden;
  opacity: 0;
  background: rgba(215, 164, 76, 0.18);
  pointer-events: none;
  transition: opacity var(--motion-fast) var(--ease-standard);
}

.stale-progress::before {
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 34%;
  background: var(--running);
  transform: translateX(-110%);
}

.console-shell.is-stale .stale-progress {
  opacity: 1;
}

.console-shell.is-stale .stale-progress::before,
.console-shell.is-polling .stale-progress::before {
  animation: progress-sweep 1.2s ease-in-out infinite;
}

.console-shell.is-polling .stale-progress {
  opacity: 1;
}

@keyframes progress-sweep {
  from {
    transform: translateX(-110%);
  }

  to {
    transform: translateX(330%);
  }
}

.console-top {
  grid-column: 1 / -1;
  min-height: 64px;
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto auto;
  gap: 16px;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: rgba(246, 243, 238, 0.7);
}

.brand-line,
.top-meta,
.top-actions {
  display: flex;
  align-items: center;
}

.brand-line {
  min-width: 0;
  gap: 12px;
}

.brand-mark {
  width: 38px;
  height: 38px;
  flex: 0 0 auto;
}

.brand-meta {
  min-width: 0;
}

.brand-meta strong,
.brand-meta span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.brand-meta span {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 12px;
}

.top-meta,
.top-actions {
  gap: 8px;
}

.source-pill {
  min-height: 28px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel);
  color: var(--muted-strong);
  font-family: var(--font-mono);
  font-size: 11px;
}

.main-pane {
  min-width: 0;
  padding: 18px 18px 22px;
  background: var(--panel);
}

.main-pane :deep(.topic-tabs) {
  position: relative;
  z-index: 4;
}

.error-banner {
  margin: 14px 0;
  padding: 10px 12px;
  border: 1px solid rgba(159, 58, 47, 0.22);
  border-radius: 7px;
  background: rgba(159, 58, 47, 0.08);
  color: var(--failed);
}

.live-status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 12px 0 0;
  padding: 7px 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.7);
  color: var(--muted-strong);
  font-size: 12px;
}

.live-spinner {
  width: 13px;
  height: 13px;
  border: 2px solid rgba(49, 95, 125, 0.22);
  border-top-color: var(--tool);
  border-radius: 50%;
  animation: spin 760ms linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.overview-pane {
  display: grid;
  gap: 18px;
  padding-top: 18px;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.overview-grid article {
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: rgba(255, 255, 255, 0.78);
}

.overview-grid h3 {
  margin: 6px 0 8px;
}

.loading-state {
  grid-column: 1 / -1;
  display: grid;
  min-height: 520px;
  align-content: center;
  justify-items: center;
  gap: 8px;
  padding: 28px;
}

@media (max-width: 1200px) {
  .console-shell,
  .console-shell.drawer-closed {
    grid-template-columns: minmax(0, 1fr) minmax(520px, 0.88fr);
  }

  .console-shell :deep(.summary-rail) {
    grid-column: 1 / -1;
  }

}

@media (max-width: 900px) {
  .console-shell,
  .console-shell.drawer-closed {
    grid-template-columns: 1fr;
  }

  .console-top {
    grid-template-columns: 1fr;
  }

  .top-meta,
  .top-actions {
    flex-wrap: wrap;
  }

  .overview-grid {
    grid-template-columns: 1fr;
  }

  .console-shell :deep(.detail-drawer) {
    position: fixed;
    inset: auto 0 0 0;
    max-height: 86vh;
    overflow: auto;
    border-top: 1px solid var(--border);
    border-left: 0;
  }
}
</style>
