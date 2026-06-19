<script setup lang="ts">
import { computed } from "vue";
import { Ban, FileWarning, ShieldCheck } from "@lucide/vue";
import { useI18n } from "../../i18n";
import type {
  EvaluationEventContract,
  ReflectionEventBackfeedContract,
  ReflectionEventBackfeedDecisionContract,
} from "../../types/api";

const props = defineProps<{
  evaluationEvents: EvaluationEventContract[];
  reflectionEventBackfeed: ReflectionEventBackfeedContract[];
}>();

const { t } = useI18n();

type DecisionRow = ReflectionEventBackfeedDecisionContract & {
  clean_run_id: string;
  repeat_index: number;
  strategy_version_id: string;
};

const eventById = computed(() => new Map(props.evaluationEvents.map((event) => [event.event_id, event])));

const decisionRows = computed<DecisionRow[]>(() =>
  props.reflectionEventBackfeed.flatMap((audit) =>
    audit.decisions.map((decision) => ({
      ...decision,
      clean_run_id: audit.clean_run_id,
      repeat_index: audit.repeat_index,
      strategy_version_id: audit.strategy_version_id,
    }))
  )
);

const latestDecisionByEvent = computed(() => {
  const decisions = new Map<string, DecisionRow>();
  for (const decision of decisionRows.value) {
    decisions.set(decision.event_id, decision);
  }
  return decisions;
});

const includedCount = computed(() => decisionRows.value.filter((decision) => decision.action === "included").length);
const filteredCount = computed(() => decisionRows.value.filter((decision) => decision.action === "filtered").length);
const blockingCount = computed(() => props.evaluationEvents.filter((event) => event.severity === "blocking").length);

function eventClass(event: EvaluationEventContract): string {
  if (event.severity === "blocking") {
    return "blocking";
  }
  if (event.severity === "error") {
    return "error";
  }
  return "info";
}

function decisionLabel(event: EvaluationEventContract): string {
  const decision = latestDecisionByEvent.value.get(event.event_id);
  if (decision?.action === "included") {
    return t("experiments.promptSafe");
  }
  if (decision?.action === "filtered") {
    return t("experiments.auditOnly");
  }
  return t("experiments.eventOnly");
}

function decisionClass(event: EvaluationEventContract): string {
  const decision = latestDecisionByEvent.value.get(event.event_id);
  if (decision?.action === "included") {
    return "prompt-safe";
  }
  if (decision?.action === "filtered") {
    return "audit-only";
  }
  return "event-only";
}

</script>

