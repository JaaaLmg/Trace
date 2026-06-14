<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { ArrowRight, FolderGit2, Play, RefreshCw } from "@lucide/vue";
import { createSnapshot, createTestPlan, listProjects, listSnapshots } from "../api/projects";
import { createRun } from "../api/runs";
import { useI18n } from "../i18n";
import { mockPlans, mockProjects } from "../mock/data";
import type { ProjectOut } from "../types/api";
import type { DataSource } from "../types/ui";

const props = defineProps<{
  dataSource: DataSource;
}>();

const emit = defineEmits<{
  navigate: [hash: string];
}>();

const projects = ref<ProjectOut[]>([]);
const loading = ref(false);
const startingProjectId = ref<string | null>(null);
const errorMessage = ref<string | null>(null);
const { t } = useI18n();

async function loadProjects() {
  loading.value = true;
  errorMessage.value = null;
  try {
    projects.value = props.dataSource === "mock" ? mockProjects : await listProjects();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t("projects.errorFallback");
    projects.value = mockProjects;
  } finally {
    loading.value = false;
  }
}

function openMockRun() {
  emit("navigate", "#/runs/run-demo-react-001");
}

async function startProjectRun(project: ProjectOut) {
  if (props.dataSource !== "api") {
    openMockRun();
    return;
  }

  startingProjectId.value = project.id;
  errorMessage.value = null;
  try {
    const snapshots = await listSnapshots(project.id);
    const snapshot =
      snapshots.find((item) => item.root_path === project.local_path) ??
      (await createSnapshot(project.id, { root_path: project.local_path }));
    const plan = await createTestPlan({
      project_id: project.id,
      name: t("projects.planName"),
      target_scope: ["."],
      goal: t("projects.planGoal"),
      budget: { timeout_seconds: 120, allow_reflection: true },
      output_options: { save_full_trace: true },
      default_strategy_version_id: "sv-react-v1"
    });
    const run = await createRun(plan.id, {
      snapshot_id: snapshot.id,
      strategy_version_id: plan.default_strategy_version_id,
      budget_override: { timeout_seconds: 120, allow_reflection: true },
      output_options: { save_full_trace: true }
    });
    emit("navigate", `#/runs/${run.id}`);
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t("run.creationFailed");
  } finally {
    startingProjectId.value = null;
  }
}

onMounted(() => {
  void loadProjects();
});

watch(
  () => props.dataSource,
  () => {
    void loadProjects();
  }
);
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
        <button v-if="props.dataSource === 'mock'" class="primary-action" type="button" @click="openMockRun">
          <ArrowRight :size="17" aria-hidden="true" />
          {{ t("projects.openMock") }}
        </button>
      </div>
    </section>

    <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>
    <p v-if="props.dataSource === 'api'" class="mode-note">{{ t("projects.apiHint") }}</p>
    <p v-if="loading" class="mode-note">{{ t("projects.loading") }}</p>

    <section class="project-grid">
      <article v-for="project in projects" :key="project.id" class="project-card">
        <div class="project-icon">
          <FolderGit2 :size="22" aria-hidden="true" />
        </div>
        <div class="project-main">
          <p class="eyebrow">{{ project.framework }} / {{ project.language }}</p>
          <h3>{{ project.name }}</h3>
          <p>{{ project.description || t("projects.noDescription") }}</p>
          <code>{{ project.local_path }}</code>
        </div>
        <button
          class="primary-action run-action"
          type="button"
          :title="t('projects.startRun')"
          :disabled="startingProjectId === project.id"
          @click="startProjectRun(project)"
        >
          <RefreshCw v-if="startingProjectId === project.id" :size="17" aria-hidden="true" />
          <Play v-else-if="props.dataSource === 'api'" :size="17" aria-hidden="true" />
          <ArrowRight v-else :size="17" aria-hidden="true" />
          <span>{{ startingProjectId === project.id ? t("projects.running") : t("projects.startRun") }}</span>
        </button>
      </article>
    </section>

    <section v-if="!loading && projects.length === 0" class="empty-state subtle-panel">
      <h2>{{ t("projects.emptyTitle") }}</h2>
      <p>{{ t("projects.emptyBody") }}</p>
    </section>

    <section v-if="props.dataSource === 'mock'" class="plan-strip">
      <p class="eyebrow">V1 TEST PLAN</p>
      <h2>{{ mockPlans[0].name }}</h2>
      <p>{{ mockPlans[0].goal }}</p>
      <code>{{ t("projects.planScope") }}: {{ mockPlans[0].target_scope.join(", ") }}</code>
    </section>
  </main>
</template>

<style scoped>
.project-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  align-items: end;
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

.head-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.error-banner {
  margin: 18px 0 0;
  padding: 10px 12px;
  border: 1px solid rgba(159, 58, 47, 0.22);
  border-radius: 7px;
  background: rgba(159, 58, 47, 0.08);
  color: var(--failed);
}

.mode-note {
  margin: 14px 0 0;
  color: var(--muted);
  font-size: 13px;
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 22px;
}

.project-card {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) auto;
  gap: 14px;
  align-items: start;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: rgba(255, 255, 255, 0.78);
  box-shadow: var(--shadow);
}

.project-icon {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--panel-soft);
  color: var(--tool);
}

.project-main {
  min-width: 0;
}

.project-main h3 {
  margin: 6px 0 8px;
}

.project-main code {
  display: inline-block;
  max-width: 100%;
  margin-top: 10px;
  overflow: auto;
}

.plan-strip {
  margin-top: 22px;
  padding: 20px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: rgba(246, 243, 238, 0.76);
}

.plan-strip h2 {
  margin: 6px 0 8px;
}

.plan-strip code {
  display: inline-block;
  margin-top: 10px;
}

.empty-state {
  display: grid;
  gap: 8px;
  margin-top: 22px;
  padding: 22px;
}

.run-action {
  min-width: 126px;
  white-space: nowrap;
}

@media (max-width: 860px) {
  .project-head,
  .project-grid {
    grid-template-columns: 1fr;
  }

  .head-actions {
    justify-content: flex-start;
  }

  .project-card {
    grid-template-columns: 44px minmax(0, 1fr);
  }

  .run-action {
    grid-column: 2;
    justify-self: start;
  }
}
</style>
