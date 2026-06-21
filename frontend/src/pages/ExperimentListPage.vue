<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ArrowRight, Beaker, Play, Plus, RefreshCw, ServerCrash } from "@lucide/vue";
import { createExperiment, listExperiments, runExperiment } from "../api/experiments";
import { listEvalDatasets } from "../api/evaluation";
import { listLlmOptions } from "../api/llmOptions";
import { createDatasetRuntimeProfile, getDatasetRuntimeBindingManifest, getExecutorStatus, listDatasetRuntimeProfiles } from "../api/runtimeProfiles";
import { listStrategies, listStrategyVersions } from "../api/strategies";
import { demoExperimentMetrics } from "../demo/staticRunFixture";
import { useLatestRequest } from "../composables/useLatestRequest";
import { useI18n } from "../i18n";
import type { DatasetRuntimeBindingManifestOut, EvalDatasetOut, ExperimentDefinition, LlmOptionOut, RuntimeProfileOut, StrategyVersionOut } from "../types/api";
import type { DataSource } from "../types/ui";

const props = defineProps<{
  dataSource: DataSource;
  initialDatasetId?: string;
}>();

const emit = defineEmits<{
  navigate: [hash: string];
}>();

const { t } = useI18n();

const experiments = ref<ExperimentDefinition[]>([]);
const datasets = ref<EvalDatasetOut[]>([]);
const runtimeBindingManifest = ref<DatasetRuntimeBindingManifestOut | null>(null);
const strategyVersions = ref<StrategyVersionOut[]>([]);
const runtimeProfiles = ref<RuntimeProfileOut[]>([]);
const llmOptions = ref<LlmOptionOut[]>([]);
const llmConfigStatus = ref<"ok" | "missing" | "error">("missing");
const llmConfigError = ref<string | null>(null);
const projectRuntimeProfiles = ref<Record<string, RuntimeProfileOut[]>>({});
const projectLabels = ref<Record<string, string>>({});
const runtimeProfileBindings = ref<Record<string, string>>({});
const dockerAvailable = ref<boolean | null>(null);
const loading = ref(false);
const creating = ref(false);
const creatingRuntime = ref(false);
const startingId = ref<string | null>(null);
const errorMessage = ref<string | null>(null);
const createError = ref<string | null>(null);
const datasetSelectionWarning = ref<string | null>(null);
const loadingCreateOptions = ref(false);
const dockerProfileBox = ref<HTMLElement | null>(null);
const form = ref({
  id: "",
  name: "local demo experiment",
  datasetId: "",
  runtimeProfileId: "",
  strategyVersionIds: [] as string[],
  repeatCount: 1,
  llmOptionId: "mock"
});
const dockerProfileForm = ref({
  name: "Docker pytest 3.12",
  image: "trace-pytest:3.12",
  workingDir: "/workspace",
  testCommand: "python -m pytest tests -q",
  networkPolicy: "disabled" as "default" | "disabled" | "install_only",
  timeoutSeconds: 120
});

const listRequest = useLatestRequest();

const completedCount = computed(() => experiments.value.filter((experiment) => experiment.status === "completed").length);
const datasetProjectIds = computed(() => {
  return (runtimeBindingManifest.value?.projects ?? []).map((project) => project.project_id).sort();
});
const isMultiProjectDataset = computed(() => datasetProjectIds.value.length > 1);
const selectedLlmOption = computed(() => llmOptions.value.find((option) => option.id === form.value.llmOptionId) ?? null);
const canCreate = computed(
  () =>
    props.dataSource === "api" &&
    !loadingCreateOptions.value &&
    form.value.name.trim() &&
    form.value.datasetId &&
    (isMultiProjectDataset.value
      ? datasetProjectIds.value.every((projectId) => Boolean(runtimeProfileBindings.value[`project:${projectId}`]))
      : form.value.runtimeProfileId) &&
    form.value.strategyVersionIds.length > 0 &&
    form.value.repeatCount >= 1 &&
    Boolean(selectedLlmOption.value?.selectable)
);

type CreateBlockerId = "loading" | "name" | "dataset" | "runtime" | "strategy" | "repeat" | "llm";

