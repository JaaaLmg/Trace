<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { ArrowRight, Database, Plus, RefreshCw } from "@lucide/vue";
import { listEvalDatasets } from "../api/evaluation";
import { demoEvalDataset } from "../demo/staticRunFixture";
import { useLatestRequest } from "../composables/useLatestRequest";
import { useI18n } from "../i18n";
import type { EvalDatasetOut } from "../types/api";
import type { DataSource } from "../types/ui";

const props = defineProps<{
  dataSource: DataSource;
}>();

const emit = defineEmits<{
  navigate: [hash: string];
}>();

const { t } = useI18n();

const datasets = ref<EvalDatasetOut[]>([]);
const loading = ref(false);
const errorMessage = ref<string | null>(null);
const datasetRequest = useLatestRequest();

async function loadDatasets() {
  const requestSeq = datasetRequest.next();
  loading.value = true;
  errorMessage.value = null;
  try {
    const next =
      props.dataSource === "demo"
        ? [
            {
              id: demoEvalDataset.id,
              name: demoEvalDataset.name,
              version: demoEvalDataset.version,
              description: demoEvalDataset.description,
              project_snapshot_ids: demoEvalDataset.project_snapshot_ids,
              created_at: demoEvalDataset.created_at
            }
          ]
        : await listEvalDatasets();
    if (!datasetRequest.isCurrent(requestSeq)) {
      return;
    }
    datasets.value = next;
  } catch (error) {
    if (!datasetRequest.isCurrent(requestSeq)) {
      return;
    }
    datasets.value = [];
    errorMessage.value = error instanceof Error ? error.message : t("datasets.loadFailed");
  } finally {
    if (datasetRequest.isCurrent(requestSeq)) {
      loading.value = false;
    }
  }
}

function openDataset(datasetId: string) {
  emit("navigate", `#/datasets/${datasetId}`);
}

onMounted(() => {
  void loadDatasets();
});

watch(
  () => props.dataSource,
  () => {
    void loadDatasets();
  }
);
</script>

<template>
  <main class="page-shell">
    <section class="detail-head">
      <div>
        <p class="eyebrow">{{ t("datasets.listEyebrow") }}</p>
        <h1>{{ t("app.datasets") }}</h1>
      </div>
      <div class="dataset-actions">
        <button v-if="props.dataSource === 'api'" class="text-button" type="button" @click="emit('navigate', '#/datasets/new')">
          <Plus :size="16" aria-hidden="true" />
          {{ t("datasets.create") }}
        </button>
        <button class="text-button" type="button" :disabled="loading" @click="loadDatasets">
          <RefreshCw :size="16" aria-hidden="true" />
          {{ t("projects.refresh") }}
        </button>
      </div>
    </section>

    <p v-if="errorMessage" class="warning-banner">{{ errorMessage }}</p>
    <p v-if="loading" class="mode-note">{{ t("datasets.loading") }}</p>

    <section v-if="datasets.length" class="dataset-list">
      <article v-for="dataset in datasets" :key="dataset.id" class="subtle-panel dataset-card">
        <div class="dataset-icon">
          <Database :size="18" aria-hidden="true" />
        </div>
        <div>
          <p class="eyebrow">{{ dataset.version }}</p>
          <h2>{{ dataset.name }}</h2>
          <p>{{ dataset.description || t("datasets.noDescription") }}</p>
          <small>{{ dataset.id }} · {{ dataset.project_snapshot_ids.length }} {{ t("datasets.snapshots") }}</small>
        </div>
        <button class="icon-button" type="button" :aria-label="dataset.name" @click="openDataset(dataset.id)">
          <ArrowRight :size="18" aria-hidden="true" />
        </button>
      </article>
    </section>

    <section v-else-if="!loading" class="empty-state subtle-panel">
      <strong>{{ t("datasets.emptyTitle") }}</strong>
      <span>{{ t("datasets.emptyBody") }}</span>
      <button v-if="props.dataSource === 'api'" class="text-button" type="button" @click="emit('navigate', '#/datasets/new')">
        <Plus :size="16" aria-hidden="true" />
        {{ t("datasets.create") }}
      </button>
    </section>
  </main>
</template>

<style scoped>
.detail-head,
.dataset-actions,
.dataset-card {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  justify-content: space-between;
}

.detail-head {
  margin-top: 18px;
}

.dataset-actions {
  flex-wrap: wrap;
  justify-content: flex-end;
}

.dataset-list {
  display: grid;
  gap: 12px;
  margin-top: 18px;
}

.dataset-card {
  padding: 16px;
}

.dataset-card > div:nth-child(2) {
  flex: 1;
  min-width: 0;
}

.dataset-card h2 {
  margin: 4px 0 6px;
  font-size: 18px;
}

.dataset-card p {
  color: var(--muted-strong);
}

.dataset-card small {
  display: block;
  margin-top: 8px;
  overflow-wrap: anywhere;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
}

.dataset-icon,
.icon-button {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(251, 250, 247, 0.72);
  color: var(--tool);
}

.icon-button:hover {
  border-color: var(--border-strong);
  background: var(--panel);
}

.empty-state {
  display: grid;
  gap: 10px;
  margin-top: 18px;
  padding: 18px;
  justify-items: start;
}
</style>
