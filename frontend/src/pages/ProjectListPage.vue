<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ArrowRight, FolderGit2, Layers3, Play, Plus, RefreshCw, ServerCrash } from "@lucide/vue";
import {
  createProject,
  createSnapshot,
  createTestPlan,
  listProjectTestPlans,
  listProjectTestRuns,
  listProjects,
  listSnapshots
} from "../api/projects";
import { createRun } from "../api/runs";
import PathPickerField from "../components/PathPickerField.vue";
import { useI18n } from "../i18n";
import { demoPlans, demoProjects, demoSnapshots } from "../demo/staticRunFixture";
import type { ProjectOut, ProjectSnapshotOut, TestPlanOut, TestRunOut } from "../types/api";
import type { DataSource } from "../types/ui";

const props = defineProps<{
  dataSource: DataSource;
}>();

const emit = defineEmits<{
  navigate: [hash: string];
}>();

const { t } = useI18n();

const projects = ref<ProjectOut[]>([]);
const selectedProjectId = ref<string | null>(null);
const selectedPlanId = ref<string | null>(null);
const snapshots = ref<ProjectSnapshotOut[]>([]);
const plans = ref<TestPlanOut[]>([]);
const runs = ref<TestRunOut[]>([]);
const loadingProjects = ref(false);
const loadingDetails = ref(false);
const creatingProject = ref(false);
const creatingSnapshot = ref(false);
const startingRun = ref(false);
const errorMessage = ref<string | null>(null);

const projectForm = reactive({
  name: "",
  localPath: "",
  description: ""
});

const snapshotRoot = ref("");
const runForm = reactive({
  planName: "",
  goal: "",
  targetScope: ".",
  timeoutSeconds: 120,
  allowReflection: true,
  strategyVersionId: "sv-react-v1",
  snapshotId: ""
});

const selectedProject = computed(() => projects.value.find((project) => project.id === selectedProjectId.value) ?? null);
const selectedPlan = computed(() => plans.value.find((plan) => plan.id === selectedPlanId.value) ?? null);
const latestRun = computed(() => runs.value[0] ?? null);

function openDemoRun() {
  emit("navigate", "#/runs/run-demo-react-001");
}

function applyProjectDefaults(project: ProjectOut | null) {
  snapshotRoot.value = project?.local_path ?? "";
  runForm.planName = t("projects.planName");
  runForm.goal = t("projects.planGoal");
  runForm.targetScope = ".";
  runForm.timeoutSeconds = 120;
  runForm.allowReflection = true;
  runForm.strategyVersionId = "sv-react-v1";
}

function planScopeText(plan: TestPlanOut): string {
  return plan.target_scope.length > 0 ? plan.target_scope.join(", ") : t("common.none");
}

function planBudgetText(plan: TestPlanOut): string {
  const timeout = plan.budget.timeout_seconds ?? t("common.unknown");
  const reflection = plan.budget.allow_reflection ? t("common.yes") : t("common.no");
  return `${t("projects.timeout")}: ${timeout} / ${t("projects.allowReflection")}: ${reflection}`;
}

function usePlan(plan: TestPlanOut) {
  selectedPlanId.value = plan.id;
  runForm.planName = plan.name;
  runForm.goal = plan.goal;
  runForm.targetScope = planScopeText(plan) === t("common.none") ? "." : planScopeText(plan);
  runForm.timeoutSeconds = Number(plan.budget.timeout_seconds ?? 120);
  runForm.allowReflection = Boolean(plan.budget.allow_reflection ?? false);
  runForm.strategyVersionId = plan.default_strategy_version_id ?? "sv-react-v1";
}

