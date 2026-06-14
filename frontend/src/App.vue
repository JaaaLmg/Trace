<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { BarChart3, FolderGit2, MonitorDot, Server } from "@lucide/vue";
import ComparisonPage from "./pages/ComparisonPage.vue";
import ProjectListPage from "./pages/ProjectListPage.vue";
import RunConsolePage from "./pages/RunConsolePage.vue";
import type { DataSource } from "./types/ui";

const initialSource = (import.meta.env.VITE_TRACE_DATA_SOURCE === "api" ? "api" : "mock") as DataSource;
const dataSource = ref<DataSource>(initialSource);
const currentHash = ref(window.location.hash || "#/runs/run-demo-react-001");

const route = computed(() => {
  const hash = currentHash.value.replace(/^#/, "") || "/runs/run-demo-react-001";
  const parts = hash.split("/").filter(Boolean);
  return {
    name: parts[0] ?? "runs",
    id: parts[1] ?? "run-demo-react-001"
  };
});

const runId = computed(() => {
  if (route.value.name === "runs") {
    return route.value.id || "run-demo-react-001";
  }
  return "run-demo-react-001";
});

function syncHash() {
  currentHash.value = window.location.hash || "#/runs/run-demo-react-001";
}

function navigate(hash: string) {
  window.location.hash = hash;
  syncHash();
}

function setSource(source: DataSource) {
  dataSource.value = source;
}

onMounted(() => {
  if (!window.location.hash) {
    window.location.hash = currentHash.value;
  }
  window.addEventListener("hashchange", syncHash);
});

onBeforeUnmount(() => {
  window.removeEventListener("hashchange", syncHash);
});
</script>

<template>
  <header class="app-nav">
    <a class="nav-brand" href="#/runs/run-demo-react-001">
      <img src="/trace-logo-icon.svg" alt="" />
      <span>TRACE</span>
    </a>
    <nav class="nav-links" aria-label="Primary navigation">
      <a href="#/projects" :class="{ active: route.name === 'projects' }">
        <FolderGit2 :size="16" aria-hidden="true" />
        Projects
      </a>
      <a href="#/runs/run-demo-react-001" :class="{ active: route.name === 'runs' }">
        <MonitorDot :size="16" aria-hidden="true" />
        Run Console
      </a>
      <a href="#/comparison" :class="{ active: route.name === 'comparison' }">
        <BarChart3 :size="16" aria-hidden="true" />
        Comparison
      </a>
    </nav>
    <div class="source-switch" aria-label="Data source">
      <Server :size="15" aria-hidden="true" />
      <button type="button" :class="{ active: dataSource === 'mock' }" @click="setSource('mock')">Mock</button>
      <button type="button" :class="{ active: dataSource === 'api' }" @click="setSource('api')">API</button>
    </div>
  </header>

  <ProjectListPage v-if="route.name === 'projects'" :data-source="dataSource" @navigate="navigate" />
  <ComparisonPage v-else-if="route.name === 'comparison'" />
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
}

.nav-links a.active {
  border-color: var(--border);
  background: var(--panel);
  color: var(--ink);
  font-weight: 700;
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
}
</style>
