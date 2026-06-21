<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { BarChart3, Beaker, Database, FolderGit2, MonitorDot, Server, SlidersHorizontal } from "@lucide/vue";
import ComparisonPage from "./pages/ComparisonPage.vue";
import DatasetDetailPage from "./pages/DatasetDetailPage.vue";
import ExperimentDetailPage from "./pages/ExperimentDetailPage.vue";
import ExperimentListPage from "./pages/ExperimentListPage.vue";
import ProjectListPage from "./pages/ProjectListPage.vue";
import RuntimeProfilePage from "./pages/RuntimeProfilePage.vue";
import RunConsolePage from "./pages/RunConsolePage.vue";
import { useI18n, type Locale } from "./i18n";
import type { DataSource } from "./types/ui";

const initialSource = (import.meta.env.VITE_TRACE_DATA_SOURCE === "demo" ? "demo" : "api") as DataSource;
const dataSource = ref<DataSource>(initialSource);
const sampleRunId = "run-demo-react-001";
const sampleExperimentId = "exp-demo-v2-static";
const sampleDatasetId = "dataset-demo-v2";
const defaultHash = computed(() => (dataSource.value === "demo" ? "#/runs/run-demo-react-001" : "#/projects"));
const currentHash = ref(window.location.hash || defaultHash.value);
const { locale, setLocale, t } = useI18n();

