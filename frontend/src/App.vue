<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { BarChart3, FolderGit2, MonitorDot, Server } from "@lucide/vue";
import ComparisonPage from "./pages/ComparisonPage.vue";
import ProjectListPage from "./pages/ProjectListPage.vue";
import RunConsolePage from "./pages/RunConsolePage.vue";
import { useI18n, type Locale } from "./i18n";
import type { DataSource } from "./types/ui";

const initialSource = (import.meta.env.VITE_TRACE_DATA_SOURCE === "api" ? "api" : "mock") as DataSource;
const dataSource = ref<DataSource>(initialSource);
const sampleRunId = "run-demo-react-001";
const defaultHash = computed(() => (dataSource.value === "api" ? "#/projects" : "#/runs/run-demo-react-001"));
const currentHash = ref(window.location.hash || defaultHash.value);
const { locale, setLocale, t } = useI18n();

const route = computed(() => {
  const hash = currentHash.value.replace(/^#/, "") || defaultHash.value.replace(/^#/, "");
  const parts = hash.split("/").filter(Boolean);
  return {
    name: parts[0] ?? (dataSource.value === "api" ? "projects" : "runs"),
    id: parts[1] ?? (dataSource.value === "api" ? "" : sampleRunId)
  };
});

const runId = computed(() => {
  if (route.value.name === "runs") {
    return route.value.id || (dataSource.value === "api" ? "" : sampleRunId);
  }
  return dataSource.value === "api" ? "" : sampleRunId;
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

function setSource(source: DataSource) {
  dataSource.value = source;
  if (source === "api" && route.value.name === "runs" && runId.value === sampleRunId) {
    navigate("#/projects");
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
    <a class="nav-brand" :href="dataSource === 'api' ? '#/projects' : `#/runs/${sampleRunId}`">
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
      <a href="#/comparison" :class="{ active: route.name === 'comparison' }">
        <BarChart3 :size="16" aria-hidden="true" />
        {{ t("app.comparison") }}
      </a>
    </nav>
    <div class="nav-controls">
      <div class="source-switch" :aria-label="t('app.dataSource')">
        <Server :size="15" aria-hidden="true" />
        <button type="button" :class="{ active: dataSource === 'mock' }" @click="setSource('mock')">
          {{ t("app.mock") }}
        </button>
        <button type="button" :class="{ active: dataSource === 'api' }" @click="setSource('api')">
          {{ t("app.api") }}
        </button>
      </div>
      <div class="source-switch" :aria-label="t('app.language')">
        <button type="button" :class="{ active: locale === 'zh' }" @click="setLocale('zh' as Locale)">中文</button>
        <button type="button" :class="{ active: locale === 'en' }" @click="setLocale('en' as Locale)">EN</button>
      </div>
    </div>
  </header>

  <ProjectListPage v-if="route.name === 'projects' || (route.name === 'runs' && !runId)" :data-source="dataSource" @navigate="navigate" />
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