async function loadProjects() {
  loadingProjects.value = true;
  errorMessage.value = null;
  try {
    projects.value = props.dataSource === "demo" ? demoProjects : await listProjects();
    if (!selectedProjectId.value || !projects.value.some((project) => project.id === selectedProjectId.value)) {
      selectedProjectId.value = projects.value[0]?.id ?? null;
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t("projects.errorFallback");
    projects.value = [];
    selectedProjectId.value = projects.value[0]?.id ?? null;
  } finally {
    loadingProjects.value = false;
  }
}

async function loadProjectDetails() {
  const project = selectedProject.value;
  if (!project) {
    snapshots.value = [];
    plans.value = [];
    runs.value = [];
    selectedPlanId.value = null;
    applyProjectDefaults(null);
    return;
  }

  applyProjectDefaults(project);
  loadingDetails.value = true;
  errorMessage.value = null;
  try {
    if (props.dataSource === "demo") {
      snapshots.value = demoSnapshots.filter((snapshot) => snapshot.project_id === project.id);
      plans.value = demoPlans.filter((plan) => plan.project_id === project.id);
      runs.value = [];
      runForm.snapshotId = snapshots.value[0]?.id ?? "";
      selectedPlanId.value = plans.value[0]?.id ?? null;
      return;
    }
    const [nextSnapshots, nextPlans, nextRuns] = await Promise.all([
      listSnapshots(project.id),
      listProjectTestPlans(project.id),
      listProjectTestRuns(project.id)
    ]);
    snapshots.value = nextSnapshots;
    plans.value = nextPlans;
    runs.value = nextRuns;
    selectedPlanId.value = nextPlans[0]?.id ?? null;
    runForm.snapshotId =
      nextSnapshots.find((snapshot) => snapshot.root_path === project.local_path)?.id ?? nextSnapshots[0]?.id ?? "";
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t("projects.detailsFailed");
    snapshots.value = [];
    plans.value = [];
    runs.value = [];
    selectedPlanId.value = null;
  } finally {
    loadingDetails.value = false;
  }
}

async function submitProject() {
  if (props.dataSource !== "api") {
    return;
  }
  creatingProject.value = true;
  errorMessage.value = null;
  try {
    const project = await createProject({
      name: projectForm.name.trim(),
      local_path: projectForm.localPath.trim(),
      description: projectForm.description.trim() || null
    });
    projectForm.name = "";
    projectForm.localPath = "";
    projectForm.description = "";
    await loadProjects();
    selectedProjectId.value = project.id;
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t("projects.createFailed");
  } finally {
    creatingProject.value = false;
  }
}

async function submitSnapshot() {
  const project = selectedProject.value;
  if (!project || props.dataSource !== "api") {
    return;
  }
  creatingSnapshot.value = true;
  errorMessage.value = null;
  try {
    const snapshot = await createSnapshot(project.id, { root_path: snapshotRoot.value.trim() || project.local_path });
    await loadProjectDetails();
    runForm.snapshotId = snapshot.id;
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t("projects.snapshotFailed");
  } finally {
    creatingSnapshot.value = false;
  }
}

function targetScopeList(): string[] {
  return runForm.targetScope
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

async function startRun() {
  const project = selectedProject.value;
  if (!project) {
    return;
  }
  if (props.dataSource !== "api") {
    openDemoRun();
    return;
  }
  startingRun.value = true;
  errorMessage.value = null;
  try {
    let snapshotId = runForm.snapshotId;
    if (!snapshotId) {
      const snapshot = await createSnapshot(project.id, { root_path: snapshotRoot.value.trim() || project.local_path });
      snapshotId = snapshot.id;
    }
    const plan = await createTestPlan({
      project_id: project.id,
      name: runForm.planName.trim() || t("projects.planName"),
      target_scope: targetScopeList(),
      goal: runForm.goal.trim() || t("projects.planGoal"),
      budget: {
        timeout_seconds: Number(runForm.timeoutSeconds) || 120,
        allow_reflection: runForm.allowReflection
      },
      output_options: { save_full_trace: true },
      default_strategy_version_id: runForm.strategyVersionId || "sv-react-v1"
    });
    const run = await createRun(plan.id, {
      snapshot_id: snapshotId,
      strategy_version_id: plan.default_strategy_version_id,
      budget_override: {
        timeout_seconds: Number(runForm.timeoutSeconds) || 120,
        allow_reflection: runForm.allowReflection
      },
      output_options: { save_full_trace: true }
    });
    emit("navigate", `#/runs/${run.id}`);
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t("run.creationFailed");
  } finally {
    startingRun.value = false;
  }
}

function selectProject(projectId: string) {
  selectedProjectId.value = projectId;
}

onMounted(() => {
  void loadProjects();
});

watch(
  () => props.dataSource,
  () => {
    selectedProjectId.value = null;
    void loadProjects();
  }
);

watch(selectedProjectId, () => {
  void loadProjectDetails();
});
</script>

<template>
  <main class="project-page app-page">
    <section class="project-head">
      <div>
        <p class="eyebrow">TRACE / PROJECTS</p>
        <h1>{{ t("projects.title") }}</h1>
        <p>{{ t("projects.subtitle") }}</p>
      </div>
      <div class="head-actions">
        <button class="text-button" type="button" @click="loadProjects">
          <RefreshCw :size="16" aria-hidden="true" />
          {{ t("projects.refresh") }}
        </button>
        <button v-if="props.dataSource === 'demo'" class="primary-action" type="button" @click="openDemoRun">
          <ArrowRight :size="17" aria-hidden="true" />
          {{ t("projects.openDemo") }}
        </button>
      </div>
    </section>

    <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

    <section v-if="props.dataSource === 'api'" class="create-project subtle-panel">
      <div>
        <p class="eyebrow">{{ t("projects.createProject") }}</p>
        <h2>{{ t("projects.registerProject") }}</h2>
      </div>
      <form class="project-form" @submit.prevent="submitProject">
        <label>
          <span>{{ t("projects.projectName") }}</span>
          <input v-model="projectForm.name" required type="text" :placeholder="t('projects.projectNamePlaceholder')" />
        </label>
        <PathPickerField
          v-model="projectForm.localPath"
          :label="t('projects.localPath')"
          :placeholder="t('projects.localPathPlaceholder')"
          :picker-title="t('pathPicker.projectTitle')"
          required
        />
        <label>
          <span>{{ t("projects.description") }}</span>
          <input v-model="projectForm.description" type="text" :placeholder="t('projects.descriptionPlaceholder')" />
        </label>
        <button class="primary-action" type="submit" :disabled="creatingProject">
          <Plus :size="17" aria-hidden="true" />
          {{ creatingProject ? t("projects.creating") : t("projects.createProject") }}
        </button>
      </form>
    </section>

    <section class="workspace-grid">
      <aside class="project-list subtle-panel">
        <div class="panel-head">
          <div>
            <p class="eyebrow">{{ t("projects.availableProjects") }}</p>
            <h2>{{ projects.length }}</h2>
          </div>
          <RefreshCw v-if="loadingProjects" :size="18" aria-hidden="true" />
        </div>
        <button
          v-for="project in projects"
          :key="project.id"
          type="button"
          class="project-row"
          :class="{ selected: project.id === selectedProjectId }"
          @click="selectProject(project.id)"
        >
          <FolderGit2 :size="18" aria-hidden="true" />
          <span>
            <strong>{{ project.name }}</strong>
            <small>{{ project.local_path }}</small>
          </span>
        </button>
        <div v-if="!loadingProjects && projects.length === 0" class="empty-state">
          <ServerCrash :size="22" aria-hidden="true" />
          <h3>{{ t("projects.emptyTitle") }}</h3>
          <p>{{ t("projects.emptyBody") }}</p>
        </div>
      </aside>

      <section class="project-detail">
        <template v-if="selectedProject">
          <article class="project-overview subtle-panel">
            <div>
              <p class="eyebrow">{{ selectedProject.framework }} / {{ selectedProject.language }}</p>
              <h2>{{ selectedProject.name }}</h2>
              <p>{{ selectedProject.description || t("projects.noDescription") }}</p>
              <code>{{ selectedProject.local_path }}</code>
            </div>
            <button class="primary-action" type="button" :disabled="startingRun" @click="startRun">
              <Play :size="17" aria-hidden="true" />
              {{ startingRun ? t("projects.running") : t("projects.startRun") }}
            </button>
          </article>

          <section class="management-grid">
            <article class="subtle-panel management-panel">
              <div class="panel-head">
                <div>
                  <p class="eyebrow">{{ t("projects.snapshots") }}</p>
                  <h3>{{ snapshots.length }}</h3>
                </div>
                <Layers3 :size="18" aria-hidden="true" />
              </div>
              <form v-if="props.dataSource === 'api'" class="stack-form" @submit.prevent="submitSnapshot">
                <PathPickerField
                  v-model="snapshotRoot"
                  :label="t('projects.snapshotRoot')"
                  :initial-path="selectedProject.local_path"
                  :picker-title="t('pathPicker.snapshotTitle')"
                  required
                />
                <button class="text-button" type="submit" :disabled="creatingSnapshot">
                  <Plus :size="15" aria-hidden="true" />
                  {{ creatingSnapshot ? t("projects.creating") : t("projects.createSnapshot") }}
                </button>
              </form>
              <div class="compact-list">
                <label v-for="snapshot in snapshots" :key="snapshot.id" class="choice-row">
                  <input v-model="runForm.snapshotId" type="radio" :value="snapshot.id" />
                  <span>
                    <strong>{{ snapshot.id }}</strong>
                    <small>{{ snapshot.root_path }}</small>
                  </span>
                </label>
                <p v-if="snapshots.length === 0" class="muted-note">{{ t("projects.noSnapshots") }}</p>
              </div>
            </article>

            <article class="subtle-panel management-panel">
              <div class="panel-head">
                <div>
                  <p class="eyebrow">{{ t("projects.newPlanRun") }}</p>
                  <h3>{{ t("projects.runConfig") }}</h3>
                </div>
              </div>
              <form class="stack-form" @submit.prevent="startRun">
                <label>
                  <span>{{ t("projects.planNameLabel") }}</span>
                  <input v-model="runForm.planName" type="text" />
                </label>
                <label>
                  <span>{{ t("projects.goal") }}</span>
                  <textarea v-model="runForm.goal" rows="3"></textarea>
                </label>
                <label>
                  <span>{{ t("projects.planScope") }}</span>
                  <input v-model="runForm.targetScope" type="text" />
                </label>
                <div class="form-row">
                  <label>
                    <span>{{ t("projects.timeout") }}</span>
                    <input v-model.number="runForm.timeoutSeconds" min="1" type="number" />
                  </label>
                  <label>
                    <span>{{ t("projects.strategy") }}</span>
                    <select v-model="runForm.strategyVersionId">
                      <option value="sv-react-v1">ReAct+Reflection v1</option>
                      <option value="sv-plan-v1">Plan-and-Execute v1</option>
                      <option value="sv-direct-v1">Direct v1</option>
                    </select>
                  </label>
                </div>
                <label class="checkbox-row">
                  <input v-model="runForm.allowReflection" type="checkbox" />
                  <span>{{ t("projects.allowReflection") }}</span>
                </label>
                <button class="primary-action" type="submit" :disabled="startingRun">
                  <Play :size="17" aria-hidden="true" />
                  {{ startingRun ? t("projects.running") : t("projects.startRun") }}
                </button>
              </form>
            </article>
          </section>

          <section class="history-grid">
            <article class="subtle-panel history-panel">
              <div class="panel-head">
                <div>
                  <p class="eyebrow">{{ t("projects.plans") }}</p>
                  <h3>{{ plans.length }}</h3>
                </div>
              </div>
              <div class="compact-list plan-list">
                <button
                  v-for="plan in plans"
                  :key="plan.id"
                  class="plan-row"
                  :class="{ selected: plan.id === selectedPlanId }"
                  type="button"
                  @click="selectedPlanId = plan.id"
                >
                  <span>
                    <strong>{{ plan.name }}</strong>
                    <small>{{ plan.goal }}</small>
                  </span>
                  <span class="plan-meta">
                    <small>{{ t("projects.planScope") }}: {{ planScopeText(plan) }}</small>
                    <small>{{ planBudgetText(plan) }}</small>
                  </span>
                </button>
                <p v-if="plans.length === 0" class="muted-note">{{ t("projects.noPlans") }}</p>
              </div>
              <div v-if="selectedPlan" class="plan-detail">
                <div class="panel-head">
                  <div>
                    <p class="eyebrow">{{ t("projects.planDetail") }}</p>
                    <h3>{{ selectedPlan.name }}</h3>
                  </div>
                  <button class="text-button" type="button" @click="usePlan(selectedPlan)">
                    <Play :size="15" aria-hidden="true" />
                    {{ t("projects.usePlan") }}
                  </button>
                </div>
                <dl>
                  <div>
                    <dt>{{ t("projects.goal") }}</dt>
                    <dd>{{ selectedPlan.goal }}</dd>
                  </div>
                  <div>
                    <dt>{{ t("projects.planScope") }}</dt>
                    <dd>{{ planScopeText(selectedPlan) }}</dd>
                  </div>
                  <div>
                    <dt>{{ t("projects.strategy") }}</dt>
                    <dd>{{ selectedPlan.default_strategy_version_id ?? t("common.none") }}</dd>
                  </div>
                  <div>
                    <dt>{{ t("projects.budget") }}</dt>
                    <dd>{{ planBudgetText(selectedPlan) }}</dd>
                  </div>
                  <div>
                    <dt>{{ t("projects.created") }}</dt>
                    <dd>{{ new Date(selectedPlan.created_at).toLocaleString() }}</dd>
                  </div>
                </dl>
              </div>
            </article>

            <article class="subtle-panel history-panel">
              <div class="panel-head">
                <div>
                  <p class="eyebrow">{{ t("projects.runs") }}</p>
                  <h3>{{ runs.length }}</h3>
                </div>
                <button v-if="latestRun" class="text-button" type="button" @click="emit('navigate', `#/runs/${latestRun.id}`)">
                  <ArrowRight :size="15" aria-hidden="true" />
                  {{ t("projects.openLatest") }}
                </button>
              </div>
              <div class="compact-list">
                <button v-for="run in runs" :key="run.id" class="run-row" type="button" @click="emit('navigate', `#/runs/${run.id}`)">
                  <span>
                    <strong>{{ run.status }}</strong>
                    <small>{{ run.id }}</small>
                  </span>
                  <ArrowRight :size="15" aria-hidden="true" />
                </button>
                <p v-if="runs.length === 0" class="muted-note">{{ t("projects.noRuns") }}</p>
              </div>
            </article>
          </section>
        </template>

        <section v-else class="empty-state subtle-panel">
          <ServerCrash :size="24" aria-hidden="true" />
          <h2>{{ t("projects.emptyTitle") }}</h2>
          <p>{{ t("projects.emptyBody") }}</p>
        </section>

        <p v-if="loadingDetails" class="mode-note">{{ t("projects.loadingDetails") }}</p>
      </section>
    </section>
  </main>
</template>

<style scoped>
.project-head,
.create-project,
.project-overview,
.panel-head {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}

.project-head {
  padding: 18px 0 24px;
  border-bottom: 1px solid var(--border);
}

.project-head h1 {
  margin: 8px 0 10px;
}

.project-head p {
  max-width: 760px;
  font-family: var(--font-serif);
}

.head-actions,
.form-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.error-banner {
  margin: 18px 0 0;
  padding: 10px 12px;
  border: 1px solid rgba(159, 58, 47, 0.22);
  border-radius: 7px;
  background: rgba(159, 58, 47, 0.08);
  color: var(--failed);
}

.create-project {
  margin-top: 18px;
  padding: 18px;
}

.project-form {
  display: grid;
  grid-template-columns: minmax(140px, 0.8fr) minmax(260px, 1.4fr) minmax(160px, 1fr) auto;
  gap: 10px;
  align-items: end;
  width: min(980px, 100%);
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(260px, 340px) minmax(0, 1fr);
  gap: 18px;
  margin-top: 18px;
}

.project-list,
.project-overview,
.management-panel,
.history-panel,
.empty-state {
  padding: 18px;
}

.project-list {
  align-self: start;
}

.project-row,
.run-row,
.plan-row {
  width: 100%;
  display: flex;
  gap: 10px;
  align-items: flex-start;
  justify-content: space-between;
  margin-top: 10px;
  padding: 10px;
  text-align: left;
  transition:
    background-color var(--motion-fast) var(--ease-standard),
    border-color var(--motion-fast) var(--ease-standard),
    box-shadow var(--motion-fast) var(--ease-standard),
    transform var(--motion-fast) var(--ease-standard);
}

.project-row:hover:not(.selected),
.run-row:hover,
.plan-row:hover:not(.selected) {
  border-color: var(--border-strong);
  background: rgba(251, 250, 247, 0.9);
  box-shadow: var(--shadow-hover);
  transform: translateY(-1px);
}

.project-row.selected {
  border-color: var(--ink);
  box-shadow: inset 3px 0 0 var(--ink);
}

.plan-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
}

.plan-row.selected {
  border-color: var(--tool);
  background: rgba(49, 95, 125, 0.08);
  box-shadow: inset 3px 0 0 var(--tool);
}

.plan-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.project-row span,
.run-row span,
.choice-row span,
.data-row {
  min-width: 0;
  display: grid;
  gap: 3px;
}

small {
  overflow-wrap: anywhere;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
}

.project-detail {
  display: grid;
  gap: 18px;
  min-width: 0;
}

.project-overview code {
  display: inline-block;
  max-width: 100%;
  margin-top: 10px;
  overflow: auto;
}

.management-grid,
.history-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.stack-form,
.compact-list,
.empty-state {
  display: grid;
  gap: 10px;
}

.stack-form {
  margin-top: 14px;
}

label {
  display: grid;
  gap: 5px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}

input,
select,
textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--ink);
  padding: 8px 9px;
}

textarea {
  resize: vertical;
}

.checkbox-row,
.choice-row {
  display: flex;
  gap: 9px;
  align-items: flex-start;
}

.checkbox-row input,
.choice-row input {
  width: auto;
  margin-top: 3px;
}

.data-row,
.choice-row {
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.62);
}

.data-row code {
  justify-self: start;
}

.plan-detail {
  display: grid;
  gap: 12px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}

.plan-detail dl {
  display: grid;
  gap: 10px;
  margin: 0;
}

.plan-detail dl > div {
  display: grid;
  gap: 3px;
}

.plan-detail dt {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
}

.plan-detail dd {
  margin: 0;
  color: var(--muted-strong);
  overflow-wrap: anywhere;
}

.mode-note,
.muted-note {
  color: var(--muted);
  font-size: 13px;
}

@media (max-width: 1080px) {
  .workspace-grid,
  .management-grid,
  .history-grid,
  .project-form {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .project-head,
  .create-project,
  .project-overview,
  .panel-head {
    display: grid;
  }
}
</style>