type CreateBlocker = {
  id: CreateBlockerId;
  message: string;
};

const createBlockers = computed<CreateBlocker[]>(() => {
  if (props.dataSource !== "api") {
    return [];
  }
  if (loadingCreateOptions.value) {
    return [{ id: "loading", message: t("experiments.blockerLoadingOptions") }];
  }
  const blockers: CreateBlocker[] = [];
  if (!form.value.name.trim()) {
    blockers.push({ id: "name", message: t("experiments.blockerName") });
  }
  if (!form.value.datasetId || datasets.value.length === 0) {
    blockers.push({ id: "dataset", message: t("experiments.blockerDataset") });
  } else if (
    isMultiProjectDataset.value
      ? datasetProjectIds.value.some((projectId) => !runtimeProfileBindings.value[`project:${projectId}`])
      : !form.value.runtimeProfileId
  ) {
    blockers.push({ id: "runtime", message: t("experiments.blockerRuntime") });
  }
  if (form.value.strategyVersionIds.length === 0) {
    blockers.push({ id: "strategy", message: t("experiments.blockerStrategy") });
  }
  if (form.value.repeatCount < 1) {
    blockers.push({ id: "repeat", message: t("experiments.blockerRepeat") });
  }
  if (!selectedLlmOption.value?.selectable) {
    blockers.push({ id: "llm", message: t("experiments.blockerLlm") });
  }
  return blockers;
});

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

function openDataset(datasetId: string) {
  emit("navigate", `#/datasets/${datasetId}`);
}

