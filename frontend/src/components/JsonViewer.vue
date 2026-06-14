<script setup lang="ts">
import { ref } from "vue";
import { Copy, FolderOpen, Minimize2 } from "@lucide/vue";
import JsonNode from "./JsonNode.vue";
import type { JsonValue } from "../types/api";

const props = defineProps<{
  value: JsonValue | null | undefined;
  maxDepth?: number;
  maxArrayItems?: number;
}>();

const viewerKey = ref(0);
const copied = ref(false);
const expandAll = ref(false);

function collapseTree() {
  expandAll.value = false;
  viewerKey.value += 1;
}

function expandTree() {
  expandAll.value = true;
  viewerKey.value += 1;
}

async function copyFullPayload() {
  const text = JSON.stringify(props.value ?? null, null, 2);
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
  }, 1000);
}
</script>

<template>
  <div class="json-shell">
    <div class="json-tools">
      <button type="button" class="text-button" @click="expandTree">
        <FolderOpen :size="15" aria-hidden="true" />
        Expand
      </button>
      <button type="button" class="text-button" @click="collapseTree">
        <Minimize2 :size="15" aria-hidden="true" />
        Collapse
      </button>
      <button type="button" class="text-button" @click="copyFullPayload">
        <Copy :size="15" aria-hidden="true" />
        {{ copied ? "Copied full payload" : "Copy full payload" }}
      </button>
    </div>
    <p class="json-note">
      Large payload guard: arrays render first {{ props.maxArrayItems ?? 50 }} items, depth limit is
      {{ props.maxDepth ?? 10 }}.
    </p>
    <div class="json-viewer" aria-label="Collapsible JSON viewer">
      <JsonNode
        :key="viewerKey"
        :value="props.value ?? null"
        :max-depth="props.maxDepth ?? 10"
        :max-array-items="props.maxArrayItems ?? 50"
        :expand-all="expandAll"
      />
    </div>
  </div>
</template>

<style scoped>
.json-shell {
  min-width: 0;
}

.json-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.json-note {
  margin-bottom: 10px;
  padding: 8px 10px;
  border: 1px dashed var(--border-strong);
  border-radius: 7px;
  background: rgba(251, 250, 247, 0.82);
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
}

.json-viewer {
  max-height: 520px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: #fffcf7;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.62;
}
</style>
