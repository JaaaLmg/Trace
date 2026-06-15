<script setup lang="ts">
import { computed } from "vue";
import { CheckCircle2, XCircle } from "@lucide/vue";
import { useI18n } from "../i18n";
import { demoComparison } from "../demo/staticRunFixture";

const bugIds = computed(() => Object.keys(demoComparison.capture_matrix));
const strategyIds = computed(() => demoComparison.rows.map((row) => row.strategy_id));
const { t } = useI18n();

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}
</script>

<template>
  <main class="comparison-page app-page">
    <section class="comparison-head">
      <p class="eyebrow">TRACE / COMPARISON</p>
      <h1>{{ t("comparison.title") }}</h1>
      <p>{{ t("comparison.subtitle") }}</p>
    </section>

    <section class="table-shell">
      <table>
        <thead>
          <tr>
            <th>{{ t("comparison.strategy") }}</th>
            <th>{{ t("comparison.capture") }}</th>
            <th>{{ t("comparison.falsePositive") }}</th>
            <th>{{ t("comparison.tokens") }}</th>
            <th>{{ t("comparison.toolCalls") }}</th>
            <th>{{ t("comparison.reflection") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in demoComparison.rows" :key="row.strategy_id">
            <td>{{ row.strategy_name }}</td>
            <td>{{ percent(row.capture_rate_mean) }} ({{ row.captured_mean }}/{{ row.total_in_scope }})</td>
            <td>{{ percent(row.false_positive_rate) }}</td>
            <td class="mono">{{ row.avg_tokens }}</td>
            <td class="mono">{{ row.avg_tool_calls }}</td>
            <td>{{ row.reflection_used ? t("common.yes") : t("common.no") }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="matrix-section">
      <div>
        <p class="eyebrow">CAPTURE MATRIX</p>
        <h2>{{ t("comparison.matrix") }}</h2>
      </div>
      <div class="table-shell">
        <table>
          <thead>
            <tr>
              <th>{{ t("comparison.bugVariant") }}</th>
              <th v-for="strategyId in strategyIds" :key="strategyId">{{ strategyId }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="bugId in bugIds" :key="bugId">
              <td class="mono">{{ bugId }}</td>
              <td v-for="strategyId in strategyIds" :key="strategyId">
                <span v-if="demoComparison.capture_matrix[bugId][strategyId]" class="matrix-ok">
                  <CheckCircle2 :size="16" aria-hidden="true" />
                  {{ t("comparison.captured") }}
                </span>
                <span v-else class="matrix-miss">
                  <XCircle :size="16" aria-hidden="true" />
                  {{ t("comparison.missed") }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </main>
</template>

<style scoped>
.comparison-head {
  padding: 18px 0 24px;
  border-bottom: 1px solid var(--border);
}

.comparison-head h1 {
  margin: 8px 0 10px;
}

.comparison-head p {
  max-width: 760px;
  font-family: var(--font-serif);
}

.comparison-page > .table-shell {
  margin-top: 22px;
}

.matrix-section {
  display: grid;
  gap: 16px;
  margin-top: 28px;
}

.matrix-ok,
.matrix-miss {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 700;
}

.matrix-ok {
  color: var(--passed);
}

.matrix-miss {
  color: var(--failed);
}
</style>
