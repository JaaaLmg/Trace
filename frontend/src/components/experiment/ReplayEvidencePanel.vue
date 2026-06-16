<script setup lang="ts">
import { computed } from "vue";
import { CheckCircle2, TestTube2, XCircle } from "@lucide/vue";
import { useI18n } from "../../i18n";
import type { ExperimentReplayRunContract, TestReplayContract } from "../../types/api";

const props = defineProps<{
  replayRuns: TestReplayContract[];
  replayResults: ExperimentReplayRunContract[];
  selectedReplayId: string | null;
}>();

const emit = defineEmits<{
  select: [replayId: string];
}>();

const { t } = useI18n();

// A clean replay has no bug_variant_id and never has an experiment_replay_runs
// result — it validates the frozen test set on clean code (false-positive check),
// so it must not be scored as captured/missed.
function isCleanReplay(replay: TestReplayContract): boolean {
  return replay.bug_variant_id === null;
}

function cleanValidationOk(replay: TestReplayContract): boolean {
  const summary = replay.pytest_summary;
  return summary.failed === 0 && summary.collection_errors === 0;
}

const selectedReplay = computed(() => {
  const id = props.selectedReplayId;
  if (!id) {
    return null;
  }
  const replay = props.replayRuns.find((item) => item.id === id) ?? null;
  if (!replay) {
    return null;
  }
  // result is null for clean replays; the detail panel handles both cases.
  const result = props.replayResults.find((item) => item.replay_id === id) ?? null;
  return { replay, result };
});

function replayResult(replayId: string): ExperimentReplayRunContract | null {
  return props.replayResults.find((item) => item.replay_id === replayId) ?? null;
}

function replaySummary(replay: TestReplayContract): string {
  const summary = replay.pytest_summary;
  return `${summary.passed}/${summary.collected} ${t("summary.passed")} · ${summary.failed} ${t("summary.failed")}`;
}
</script>

<template>
  <section class="replay-grid">
    <article class="section-stack">
      <div>
        <p class="eyebrow">REPLAYS</p>
        <h2>{{ t("experiments.replayDetail") }}</h2>
      </div>
      <div class="table-shell">
        <table>
          <thead>
            <tr>
              <th>{{ t("comparison.bugVariant") }}</th>
              <th>{{ t("experiments.status") }}</th>
              <th>{{ t("summary.pytest") }}</th>
              <th>{{ t("experiments.llmCalls") }}</th>
              <th>{{ t("experiments.result") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="replay in replayRuns" :key="replay.id" :class="{ selected: replay.id === selectedReplayId }">
              <td>
                <button class="link-button" type="button" @click="emit('select', replay.id)">
                  <TestTube2 :size="15" aria-hidden="true" />
                  <span>
                    <strong>{{ replay.bug_variant_id ?? t("experiments.cleanReplay") }}</strong>
                    <small>{{ replay.id }}</small>
                  </span>
                </button>
              </td>
              <td>{{ t(`status.${replay.status}`) }}</td>
              <td>{{ replaySummary(replay) }}</td>
              <td class="mono">{{ replay.llm_calls }}</td>
              <td>
                <template v-if="isCleanReplay(replay)">
                  <span :class="cleanValidationOk(replay) ? 'evidence-ok' : 'evidence-miss'">
                    <CheckCircle2 v-if="cleanValidationOk(replay)" :size="16" aria-hidden="true" />
                    <XCircle v-else :size="16" aria-hidden="true" />
                    {{ cleanValidationOk(replay) ? t("experiments.validationPassed") : t("experiments.falsePositive") }}
                  </span>
                </template>
                <template v-else>
                  <span v-if="replayResult(replay.id)?.captured_bug" class="evidence-ok">
                    <CheckCircle2 :size="16" aria-hidden="true" />
                    {{ t("comparison.captured") }}
                  </span>
                  <span v-else class="evidence-miss">
                    <XCircle :size="16" aria-hidden="true" />
                    {{ t("comparison.missed") }}
                  </span>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>

    <aside class="subtle-panel replay-detail-panel">
      <template v-if="selectedReplay">
        <p class="eyebrow">{{ t("experiments.selectedReplay") }}</p>
        <h3>{{ selectedReplay.replay.bug_variant_id ?? t("experiments.cleanReplay") }}</h3>
        <dl>
          <template v-if="isCleanReplay(selectedReplay.replay)">
            <div>
              <dt>{{ t("experiments.cleanValidation") }}</dt>
              <dd>
                <span :class="cleanValidationOk(selectedReplay.replay) ? 'evidence-ok' : 'evidence-miss'">
                  {{ cleanValidationOk(selectedReplay.replay) ? t("experiments.validationPassed") : t("experiments.falsePositive") }}
                </span>
              </dd>
            </div>
            <div>
              <dt>{{ t("summary.pytest") }}</dt>
              <dd>{{ replaySummary(selectedReplay.replay) }}</dd>
            </div>
          </template>
          <template v-else-if="selectedReplay.result">
            <div>
              <dt>{{ t("experiments.captureRule") }}</dt>
              <dd>{{ selectedReplay.result.replay_metrics.capture_rule }}</dd>
            </div>
            <div>
              <dt>{{ t("experiments.capturingNodeids") }}</dt>
              <dd>
                <code v-for="nodeid in selectedReplay.result.replay_metrics.capturing_nodeids" :key="nodeid">{{ nodeid }}</code>
                <span v-if="selectedReplay.result.replay_metrics.capturing_nodeids.length === 0">{{ t("common.none") }}</span>
              </dd>
            </div>
          </template>
          <div>
            <dt>{{ t("experiments.error") }}</dt>
            <dd>{{ selectedReplay.replay.error_message ?? t("common.none") }}</dd>
          </div>
        </dl>
      </template>
      <template v-else>
        <p class="eyebrow">{{ t("experiments.selectedReplay") }}</p>
        <h3>{{ t("experiments.noReplaySelected") }}</h3>
        <p>{{ t("experiments.noReplaySelectedBody") }}</p>
      </template>
    </aside>
  </section>
</template>

<style scoped>
.section-stack,
.replay-detail-panel {
  display: grid;
  gap: 14px;
}

.replay-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.65fr);
  gap: 18px;
  align-items: start;
  margin-top: 18px;
}

.replay-detail-panel {
  padding: 18px;
}

.replay-detail-panel dl {
  display: grid;
  gap: 12px;
  margin: 0;
}

.replay-detail-panel dt {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
}

.replay-detail-panel dd {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  color: var(--muted-strong);
  overflow-wrap: anywhere;
}

.link-button {
  display: inline-flex;
  align-items: flex-start;
  gap: 8px;
  padding: 0;
  border: 0;
  background: transparent;
  text-align: left;
}

.link-button span {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.link-button small {
  overflow-wrap: anywhere;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
}

.link-button:hover {
  background: transparent;
  color: var(--ink);
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

tr.selected td {
  background: rgba(49, 95, 125, 0.07);
}

@media (max-width: 1080px) {
  .replay-grid {
    grid-template-columns: 1fr;
  }
}
</style>