const route = computed(() => {
  const hash = currentHash.value.replace(/^#/, "") || defaultHash.value.replace(/^#/, "");
  const parts = hash.split("/").filter(Boolean);
  return {
    name: parts[0] ?? (dataSource.value === "demo" ? "runs" : "projects"),
    id: parts[1] ?? (dataSource.value === "demo" ? sampleRunId : "")
  };
});

const runId = computed(() => {
  if (route.value.name === "runs") {
    return route.value.id || (dataSource.value === "demo" ? sampleRunId : "");
  }
  return dataSource.value === "demo" ? sampleRunId : "";
});

const runConsoleHref = computed(() => {
  if (dataSource.value === "api") {
    return route.value.name === "runs" && runId.value ? `#/runs/${runId.value}` : "#/projects";
  }
  return `#/runs/${sampleRunId}`;
});

function syncHash() {
  currentHash.value = window.location.hash || defaultHash.value;
}

function navigate(hash: string) {
  window.location.hash = hash;
  syncHash();
}

function demoHashForRoute(name: string, id: string): string {
  if (name === "runs") {
    return `#/runs/${sampleRunId}`;
  }
  if (name === "experiments") {
    return id ? `#/experiments/${sampleExperimentId}` : "#/experiments";
  }
  if (name === "datasets") {
    return `#/datasets/${sampleDatasetId}`;
  }
  if (name === "comparison") {
    return "#/comparison";
  }
  if (name === "runtime") {
    return "#/runtime";
  }
  if (name === "projects") {
    return "#/projects";
  }
  return `#/runs/${sampleRunId}`;
}

function apiHashForRoute(name: string, id: string): string | null {
  if (name === "runs" && id === sampleRunId) {
    return "#/projects";
  }
  if (name === "experiments" && id === sampleExperimentId) {
    return "#/experiments";
  }
  if (name === "datasets" && id === sampleDatasetId) {
    return "#/experiments";
  }
  return null;
}

function setSource(source: DataSource) {
  const currentRoute = route.value;
  dataSource.value = source;
  if (source === "demo") {
    navigate(demoHashForRoute(currentRoute.name, currentRoute.id));
    return;
  }
  const apiHash = apiHashForRoute(currentRoute.name, currentRoute.id);
  if (apiHash) {
    navigate(apiHash);
  }
}

onMounted(() => {
  if (!window.location.hash) {
    window.location.hash = defaultHash.value;
  }
  window.addEventListener("hashchange", syncHash);
});

onBeforeUnmount(() => {
  window.removeEventListener("hashchange", syncHash);
});
</script>

<template>
  <header class="app-nav">
    <a class="nav-brand" :href="dataSource === 'demo' ? `#/runs/${sampleRunId}` : '#/projects'">
      <img src="/trace-logo-icon.svg" alt="" />
      <span>TRACE</span>
    </a>
    <nav class="nav-links" aria-label="Primary navigation">
      <a href="#/projects" :class="{ active: route.name === 'projects' }">
        <FolderGit2 :size="16" aria-hidden="true" />
        {{ t("app.projects") }}
      </a>
      <a :href="runConsoleHref" :class="{ active: route.name === 'runs' }">
        <MonitorDot :size="16" aria-hidden="true" />
        {{ t("app.runConsole") }}
      </a>
      <a href="#/experiments" :class="{ active: route.name === 'experiments' }">
        <Beaker :size="16" aria-hidden="true" />
        {{ t("app.experiments") }}
      </a>
      <a :href="dataSource === 'demo' ? `#/datasets/${sampleDatasetId}` : '#/datasets/new'" :class="{ active: route.name === 'datasets' }">
        <Database :size="16" aria-hidden="true" />
        {{ t("app.datasets") }}
      </a>
      <a href="#/runtime" :class="{ active: route.name === 'runtime' }">
        <SlidersHorizontal :size="16" aria-hidden="true" />
        {{ t("app.runtime") }}
      </a>
      <a href="#/comparison" :class="{ active: route.name === 'comparison' }">
        <BarChart3 :size="16" aria-hidden="true" />
        {{ t("app.comparison") }}
      </a>
    </nav>
    <div class="nav-controls">
      <div class="source-switch" :aria-label="t('app.dataSource')">
        <Server :size="15" aria-hidden="true" />
        <button type="button" :class="{ active: dataSource === 'api' }" @click="setSource('api')">
          {{ t("app.api") }}
        </button>
        <button type="button" :class="{ active: dataSource === 'demo' }" @click="setSource('demo')">
          {{ t("app.demo") }}
        </button>
      </div>
      <div class="source-switch" :aria-label="t('app.language')">
        <button type="button" :class="{ active: locale === 'zh' }" @click="setLocale('zh' as Locale)">中文</button>
        <button type="button" :class="{ active: locale === 'en' }" @click="setLocale('en' as Locale)">EN</button>
      </div>
    </div>
  </header>

  <ProjectListPage v-if="route.name === 'projects' || (route.name === 'runs' && !runId)" :data-source="dataSource" @navigate="navigate" />
  <DatasetDetailPage
    v-else-if="route.name === 'datasets' && route.id"
    :dataset-id="route.id"
    :data-source="dataSource"
    @navigate="navigate"
  />
  <ExperimentDetailPage
    v-else-if="route.name === 'experiments' && route.id"
    :experiment-id="route.id"
    :data-source="dataSource"
    @navigate="navigate"
  />
  <ExperimentListPage v-else-if="route.name === 'experiments'" :data-source="dataSource" @navigate="navigate" />
  <RuntimeProfilePage v-else-if="route.name === 'runtime'" :data-source="dataSource" />
  <ComparisonPage v-else-if="route.name === 'comparison'" :data-source="dataSource" @navigate="navigate" />
  <RunConsolePage v-else :run-id="runId" :data-source="dataSource" @navigate="navigate" />
</template>

<style scoped>
.app-nav {
  position: sticky;
  z-index: 20;
  top: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  min-height: 58px;
  padding: 10px max(16px, calc((100vw - 1380px) / 2 + 16px));
  border-bottom: 1px solid var(--border);
  background: rgba(251, 250, 247, 0.88);
  backdrop-filter: blur(10px);
}

.nav-brand {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  color: var(--ink);
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 700;
}

.nav-brand img {
  width: 32px;
  height: 32px;
}

.nav-links {
  display: flex;
  gap: 6px;
  overflow-x: auto;
}

.nav-links a {
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 5px 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  color: var(--muted-strong);
  font-size: 13px;
  white-space: nowrap;
  transition:
    background-color var(--motion-fast) var(--ease-standard),
    border-color var(--motion-fast) var(--ease-standard),
    color var(--motion-fast) var(--ease-standard),
    transform var(--motion-fast) var(--ease-standard);
}

.nav-links a:hover {
  border-color: var(--border);
  background: rgba(255, 255, 255, 0.72);
  color: var(--ink);
  transform: translateY(-1px);
}

.nav-links a.active {
  border-color: var(--border);
  background: var(--panel);
  color: var(--ink);
  font-weight: 700;
}

.nav-controls {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.source-switch {
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--panel);
  color: var(--muted);
}

.source-switch button {
  min-height: 26px;
  padding: 2px 8px;
  border: 0;
  color: var(--muted-strong);
  font-size: 12px;
}

.source-switch button:hover:not(.active) {
  background: var(--panel-soft);
  color: var(--ink);
}

.source-switch button.active {
  background: var(--ink);
  color: #ffffff;
}

@media (max-width: 760px) {
  .app-nav {
    grid-template-columns: 1fr;
    align-items: start;
  }

  .source-switch {
    justify-self: start;
  }

  .nav-controls {
    justify-content: flex-start;
  }
}
</style>
