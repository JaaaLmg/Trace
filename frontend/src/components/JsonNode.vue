<script setup lang="ts">
import { computed, ref } from "vue";
import { Copy } from "@lucide/vue";
import type { JsonValue } from "../types/api";

defineOptions({ name: "JsonNode" });

const props = withDefaults(
  defineProps<{
    value: JsonValue;
    label?: string;
    depth?: number;
    maxDepth?: number;
    maxArrayItems?: number;
    expandAll?: boolean;
  }>(),
  {
    label: "",
    depth: 0,
    maxDepth: 10,
    maxArrayItems: 50,
    expandAll: false
  }
);

const copied = ref(false);
const collapsed = ref(props.depth >= 1 && !props.expandAll);

const isBranch = computed(() => props.value !== null && typeof props.value === "object");
const isArray = computed(() => Array.isArray(props.value));

const fullEntries = computed<[string, JsonValue][]>(() => {
  if (!isBranch.value) {
    return [];
  }
  if (Array.isArray(props.value)) {
    return props.value.map((item, index) => [String(index), item]);
  }
  return Object.entries(props.value as Record<string, JsonValue>);
});

const visibleEntries = computed(() => {
  if (isArray.value) {
    return fullEntries.value.slice(0, props.maxArrayItems);
  }
  return fullEntries.value;
});

const hiddenArrayItems = computed(() => {
  if (!isArray.value) {
    return 0;
  }
  return Math.max(0, fullEntries.value.length - visibleEntries.value.length);
});

const primitiveClass = computed(() => {
  if (props.value === null) {
    return "null";
  }
  return typeof props.value;
});

function preview(): string {
  if (Array.isArray(props.value)) {
    return `Array(${props.value.length})`;
  }
  if (props.value !== null && typeof props.value === "object") {
    return `Object(${Object.keys(props.value).length})`;
  }
  return JSON.stringify(props.value);
}

async function copyValue() {
  const text = JSON.stringify(props.value, null, 2);
  if (navigator.clipboard) {
    await navigator.clipboard.writeText(text);
  } else {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
  copied.value = true;
  window.setTimeout(() => {
    copied.value = false;
  }, 900);
}
</script>

<template>
  <div class="json-node" :class="{ collapsed }" :style="{ '--depth': props.depth }">
    <div class="json-row">
      <button
        v-if="isBranch"
        class="json-toggle"
        type="button"
        :aria-label="collapsed ? '展开 JSON 节点' : '折叠 JSON 节点'"
        @click="collapsed = !collapsed"
      >
        {{ collapsed ? "+" : "-" }}
      </button>
      <span v-else class="json-toggle" aria-hidden="true"></span>

      <span v-if="props.label" class="json-key">"{{ props.label }}":</span>

      <template v-if="isBranch">
        <span class="json-preview">{{ isArray ? "[" : "{" }}</span>
        <span class="json-count">{{ preview() }}</span>
      </template>
      <span v-else class="json-value" :class="primitiveClass">{{ preview() }}</span>

      <button class="copy-node" type="button" @click="copyValue">
        <Copy :size="12" aria-hidden="true" />
        <span>{{ copied ? "Copied" : "Copy" }}</span>
      </button>
    </div>

    <div v-if="isBranch" class="json-children">
      <div v-if="props.depth >= props.maxDepth" class="json-more">
        depth limit reached
      </div>
      <template v-else>
        <JsonNode
          v-for="[childKey, childValue] in visibleEntries"
          :key="childKey"
          :label="childKey"
          :value="childValue"
          :depth="props.depth + 1"
          :max-depth="props.maxDepth"
          :max-array-items="props.maxArrayItems"
          :expand-all="props.expandAll"
        />
        <div v-if="hiddenArrayItems > 0" class="json-more">
          [... {{ hiddenArrayItems }} more items]
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.json-node {
  position: relative;
  padding-left: calc(var(--depth) * 16px + 10px);
  white-space: nowrap;
}

.json-row {
  min-height: 24px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding-right: 8px;
}

.json-toggle {
  width: 18px;
  height: 18px;
  display: inline-grid;
  place-items: center;
  border: 0;
  background: transparent;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1;
}

.json-key {
  color: #815d27;
}

.json-value.string {
  color: #2f6b3f;
}

.json-value.number,
.json-value.boolean {
  color: #315f7d;
}

.json-value.null {
  color: var(--muted);
}

.json-preview,
.json-count,
.json-more {
  color: var(--muted);
}

.copy-node {
  min-height: 22px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 6px;
  border-radius: 5px;
  color: var(--muted-strong);
  font-size: 11px;
  opacity: 0;
  transition: opacity 120ms ease;
}

.json-node:hover > .json-row .copy-node,
.copy-node:focus-visible {
  opacity: 1;
}

.json-children {
  display: block;
}

.json-node.collapsed > .json-children {
  display: none;
}

.json-more {
  padding: 4px 0 6px 28px;
  font-family: var(--font-mono);
  font-size: 11px;
}
</style>
