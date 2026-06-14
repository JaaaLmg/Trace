<script setup lang="ts">
import { computed } from "vue";
import { ExternalLink } from "@lucide/vue";
import type { TestReportOut } from "../types/api";

const props = defineProps<{
  report: TestReportOut | null;
}>();

const metricLabels: Record<string, string> = {
  final_passed: "通过用例",
  final_failed: "失败用例",
  final_skipped: "跳过用例",
  attempts: "尝试轮次",
  tool_call_count: "工具调用",
  total_tokens: "Tokens",
  duration_ms: "耗时 ms",
  reflection_used: "已反思"
};

const metrics = computed(() => {
  if (!props.report) {
    return [];
  }
  return Object.entries(props.report.metrics).map(([key, value]) => ({
    key,
    label: metricLabels[key] ?? key,
    value
  }));
});
</script>

<template>
  <section class="report-surface" aria-label="Report Paper">
    <article class="report-paper">
      <template v-if="report">
        <h3>TRACE Run Report</h3>
        <p>{{ report.summary }}</p>

        <blockquote>
          pytest failure is not equal to run failure. The run can complete while preserving failed case evidence.
        </blockquote>

        <h3>Risk Notes</h3>
        <p>{{ report.risk_notes || "No risk notes recorded." }}</p>

        <h3>Artifacts</h3>
        <p v-if="report.markdown_uri">
          Markdown:
          <code>{{ report.markdown_uri }}</code>
        </p>
        <p v-if="report.json_uri">
          JSON:
          <code>{{ report.json_uri }}</code>
        </p>

        <h3>Generated Test Snippet</h3>
        <pre><code>def test_checkout_applies_coupon_and_tax(client):
    response = client.post("/checkout", json={"coupon": "VIP20", "subtotal": 120})
    assert response.status_code == 200
    assert response.json()["total"] == 116.87</code></pre>
      </template>
      <template v-else>
        <h3>报告尚未生成</h3>
        <p>Run 可能还在 queued/running，或执行失败发生在 summarizing 之前。</p>
      </template>
    </article>

    <aside class="metrics-panel" aria-label="Report metrics">
      <div class="metrics-section">
        <p class="summary-label">报告指标</p>
        <div class="metric-pair">
          <div v-for="metric in metrics" :key="metric.key" class="metric-card">
            <strong class="tabular">{{ metric.value }}</strong>
            <span>{{ metric.label }}</span>
          </div>
        </div>
      </div>
      <div class="metrics-section">
        <p class="summary-label">口径</p>
        <p class="review-note">
          当前 token 可能来自 MockLLM 估算；这里展示工作量，不展示真实模型成本结论。
        </p>
      </div>
      <a v-if="report?.markdown_uri" class="artifact-link" :href="report.markdown_uri" target="_blank" rel="noreferrer">
        <ExternalLink :size="15" aria-hidden="true" />
        打开 Markdown 产物
      </a>
    </aside>
  </section>
</template>

<style scoped>
.report-surface {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 360px);
  gap: 24px;
  align-items: start;
}

.report-paper {
  padding: 30px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: rgba(255, 255, 255, 0.82);
  box-shadow: var(--shadow);
}

.report-paper h3 {
  margin-top: 20px;
}

.report-paper h3:first-child {
  margin-top: 0;
}

.report-paper p,
.report-paper li {
  color: var(--muted-strong);
  font-family: var(--font-serif);
  line-height: 1.72;
}

.report-paper blockquote {
  margin: 20px 0;
  padding: 2px 0 2px 18px;
  border-left: 3px solid var(--border-strong);
  color: var(--muted-strong);
  font-family: var(--font-serif);
  font-size: 18px;
  line-height: 1.7;
}

.metrics-panel {
  display: grid;
  gap: 14px;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: rgba(255, 255, 255, 0.78);
  box-shadow: var(--shadow);
}

.metrics-section {
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
}

.metrics-section:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.summary-label {
  margin-bottom: 9px;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
}

.metric-pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.metric-card {
  min-height: 74px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(251, 250, 247, 0.76);
}

.metric-card strong {
  display: block;
  color: var(--ink);
  font-family: var(--font-serif);
  font-size: 23px;
  line-height: 1.1;
  overflow-wrap: anywhere;
}

.metric-card span,
.review-note {
  color: var(--muted);
  font-size: 12px;
}

.artifact-link {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--muted-strong);
  font-weight: 700;
}

@media (max-width: 980px) {
  .report-surface {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 560px) {
  .report-paper {
    padding: 20px;
  }

  .metric-pair {
    grid-template-columns: 1fr;
  }
}
</style>