function showRuntimeProfileBox() {
  dockerProfileBox.value?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function applyInitialDatasetId(nextDatasets: EvalDatasetOut[]): boolean {
  const requestedDatasetId = props.initialDatasetId?.trim();
  datasetSelectionWarning.value = null;
  if (!requestedDatasetId) {
    return false;
  }
  if (!nextDatasets.some((dataset) => dataset.id === requestedDatasetId)) {
    datasetSelectionWarning.value = t("experiments.initialDatasetMissing", { id: requestedDatasetId });
    return false;
  }
  form.value.datasetId = requestedDatasetId;
  return true;
}

function profileSummary(profile: RuntimeProfileOut | undefined): string {
  if (!profile) {
    return t("common.none");
  }
  const concurrency = profile.replay_policy?.replay_concurrency ?? profile.resource_limits?.replay_concurrency ?? 1;
  const timeout = profile.resource_limits?.timeout_seconds ?? 120;
  return `${profile.executor} / retry:${profile.replay_policy?.max_retries ?? 0} / concurrency:${concurrency} / timeout:${timeout}s`;
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

async function loadCreateOptions() {
  if (props.dataSource !== "api") {
    datasets.value = [];
    strategyVersions.value = [];
    llmOptions.value = [];
    llmConfigStatus.value = "missing";
    llmConfigError.value = null;
    loadingCreateOptions.value = false;
    return;
  }
  loadingCreateOptions.value = true;
  try {
    const [nextDatasets, strategies, executorStatus, llmOptionResponse] = await Promise.all([
      listEvalDatasets(),
      listStrategies(),
      getExecutorStatus(),
      listLlmOptions()
    ]);
    const versionGroups = await Promise.all(strategies.map((strategy) => listStrategyVersions(strategy.id)));
    datasets.value = nextDatasets;
    strategyVersions.value = versionGroups.flat();
    llmOptions.value = llmOptionResponse.options;
    llmConfigStatus.value = llmOptionResponse.config_status;
    llmConfigError.value = llmOptionResponse.config_error;
    const defaultLlmOption =
      llmOptionResponse.options.find((option) => option.id === llmOptionResponse.default_option_id && option.selectable) ??
      llmOptionResponse.options.find((option) => option.selectable) ??
      null;
    if (!llmOptionResponse.options.some((option) => option.id === form.value.llmOptionId && option.selectable)) {
      form.value.llmOptionId = defaultLlmOption?.id ?? "";
    }
    dockerAvailable.value = Boolean(executorStatus.executors.docker?.available);
    const appliedInitialDataset = applyInitialDatasetId(nextDatasets);
    const currentDatasetExists = nextDatasets.some((dataset) => dataset.id === form.value.datasetId);
    if (!appliedInitialDataset && (!form.value.datasetId || !currentDatasetExists) && nextDatasets[0]) {
      form.value.datasetId = nextDatasets[0].id;
    }
    await loadRuntimeProfilesForDataset();
    if (form.value.strategyVersionIds.length === 0) {
      form.value.strategyVersionIds = versionGroups.flat().map((version) => version.id);
    }
  } catch (error) {
    createError.value = error instanceof Error ? error.message : t("experiments.optionsFailed");
  } finally {
    loadingCreateOptions.value = false;
  }
}

async function loadRuntimeProfilesForDataset() {
  if (!form.value.datasetId || props.dataSource !== "api") {
    runtimeProfiles.value = [];
    runtimeBindingManifest.value = null;
    projectRuntimeProfiles.value = {};
    runtimeProfileBindings.value = {};
    form.value.runtimeProfileId = "";
    return;
  }
  const manifest = await getDatasetRuntimeBindingManifest(form.value.datasetId);
  runtimeBindingManifest.value = manifest;
  const nextProjectLabels: Record<string, string> = {};
  runtimeProfiles.value = await listDatasetRuntimeProfiles(form.value.datasetId);
  const grouped: Record<string, RuntimeProfileOut[]> = {};
  for (const project of manifest.projects) {
    nextProjectLabels[project.project_id] = project.project_name ?? project.project_id;
    grouped[project.project_id] = project.profiles;
  }
  projectLabels.value = nextProjectLabels;
  const projectIds = manifest.projects.map((project) => project.project_id).sort();
  projectRuntimeProfiles.value = grouped;
  const nextBindings: Record<string, string> = {};
  for (const projectId of projectIds) {
    const key = `project:${projectId}`;
    const current = runtimeProfileBindings.value[key];
    const choices = grouped[projectId] ?? [];
    nextBindings[key] = choices.some((profile) => profile.id === current) ? current : choices[0]?.id ?? "";
  }
  runtimeProfileBindings.value = nextBindings;
  if (!runtimeProfiles.value.some((profile) => profile.id === form.value.runtimeProfileId)) {
    form.value.runtimeProfileId = runtimeProfiles.value[0]?.id ?? "";
  }
}

function toggleStrategy(versionId: string) {
  const current = new Set(form.value.strategyVersionIds);
  if (current.has(versionId)) {
    current.delete(versionId);
  } else {
    current.add(versionId);
  }
  form.value.strategyVersionIds = [...current];
}

async function submitExperiment() {
  if (!canCreate.value) {
    return;
  }
  creating.value = true;
  createError.value = null;
  try {
    const option = selectedLlmOption.value;
    if (!option) {
      return;
    }
    const override = {
      provider: option.provider,
      model: option.model
    };
    const created = await createExperiment({
      id: form.value.id.trim() || null,
      name: form.value.name.trim(),
      dataset_id: form.value.datasetId,
      runtime_profile_id: isMultiProjectDataset.value ? null : form.value.runtimeProfileId,
      runtime_profile_bindings: isMultiProjectDataset.value ? runtimeProfileBindings.value : {},
      strategy_version_ids: form.value.strategyVersionIds,
      repeat_count: Number(form.value.repeatCount) || 1,
      llm_override: override
    });
    experiments.value = [created, ...experiments.value.filter((item) => item.id !== created.id)];
    openExperiment(created.id);
  } catch (error) {
    createError.value = error instanceof Error ? error.message : t("experiments.createFailed");
  } finally {
    creating.value = false;
  }
}

async function createDockerRuntimeProfile() {
  if (!form.value.datasetId || creatingRuntime.value) {
    return;
  }
  creatingRuntime.value = true;
  createError.value = null;
  try {
    const saved = await createDatasetRuntimeProfile(form.value.datasetId, {
      name: dockerProfileForm.value.name.trim() || "Docker pytest 3.12",
      executor: "docker",
      image: dockerProfileForm.value.image.trim(),
      working_dir: dockerProfileForm.value.workingDir.trim() || "/workspace",
      test_command: dockerProfileForm.value.testCommand.trim() || "python -m pytest tests -q",
      network_policy: dockerProfileForm.value.networkPolicy,
      timeout_seconds: Number(dockerProfileForm.value.timeoutSeconds) || 120,
      artifact_policy: { retain: "evidence", image_pull_policy: "never" },
      cleanup_policy: { mode: "manual", keep_failed: true }
    });
    await loadRuntimeProfilesForDataset();
    form.value.runtimeProfileId = saved.id;
  } catch (error) {
    createError.value = error instanceof Error ? error.message : t("runtime.saveFailed");
  } finally {
    creatingRuntime.value = false;
  }
}

function canStartFromList(experiment: ExperimentDefinition): boolean {
  return props.dataSource === "api" && experiment.status === "draft";
}

function statusActionHint(experiment: ExperimentDefinition): string {
  if (experiment.status === "queued" || experiment.status === "running") {
    return t(`status.${experiment.status}`);
  }
  if (experiment.status === "cancelled") {
    return t("experiments.cloneRequired");
  }
  return "";
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
  void loadCreateOptions();
});

watch(
  () => props.dataSource,
  () => {
    void loadExperiments();
    void loadCreateOptions();
  }
);

watch(
  () => form.value.datasetId,
  () => {
    void loadRuntimeProfilesForDataset();
  }
);

watch(
  () => props.initialDatasetId,
  () => {
    applyInitialDatasetId(datasets.value);
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
        <button v-if="props.dataSource === 'api'" class="text-button" type="button" @click="emit('navigate', '#/datasets/new')">
          <Plus :size="16" aria-hidden="true" />
          {{ t("datasets.create") }}
        </button>
        <button class="text-button" type="button" @click="loadExperiments">
          <RefreshCw :size="16" aria-hidden="true" />
          {{ t("projects.refresh") }}
        </button>
      </div>
    </section>

    <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>
    <p v-if="createError" class="error-banner">{{ createError }}</p>
    <p v-if="datasetSelectionWarning" class="warning-banner">{{ datasetSelectionWarning }}</p>

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

    <section v-if="props.dataSource === 'api'" class="subtle-panel create-panel">
      <div class="panel-title">
        <div>
          <p class="eyebrow">CREATE EXPERIMENT</p>
          <h2>{{ t("experiments.createTitle") }}</h2>
        </div>
        <button class="text-button" type="button" :disabled="!canCreate || creating" @click="submitExperiment">
          <Plus :size="16" aria-hidden="true" />
          {{ creating ? t("experiments.creating") : t("experiments.create") }}
        </button>
      </div>
      <div class="create-grid">
        <label>
          <span>{{ t("experiments.optionalId") }}</span>
          <input v-model="form.id" type="text" placeholder="exp-local-demo" />
        </label>
        <label>
          <span>{{ t("experiments.name") }}</span>
          <input v-model="form.name" type="text" />
        </label>
        <label>
          <span>{{ t("experiments.dataset") }}</span>
          <select v-model="form.datasetId">
            <option v-for="dataset in datasets" :key="dataset.id" :value="dataset.id">
              {{ dataset.name }} / {{ dataset.version }}
            </option>
          </select>
        </label>
        <label v-if="!isMultiProjectDataset">
          <span>{{ t("runtime.profileContract") }}</span>
          <select v-model="form.runtimeProfileId">
            <option v-for="profile in runtimeProfiles" :key="profile.id" :value="profile.id">
              {{ profile.name }} / {{ profile.executor }}
            </option>
          </select>
        </label>
        <label>
          <span>{{ t("experiments.repeat") }}</span>
          <input v-model.number="form.repeatCount" type="number" min="1" max="20" />
        </label>
        <label class="wide-field">
          <span>{{ t("experiments.llmOption") }}</span>
          <select v-model="form.llmOptionId">
            <option v-for="option in llmOptions" :key="option.id" :value="option.id" :disabled="!option.selectable">
              {{ option.label }} · {{ option.is_mock ? t("experiments.mockSource") : t("experiments.realLlm") }}{{ option.selectable ? "" : " · " + t("experiments.llmUnavailable") }}
            </option>
          </select>
        </label>
      </div>
      <p v-if="selectedLlmOption" class="runtime-note llm-note">
        {{ selectedLlmOption.provider }} / {{ selectedLlmOption.model }} ·
        {{ selectedLlmOption.config_source === "runtime_config" ? t("experiments.llmRuntimeConfig") : t("experiments.llmBuiltIn") }}
        <span v-if="!selectedLlmOption.selectable"> · {{ t("experiments.llmUnavailable") }}</span>
      </p>
      <p v-if="llmConfigStatus === 'error' && llmConfigError" class="runtime-note llm-note">
        {{ t("experiments.llmConfigError") }}: {{ llmConfigError }}
      </p>
      <div v-if="createBlockers.length" class="create-checklist" role="status">
        <strong>{{ t("experiments.createBlockedTitle") }}</strong>
        <ul>
          <li v-for="blocker in createBlockers" :key="blocker.id">
            <span>{{ blocker.message }}</span>
            <button v-if="blocker.id === 'dataset'" class="inline-link" type="button" @click="emit('navigate', '#/datasets/new')">
              {{ t("datasets.create") }}
            </button>
            <button v-else-if="blocker.id === 'runtime' && form.datasetId" class="inline-link" type="button" @click="showRuntimeProfileBox">
              {{ t("experiments.createDockerProfileAction") }}
            </button>
            <button v-else-if="blocker.id === 'strategy' || blocker.id === 'llm' || blocker.id === 'loading'" class="inline-link" type="button" @click="loadCreateOptions">
              {{ t("projects.refresh") }}
            </button>
          </li>
        </ul>
      </div>
      <div class="strategy-picker">
        <p v-if="!isMultiProjectDataset && form.runtimeProfileId" class="runtime-note">
          {{
            runtimeProfiles.find((profile) => profile.id === form.runtimeProfileId)?.executor ?? "local_subprocess"
          }}
          · {{ t("experiments.network") }}:
          {{ runtimeProfiles.find((profile) => profile.id === form.runtimeProfileId)?.network_policy ?? "default" }}
          · {{ t("experiments.timeout") }}:
          {{ runtimeProfiles.find((profile) => profile.id === form.runtimeProfileId)?.resource_limits?.timeout_seconds ?? 120 }}s
          · {{ t("experiments.dockerAvailability") }} {{ dockerAvailable ? t("experiments.available") : t("experiments.notAvailable") }}
        </p>
        <div v-if="isMultiProjectDataset" class="runtime-binding-box">
          <div class="docker-profile-head">
            <span>{{ t("experiments.runtimeBindings") }}</span>
          </div>
          <div class="binding-list">
            <label v-for="projectId in datasetProjectIds" :key="projectId">
              <span>{{ projectLabels[projectId] ?? projectId }}</span>
              <select v-model="runtimeProfileBindings[`project:${projectId}`]">
                <option v-for="profile in projectRuntimeProfiles[projectId] ?? []" :key="profile.id" :value="profile.id">
                  {{ profile.name }} / {{ profileSummary(profile) }}
                </option>
              </select>
            </label>
          </div>
        </div>
        <div ref="dockerProfileBox" class="docker-profile-box">
          <div class="docker-profile-head">
            <span>{{ t("experiments.createDockerProfile") }}</span>
            <button class="text-button" type="button" :disabled="!form.datasetId || creatingRuntime" @click="createDockerRuntimeProfile">
              <Plus :size="15" aria-hidden="true" />
              {{ creatingRuntime ? t("experiments.creatingDockerProfile") : t("experiments.createDockerProfileAction") }}
            </button>
          </div>
          <p class="runtime-note">{{ t("experiments.datasetRuntimeHint") }}</p>
          <div class="docker-profile-grid">
            <label>
              <span>{{ t("runtime.name") }}</span>
              <input v-model="dockerProfileForm.name" type="text" />
            </label>
            <label>
              <span>{{ t("runtime.dockerImage") }}</span>
              <input v-model="dockerProfileForm.image" type="text" placeholder="trace-pytest:3.12" />
            </label>
            <label>
              <span>{{ t("runtime.workingDirectory") }}</span>
              <input v-model="dockerProfileForm.workingDir" type="text" placeholder="/workspace" />
            </label>
            <label>
              <span>{{ t("runtime.pytestCommand") }}</span>
              <input v-model="dockerProfileForm.testCommand" type="text" />
            </label>
            <label>
              <span>{{ t("runtime.networkPolicy") }}</span>
              <select v-model="dockerProfileForm.networkPolicy">
                <option value="default">default</option>
                <option value="disabled">disabled</option>
                <option value="install_only">install_only</option>
              </select>
            </label>
            <label>
              <span>{{ t("runtime.timeoutSeconds") }}</span>
              <input v-model.number="dockerProfileForm.timeoutSeconds" type="number" min="1" />
            </label>
          </div>
        </div>
        <span>{{ t("experiments.strategy") }}</span>
        <div class="strategy-options">
          <button
            v-for="version in strategyVersions"
            :key="version.id"
            type="button"
            :class="{ selected: form.strategyVersionIds.includes(version.id) }"
            @click="toggleStrategy(version.id)"
          >
            <strong>{{ version.name }}</strong>
            <small>{{ version.id }}</small>
          </button>
        </div>
      </div>
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
            <td>
              <button class="inline-link" type="button" @click="openDataset(experiment.dataset_id)">
                {{ experiment.dataset_id }}
              </button>
            </td>
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
                  v-if="canStartFromList(experiment)"
                  class="text-button"
                  type="button"
                  :disabled="startingId === experiment.id"
                  @click="startExperiment(experiment)"
                >
                  <Play :size="15" aria-hidden="true" />
                  {{ startingId === experiment.id ? t("experiments.starting") : t("run.start") }}
                </button>
                <small v-else-if="props.dataSource === 'api' && statusActionHint(experiment)" class="row-hint">
                  {{ statusActionHint(experiment) }}
                </small>
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
  align-items: center;
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

.create-panel {
  display: grid;
  gap: 14px;
  margin-top: 18px;
  padding: 16px;
}

.panel-title {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.panel-title h2 {
  margin-top: 4px;
  font-size: 18px;
}

.create-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.create-grid label,
.strategy-picker,
.docker-profile-grid label,
.binding-list label {
  display: grid;
  gap: 6px;
}

.create-grid label.wide-field {
  grid-column: span 2;
}

.llm-note {
  margin: 0;
}

.create-checklist {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.72);
}

.create-checklist strong {
  font-size: 13px;
}

.create-checklist ul {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.create-checklist li {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  color: var(--muted-strong);
  font-size: 13px;
}

.create-grid span,
.strategy-picker > span,
.docker-profile-head span,
.docker-profile-grid span,
.binding-list span {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
}

.runtime-note {
  padding: 9px 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.68);
  color: var(--muted-strong);
  font-family: var(--font-mono);
  font-size: 11px;
}

.create-grid input,
.create-grid select,
.docker-profile-grid input,
.docker-profile-grid select,
.binding-list select {
  width: 100%;
  min-height: 34px;
  padding: 6px 9px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--ink);
}

.docker-profile-box,
.runtime-binding-box {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.56);
}

.docker-profile-head {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}

.docker-profile-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.binding-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.strategy-options {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.strategy-options button {
  display: grid;
  gap: 2px;
  justify-items: start;
  min-height: 52px;
  padding: 9px;
  text-align: left;
}

.strategy-options button.selected {
  border-color: var(--tool);
  background: rgba(49, 95, 125, 0.08);
  box-shadow: inset 3px 0 0 var(--tool);
}

.strategy-options small {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  overflow-wrap: anywhere;
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

.inline-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--tool);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
  overflow-wrap: anywhere;
  text-align: left;
}

.inline-link:hover {
  background: transparent;
  color: var(--ink);
  text-decoration: underline;
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

.row-hint {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
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
  .summary-strip,
  .create-grid,
  .docker-profile-grid,
  .binding-list,
  .strategy-options {
    grid-template-columns: 1fr;
  }

  .experiment-head {
    display: grid;
  }
}
</style>
