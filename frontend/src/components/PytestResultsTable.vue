<script setup lang="ts">
import { computed, ref } from "vue";
import { Search } from "@lucide/vue";
import type { PytestCaseResultOut } from "../types/api";
import StatusBadge from "./StatusBadge.vue";

const props = defineProps<{
  results: PytestCaseResultOut[];
}>();

const selectedStatus = ref("all");
const query = ref("");
const expandedId = ref<string | null>(null);

const statuses = ["all", "passed", "failed", "error", "skipped", "unmatched"];

const filteredResults = computed(() => {
  const needle = query.value.trim().toLowerCase();
  return props.results.filter((result) => {
    const statusMatch =
      selectedStatus.value === "all" ||
      result.status === selectedStatus.value ||
      (selectedStatus.value === "unmatched" && result.mapping_status === "unmatched");
    const queryMatch = !needle || result.nodeid.toLowerCase().includes(needle);
    return statusMatch && queryMatch;
  });
});
</script>

<template>
  <section class="pytest-panel" aria-label="Pytest Results">
    <div class="pytest-toolbar">
      <div class="search-box">
        <Search :size="16" aria-hidden="true" />
        <input v-model="query" type="search" placeholder="Search nodeid" />
      </div>
      <div class="segmented" aria-label="Status filter">
        <button
          v-for="status in statuses"
          :key="status"
          type="button"
          :class="{ active: selectedStatus === status }"
          @click="selectedStatus = status"
        >
          {{ status }}
        </button>
      </div>
    </div>

    <div class="table-shell">
      <table>
        <thead>
          <tr>
            <th>nodeid</th>
            <th>mapping</th>
            <th>status</th>
            <th>duration</th>
            <th>failure_type</th>
            <th>message</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="result in filteredResults" :key="result.id">
            <tr :class="{ 'failed-row': result.status === 'failed' || result.status === 'error' }">
              <td class="mono nodeid">
                <button type="button" class="node-button" @click="expandedId = expandedId === result.id ? null : result.id">
                  {{ result.nodeid }}
                </button>
              </td>
              <td><StatusBadge :value="result.mapping_status" /></td>
              <td><StatusBadge :value="result.status" /></td>
              <td class="mono">{{ result.duration_ms }}ms</td>
              <td class="mono">{{ result.failure_type ?? "none" }}</td>
              <td>{{ result.failure_message ?? "OK" }}</td>
            </tr>
            <tr v-if="expandedId === result.id" class="expanded-row">
              <td colspan="6">
                <div class="failure-detail">
                  <p><strong>traceback_hash:</strong> {{ result.traceback_hash ?? "none" }}</p>
                  <pre v-if="result.stdout_excerpt">{{ result.stdout_excerpt }}</pre>
                  <pre v-if="result.stderr_excerpt">{{ result.stderr_excerpt }}</pre>
                  <p v-if="!result.stdout_excerpt && !result.stderr_excerpt">
                    没有 stdout/stderr excerpt。
                  </p>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.pytest-panel {
  display: grid;
  gap: 14px;
}

.pytest-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.search-box {
  min-height: 38px;
  min-width: min(340px, 100%);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.82);
  color: var(--muted);
}

.search-box input {
  width: 100%;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--ink);
}

.segmented {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.segmented button {
  min-height: 32px;
  padding: 4px 9px;
  color: var(--muted-strong);
  font-size: 12px;
}

.segmented button.active {
  border-color: var(--ink);
  background: var(--ink);
  color: #ffffff;
}

.failed-row {
  box-shadow: inset 3px 0 0 var(--failed);
}

.nodeid {
  min-width: 360px;
  max-width: 560px;
}

.node-button {
  display: block;
  width: 100%;
  overflow-wrap: anywhere;
  border: 0;
  background: transparent;
  color: var(--ink);
  text-align: left;
}

.expanded-row td {
  padding: 0;
  background: rgba(251, 250, 247, 0.82);
}

.failure-detail {
  display: grid;
  gap: 8px;
  padding: 12px;
}

.failure-detail strong {
  color: var(--ink);
}
</style>
