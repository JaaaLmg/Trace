<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ArrowRight, FolderGit2, RefreshCw } from "@lucide/vue";
import { listProjects } from "../api/projects";
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
const errorMessage = ref<string | null>(null);

async function loadProjects() {
  loading.value = true;
  errorMessage.value = null;
  try {
    projects.value = props.dataSource === "mock" ? mockProjects : await listProjects();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Failed to load projects.";
    projects.value = mockProjects;
  } finally {
    loading.value = false;
  }
}

function openDemoRun() {
  emit("navigate", "#/runs/run-demo-react-001");
}

onMounted(() => {
  void loadProjects();
});
</script>

<template>
  <main class="project-page app-page">
    <section class="project-head">
      <div>
        <p class="eyebrow">TRACE / PROJECTS</p>
        <h1>运行档案入口</h1>
        <p>
          C 线 V1 不做大而全后台。项目页只负责把用户带到一次 run，真正的主屏是 trace、report 和 pytest 证据。
        </p>
      </div>
      <div class="head-actions">
        <button class="text-button" type="button" @click="loadProjects">
          <RefreshCw :size="16" aria-hidden="true" />
          Refresh
        </button>
        <button class="primary-action" type="button" @click="openDemoRun">
          <ArrowRight :size="17" aria-hidden="true" />
          Open Demo Run
        </button>
      </div>
    </section>

    <p v-if="errorMessage" class="error-banner">{{ errorMessage }} 已回退到 mock 项目。</p>

    <section class="project-grid">
      <article v-for="project in projects" :key="project.id" class="project-card">
        <div class="project-icon">
          <FolderGit2 :size="22" aria-hidden="true" />
        </div>
        <div class="project-main">
          <p class="eyebrow">{{ project.framework }} / {{ project.language }}</p>
          <h3>{{ project.name }}</h3>
          <p>{{ project.description || "No description." }}</p>
          <code>{{ project.local_path }}</code>
        </div>
        <button class="icon-button" type="button" title="进入最近 run" @click="openDemoRun">
          <ArrowRight :size="18" aria-hidden="true" />
          <span class="sr-only">进入最近 run</span>
        </button>
      </article>
    </section>

    <section class="plan-strip">
      <p class="eyebrow">V1 TEST PLAN</p>
      <h2>{{ mockPlans[0].name }}</h2>
      <p>{{ mockPlans[0].goal }}</p>
      <code>{{ mockPlans[0].target_scope.join(", ") }}</code>
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

@media (max-width: 860px) {
  .project-head,
  .project-grid {
    grid-template-columns: 1fr;
  }

  .head-actions {
    justify-content: flex-start;
  }
}
</style>
