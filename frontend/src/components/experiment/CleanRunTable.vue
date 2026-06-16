<script setup lang="ts">
import { ArrowRight } from "@lucide/vue";
import { useI18n } from "../../i18n";
import type { CleanRunContract } from "../../types/api";

defineProps<{
  cleanRuns: CleanRunContract[];
}>();

const emit = defineEmits<{
  openRun: [runId: string];
}>();

const { t } = useI18n();

function contextStatus(clean: CleanRunContract): string {
  return clean.report_quality?.context_completeness?.status ?? t("common.unknown");
}

function contextIncomplete(clean: CleanRunContract): boolean {
  return Boolean(clean.report_quality?.context_completeness?.context_incomplete);
}
</script>

<template>
  <section class="section-stack">
    <div>
      <p class="eyebrow">CLEAN RUNS</p>
      <h2>{{ t("experiments.cleanRunDrilldown") }}</h2>
    </div>
    <div class="table-shell">
      <table>
        <thead>
          <tr>
            <th>{{ t("experiments.strategy") }}</th>
            <th>{{ t("experiments.repeat") }}</th>
            <th>{{ t("experiments.status") }}</th>
            <th>{{ t("experiments.falsePositive") }}</th>
            <th>{{ t("summary.pytest") }}</th>
            <th>{{ t("comparison.tokens") }}</th>
            <th>{{ t("experiments.context") }}</th>
            <th>{{ t("experiments.action") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="clean in cleanRuns" :key="clean.id">
            <td class="mono">{{ clean.strategy_version_id }}</td>
            <td>{{ clean.repeat_index + 1 }}</td>
            <td>
              <span class="status-pill" :data-status="clean.status">{{ t(`status.${clean.status}`) }}</span>
            </td>
            <td>{{ clean.false_positive ? t("common.yes") : t("common.no") }}</td>
            <td>
              {{ clean.clean_metrics.final_passed }}/{{ clean.clean_metrics.final_cases_total }}
              {{ t("summary.passed") }}
            </td>
            <td class="mono">{{ clean.clean_metrics.total_tokens }}</td>
            <td>
              <span :class="contextIncomplete(clean) ? 'evidence-miss' : 'evidence-ok'">
                {{ contextStatus(clean) }}
              </span>
            </td>
            <td>
              <button class="text-button" type="button" @click="emit('openRun', clean.clean_run_id)">
                <ArrowRight :size="15" aria-hidden="true" />
                {{ t("experiments.openRun") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.section-stack {
  display: grid;
  gap: 14px;
  margin-top: 18px;
}

.evidence-ok,
.evidence-miss {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 700;
}

.evidence-ok {
  color: var(--passed);
}

.evidence-miss {
  color: var(--failed);
}

.status-pill {
  display: inline-flex;
  min-height: 24px;
  align-items: center;
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel-soft);
  color: var(--muted-strong);
  font-size: 12px;
  font-weight: 700;
}

.status-pill[data-status="completed"] {
  border-color: rgba(47, 107, 63, 0.24);
  background: var(--passed-bg);
  color: var(--passed);
}

.status-pill[data-status="running"],
.status-pill[data-status="queued"] {
  border-color: rgba(138, 90, 0, 0.2);
  background: var(--running-bg);
  color: var(--running);
}

.status-pill[data-status="failed"],
.status-pill[data-status="cancelled"] {
  border-color: rgba(159, 58, 47, 0.24);
  background: var(--failed-bg);
  color: var(--failed);
}
</style>
