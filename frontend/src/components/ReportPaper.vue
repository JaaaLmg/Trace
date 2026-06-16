<script setup lang="ts">
import { computed } from "vue";
import { ExternalLink } from "@lucide/vue";
import { useI18n } from "../i18n";
import type { ReportQualityEvidence, TestReportOut } from "../types/api";

const props = defineProps<{
  report: TestReportOut | null;
}>();

const { t } = useI18n();

const metricLabelKeys: Record<string, string> = {
  final_passed: "summary.passed",
  final_failed: "summary.failed",
  final_skipped: "summary.skipped",
  attempts: "report.attempts",
  tool_call_count: "summary.toolCalls",
  total_tokens: "comparison.tokens",
  duration_ms: "pytest.duration",
  reflection_used: "comparison.reflection"
};

// Only scalar metrics belong in the flat grid; report_quality is a nested
// object rendered separately, so skip non-primitives to avoid [object Object].
const metrics = computed(() => {
  if (!props.report) {
    return [];
  }
  return Object.entries(props.report.metrics)
    .filter(([, value]) => value === null || typeof value !== "object")
    .map(([key, value]) => ({
      key,
      label: metricLabelKeys[key] ? t(metricLabelKeys[key]) : key,
      value
    }));
});

const quality = computed<ReportQualityEvidence | null>(() => {
  const raw = props.report?.metrics.report_quality;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return null;
  }
  return raw as unknown as ReportQualityEvidence;
});

function contractText(): string {
  const evidence = quality.value?.reflection_evidence;
  if (!evidence || !evidence.contract_checked) {
    return t("report.quality.notChecked");
  }
  return evidence.contract_passed ? t("report.quality.passed") : t("report.quality.notPassed");
}
</script>

