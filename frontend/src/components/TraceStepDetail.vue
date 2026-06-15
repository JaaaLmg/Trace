<script setup lang="ts">
import { computed } from "vue";
import { X } from "@lucide/vue";
import { useI18n } from "../i18n";
import type { TraceStepOut } from "../types/api";
import JsonViewer from "./JsonViewer.vue";
import StatusBadge from "./StatusBadge.vue";

const props = defineProps<{
  step: TraceStepOut | null;
  open: boolean;
}>();

const emit = defineEmits<{
  close: [];
}>();

const { t } = useI18n();
const payload = computed(() => props.step?.payload ?? null);
</script>

<template>
  <aside class="detail-drawer" :class="{ open }" aria-label="Step Detail Drawer">
    <div v-if="step" class="drawer-content">
      <div class="drawer-header">
        <div class="drawer-title">
          <p class="eyebrow">{{ t("detail.title") }}</p>
          <h3>{{ step.name }}</h3>
          <p class="mono">{{ t("detail.attempt") }}: {{ step.attempt_id ?? t("common.none") }}</p>
        </div>
        <StatusBadge :value="step.status" />
        <button class="drawer-close" type="button" :aria-label="t('detail.close')" @click="emit('close')">
          <X :size="17" aria-hidden="true" />
        </button>
      </div>

      <div class="detail-grid">
        <div>
          <p class="detail-label">{{ t("detail.input") }}</p>
          <p>{{ step.input_summary || t("detail.noInput") }}</p>
        </div>
        <div>
          <p class="detail-label">{{ t("detail.output") }}</p>
          <p>{{ step.output_summary || t("detail.noOutput") }}</p>
        </div>
      </div>

      <JsonViewer :value="payload" />

      <pre v-if="step.error" class="traceback">{{ step.error }}</pre>
    </div>
    <div v-else class="empty-detail">
      <p class="eyebrow">{{ t("detail.title") }}</p>
      <h3>{{ t("detail.select") }}</h3>
      <p>{{ t("detail.selectBody") }}</p>
    </div>
  </aside>
</template>

<style scoped>
.detail-drawer {
  position: relative;
  z-index: 3;
  min-width: 0;
  padding: 18px;
  border-left: 1px solid var(--border);
  background: rgba(255, 252, 247, 0.96);
  box-shadow: var(--drawer-shadow);
  transform: translateX(0);
  transition:
    transform 180ms ease,
    opacity 140ms ease;
}

.detail-drawer:not(.open) {
  opacity: 0;
  transform: translateX(32px);
  pointer-events: none;
}

.drawer-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.drawer-title {
  min-width: 0;
}

.drawer-title h3 {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawer-title p:last-child {
  margin-top: 5px;
  overflow: hidden;
  color: var(--muted);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawer-close {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  color: var(--muted-strong);
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.detail-grid > div {
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.68);
}

.detail-label {
  margin-bottom: 5px;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
}

.traceback {
  max-height: 154px;
  margin-top: 14px;
  border-color: rgba(159, 58, 47, 0.2);
  background: rgba(159, 58, 47, 0.08);
  color: #693129;
  white-space: pre;
}

.empty-detail {
  display: grid;
  min-height: 360px;
  align-content: center;
  gap: 8px;
}

@media (max-width: 760px) {
  .detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
