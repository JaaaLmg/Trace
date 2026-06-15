<script setup lang="ts">
import type { TopicTab } from "../types/ui";

defineProps<{
  tabs: TopicTab[];
  active: string;
}>();

const emit = defineEmits<{
  select: [key: string];
}>();
</script>

<template>
  <nav class="topic-tabs" aria-label="Run sections">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      class="topic-tab"
      :class="{ active: tab.key === active }"
      type="button"
      @click="emit('select', tab.key)"
    >
      <span>{{ tab.label }}</span>
      <span v-if="typeof tab.count === 'number'" class="tab-count">{{ tab.count }}</span>
    </button>
  </nav>
</template>

<style scoped>
.topic-tabs {
  display: flex;
  align-items: end;
  gap: 6px;
  overflow-x: auto;
  border-bottom: 1px solid var(--border-strong);
}

.topic-tab {
  min-height: 40px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border: 1px solid var(--border);
  border-bottom: 0;
  border-radius: 8px 8px 0 0;
  background: rgba(251, 250, 247, 0.72);
  color: var(--muted-strong);
  white-space: nowrap;
  transition:
    background-color var(--motion-fast) var(--ease-standard),
    border-color var(--motion-fast) var(--ease-standard),
    color var(--motion-fast) var(--ease-standard),
    transform var(--motion-fast) var(--ease-standard);
}

.topic-tab:hover:not(.active) {
  border-color: var(--border-strong);
  background: rgba(255, 255, 255, 0.78);
  color: var(--ink);
  transform: translateY(-1px);
}

.topic-tab.active {
  background: var(--panel);
  color: var(--ink);
  font-weight: 700;
}

.topic-tab.active::before {
  content: "";
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--running);
}

.tab-count {
  min-width: 20px;
  padding: 1px 6px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel);
  font-family: var(--font-mono);
  font-size: 11px;
  font-feature-settings: "tnum" 1;
}
</style>