<template>
  <section class="report-surface" aria-label="Report Paper">
    <article class="report-paper">
      <template v-if="report">
        <h3>{{ t("report.title") }}</h3>
        <p>{{ report.summary }}</p>

        <h3>{{ t("report.riskNotes") }}</h3>
        <p>{{ report.risk_notes || t("report.noRisk") }}</p>

        <h3>{{ t("report.quality.title") }}</h3>
        <template v-if="quality">
          <div class="quality-block">
            <p class="quality-label">{{ t("report.quality.inventory") }}</p>
            <table v-if="quality.test_inventory.length" class="quality-table">
              <thead>
                <tr>
                  <th>{{ t("report.quality.test") }}</th>
                  <th>{{ t("report.quality.location") }}</th>
                  <th>nodeid</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in quality.test_inventory" :key="item.nodeid ?? item.test_name">
                  <td class="mono">{{ item.test_name }}</td>
                  <td class="mono">{{ item.source_path }}:{{ item.start_line }}-{{ item.end_line }}</td>
                  <td class="mono">{{ item.nodeid ?? t("common.none") }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="quality-empty">{{ t("common.none") }}</p>
          </div>

          <div class="quality-block">
            <p class="quality-label">{{ t("report.quality.targets") }}</p>
            <table v-if="quality.target_mappings.length" class="quality-table">
              <thead>
                <tr>
                  <th>{{ t("report.quality.target") }}</th>
                  <th>{{ t("report.quality.location") }}</th>
                  <th>{{ t("report.quality.mapping") }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(item, index) in quality.target_mappings" :key="`${item.target_ref}-${index}`">
                  <td class="mono">{{ item.target_ref }} <small>({{ item.target_type }})</small></td>
                  <td class="mono">{{ item.source_path ?? t("common.none") }}<template v-if="item.symbol"> · {{ item.symbol }}</template></td>
                  <td>
                    <span :class="item.mapping_status === 'unmapped' ? 'tag-miss' : 'tag-ok'">{{ item.mapping_status }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
            <p v-else class="quality-empty">{{ t("common.none") }}</p>
          </div>

          <div class="quality-block">
            <p class="quality-label">{{ t("report.quality.assertions") }}</p>
            <ul v-if="quality.assertion_summaries.length" class="quality-list">
              <li v-for="(item, index) in quality.assertion_summaries" :key="`${item.test_name}-${index}`">
                <strong class="mono">{{ item.test_name }}</strong>
                <span>{{ item.assertion_summary }}</span>
                <small v-if="item.target_ref" class="mono">→ {{ item.target_ref }}</small>
              </li>
            </ul>
            <p v-else class="quality-empty">{{ t("common.none") }}</p>
          </div>

          <div class="quality-block">
            <p class="quality-label">{{ t("report.quality.failures") }}</p>
            <table v-if="quality.failure_classifications.length" class="quality-table">
              <thead>
                <tr>
                  <th>nodeid</th>
                  <th>{{ t("report.quality.classification") }}</th>
                  <th>{{ t("report.quality.message") }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(item, index) in quality.failure_classifications" :key="`${item.nodeid}-${index}`">
                  <td class="mono">{{ item.nodeid }}</td>
                  <td>
                    <span :class="item.classification === 'assertion' ? 'tag-ok' : 'tag-miss'">{{ item.classification }}</span>
                  </td>
                  <td>{{ item.message ?? t("common.none") }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="quality-empty">{{ t("common.none") }}</p>
          </div>

          <div class="quality-block">
            <p class="quality-label">{{ t("report.quality.reflection") }}</p>
            <dl class="quality-dl">
              <div>
                <dt>{{ t("report.quality.used") }}</dt>
                <dd>{{ quality.reflection_evidence.used ? t("common.yes") : t("common.no") }}</dd>
              </div>
              <div>
                <dt>{{ t("report.quality.contract") }}</dt>
                <dd>{{ contractText() }}</dd>
              </div>
              <div v-if="quality.reflection_evidence.violation_reasons.length">
                <dt>{{ t("report.quality.violations") }}</dt>
                <dd>{{ quality.reflection_evidence.violation_reasons.join(", ") }}</dd>
              </div>
              <div v-if="quality.reflection_evidence.accepted_attempt_id">
                <dt>{{ t("report.quality.accepted") }}</dt>
                <dd class="mono">{{ quality.reflection_evidence.accepted_attempt_id }}</dd>
              </div>
              <div v-if="quality.reflection_evidence.rejected_attempt_ids.length">
                <dt>{{ t("report.quality.rejected") }}</dt>
                <dd class="mono">{{ quality.reflection_evidence.rejected_attempt_ids.join(", ") }}</dd>
              </div>
            </dl>
          </div>

          <div class="quality-block">
            <p class="quality-label">{{ t("report.quality.context") }}</p>
            <dl class="quality-dl">
              <div>
                <dt>{{ t("experiments.context") }}</dt>
                <dd>
                  <span :class="quality.context_completeness.context_incomplete ? 'tag-miss' : 'tag-ok'">
                    {{ quality.context_completeness.status }}
                  </span>
                </dd>
              </div>
              <div>
                <dt>{{ t("report.quality.snippets") }}</dt>
                <dd>{{ quality.context_completeness.snippets.length }}</dd>
              </div>
              <div v-if="quality.context_completeness.missing_targets.length">
                <dt>{{ t("report.quality.missingTargets") }}</dt>
                <dd class="mono">{{ quality.context_completeness.missing_targets.join(", ") }}</dd>
              </div>
              <div v-if="quality.context_completeness.risk_notes.length">
                <dt>{{ t("report.quality.riskNotes") }}</dt>
                <dd>{{ quality.context_completeness.risk_notes.join(" · ") }}</dd>
              </div>
            </dl>
          </div>
        </template>
        <p v-else>{{ t("report.quality.empty") }}</p>

        <h3>{{ t("report.artifacts") }}</h3>
        <p v-if="report.markdown_uri">
          Markdown:
          <code>{{ report.markdown_uri }}</code>
        </p>
        <p v-if="report.json_uri">
          JSON:
          <code>{{ report.json_uri }}</code>
        </p>

      </template>
      <template v-else>
        <h3>{{ t("report.notReady") }}</h3>
        <p>{{ t("report.notReadyBody") }}</p>
      </template>
    </article>

    <aside class="metrics-panel" aria-label="Report metrics">
      <div class="metrics-section">
        <p class="summary-label">{{ t("report.metrics") }}</p>
        <div class="metric-pair">
          <div v-for="metric in metrics" :key="metric.key" class="metric-card">
            <strong class="tabular">{{ metric.value }}</strong>
            <span>{{ metric.label }}</span>
          </div>
        </div>
      </div>
      <div class="metrics-section">
        <p class="summary-label">{{ t("report.scope") }}</p>
        <p class="review-note">
          {{ t("report.scopeBody") }}
        </p>
      </div>
      <a v-if="report?.markdown_uri" class="artifact-link" :href="report.markdown_uri" target="_blank" rel="noreferrer">
        <ExternalLink :size="15" aria-hidden="true" />
        {{ t("report.openMarkdown") }}
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

.quality-block {
  margin-top: 16px;
}

.quality-label {
  margin-bottom: 6px;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
}

.quality-empty {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 12px;
}

.quality-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.quality-table th,
.quality-table td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
}

.quality-table th {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
}

.quality-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.quality-list li {
  display: grid;
  gap: 2px;
  font-size: 13px;
}

.quality-dl {
  display: grid;
  gap: 8px;
  margin: 0;
}

.quality-dl > div {
  display: grid;
  grid-template-columns: minmax(120px, 0.32fr) minmax(0, 1fr);
  gap: 12px;
}

.quality-dl dt {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
}

.quality-dl dd {
  margin: 0;
  color: var(--muted-strong);
  overflow-wrap: anywhere;
}

.mono {
  font-family: var(--font-mono);
}

.tag-ok,
.tag-miss {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
}

.tag-ok {
  color: var(--passed);
}

.tag-miss {
  color: var(--failed);
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
