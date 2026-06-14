<script setup lang="ts">
import { computed } from "vue";
import { CheckCircle2, XCircle } from "@lucide/vue";
import { mockComparison } from "../mock/data";

const bugIds = computed(() => Object.keys(mockComparison.capture_matrix));
const strategyIds = computed(() => mockComparison.rows.map((row) => row.strategy_id));

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}
</script>

<template>
  <main class="comparison-page app-page">
    <section class="comparison-head">
      <p class="eyebrow">TRACE / COMPARISON</p>
      <h1>策略对比是评测证据，不是营销结论</h1>
      <p>
        这里读取 V1 harness 输出形状，展示捕获率、假阳性和逐 bug 捕获矩阵。Mock 数据只能证明 harness 可运行。
      </p>
    </section>

    <section class="table-shell">
      <table>
        <thead>
          <tr>
            <th>strategy</th>
            <th>capture</th>
            <th>false positive</th>
            <th>tokens</th>
            <th>tool calls</th>
            <th>reflection</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in mockComparison.rows" :key="row.strategy_id">
            <td>{{ row.strategy_name }}</td>
            <td>{{ percent(row.capture_rate_mean) }} ({{ row.captured_mean }}/{{ row.total_in_scope }})</td>
            <td>{{ percent(row.false_positive_rate) }}</td>
            <td class="mono">{{ row.avg_tokens }}</td>
            <td class="mono">{{ row.avg_tool_calls }}</td>
            <td>{{ row.reflection_used ? "yes" : "no" }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="matrix-section">
      <div>
        <p class="eyebrow">CAPTURE MATRIX</p>
        <h2>逐 bug 证据矩阵</h2>
      </div>
      <div class="table-shell">
        <table>
          <thead>
            <tr>
              <th>bug variant</th>
              <th v-for="strategyId in strategyIds" :key="strategyId">{{ strategyId }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="bugId in bugIds" :key="bugId">
              <td class="mono">{{ bugId }}</td>
              <td v-for="strategyId in strategyIds" :key="strategyId">
                <span v-if="mockComparison.capture_matrix[bugId][strategyId]" class="matrix-ok">
                  <CheckCircle2 :size="16" aria-hidden="true" />
                  captured
                </span>
                <span v-else class="matrix-miss">
                  <XCircle :size="16" aria-hidden="true" />
                  missed
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