<template>
  <section class="event-grid">
    <article class="section-stack">
      <div class="event-heading">
        <div>
          <p class="eyebrow">{{ t("experiments.eventTimelineEyebrow") }}</p>
          <h2>{{ t("experiments.eventTimeline") }}</h2>
        </div>
        <div class="event-counters" :aria-label="t('experiments.eventSummaryAria')">
          <span class="counter prompt-safe">
            <ShieldCheck :size="14" aria-hidden="true" />
            {{ includedCount }} {{ t("experiments.promptSafe") }}
          </span>
          <span class="counter audit-only">
            <Ban :size="14" aria-hidden="true" />
            {{ filteredCount }} {{ t("experiments.auditOnly") }}
          </span>
          <span class="counter blocking">
            <FileWarning :size="14" aria-hidden="true" />
            {{ blockingCount }} {{ t("experiments.blockingEvents") }}
          </span>
        </div>
      </div>

      <div v-if="evaluationEvents.length" class="event-list">
        <article v-for="event in evaluationEvents" :key="event.event_id" :class="['event-row', eventClass(event)]">
          <div class="event-rail" aria-hidden="true"></div>
          <div class="event-body">
            <div class="event-title">
              <strong>{{ event.event_type }}</strong>
              <span :class="['decision-chip', decisionClass(event)]">{{ decisionLabel(event) }}</span>
            </div>
            <p>{{ event.reason }}</p>
            <div class="event-meta">
              <span>{{ event.severity }}</span>
              <span>{{ event.scope }}</span>
              <span v-if="event.strategy_version_id">{{ event.strategy_version_id }}</span>
              <span v-if="event.repeat_index !== null">{{ t("experiments.repeatShort") }} {{ event.repeat_index }}</span>
              <span>{{ event.event_id }}</span>
            </div>
          </div>
        </article>
      </div>

      <div v-else class="empty-events subtle-panel">
        <p class="eyebrow">{{ t("experiments.eventTimeline") }}</p>
        <h3>{{ t("experiments.noEvaluationEvents") }}</h3>
        <p>{{ t("experiments.noEvaluationEventsBody") }}</p>
      </div>
    </article>

    <aside class="subtle-panel decision-panel">
      <p class="eyebrow">{{ t("experiments.backfeedAudit") }}</p>
      <h3>{{ t("experiments.promptBoundary") }}</h3>
      <div v-if="decisionRows.length" class="decision-list">
        <article v-for="decision in decisionRows" :key="`${decision.clean_run_id}-${decision.event_id}-${decision.action}`">
          <span :class="['decision-chip', decision.action === 'included' ? 'prompt-safe' : 'audit-only']">
            {{ decision.action === "included" ? t("experiments.promptSafe") : t("experiments.auditOnly") }}
          </span>
          <strong>{{ eventById.get(decision.event_id)?.event_type ?? decision.event_type }}</strong>
          <p>{{ decision.reason }}</p>
          <small>{{ decision.strategy_version_id }} · {{ t("experiments.repeatShort") }} {{ decision.repeat_index }} · {{ decision.event_id }}</small>
        </article>
      </div>
      <p v-else class="decision-empty">{{ t("experiments.noBackfeedDecisions") }}</p>
    </aside>
  </section>
</template>

<style scoped>
.section-stack,
.decision-panel {
  display: grid;
  gap: 14px;
}

.event-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.65fr);
  gap: 18px;
  align-items: start;
  margin-top: 18px;
}

.event-heading {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: end;
}

.event-counters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.counter,
.decision-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 24px;
  padding: 3px 8px;
  border-radius: 999px;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}

.event-list {
  display: grid;
  gap: 10px;
}

.event-row {
  display: grid;
  grid-template-columns: 4px minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.78);
}

.event-rail {
  background: var(--tool);
}

.event-row.blocking .event-rail,
.counter.blocking {
  background: var(--failed-bg);
  color: var(--failed);
}

.event-row.error .event-rail {
  background: var(--failed);
}

.event-row.info .event-rail {
  background: var(--tool);
}

.event-body {
  display: grid;
  gap: 8px;
  padding: 12px;
  min-width: 0;
}

.event-title {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.event-title strong,
.decision-list strong {
  overflow-wrap: anywhere;
  font-family: var(--font-mono);
  font-size: 12px;
}

.event-body p,
.decision-list p,
.decision-empty,
.empty-events p {
  margin: 0;
  color: var(--muted-strong);
  line-height: 1.55;
}

.event-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.event-meta span,
.decision-list small {
  overflow-wrap: anywhere;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
}

.decision-panel,
.empty-events {
  padding: 18px;
}

.decision-list {
  display: grid;
  gap: 10px;
}

.decision-list article {
  display: grid;
  gap: 6px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--panel-soft);
}

.prompt-safe {
  background: var(--tool-bg);
  color: var(--tool);
}

.audit-only,
.event-only {
  background: var(--code);
  color: var(--muted-strong);
}

.empty-events h3,
.decision-panel h3 {
  margin: 0;
}

@media (max-width: 1080px) {
  .event-grid {
    grid-template-columns: 1fr;
  }

  .event-heading {
    display: grid;
    align-items: start;
  }

  .event-counters {
    justify-content: flex-start;
  }
}
</style>
