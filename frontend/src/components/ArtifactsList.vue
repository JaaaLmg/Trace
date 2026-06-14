<script setup lang="ts">
import { ref } from "vue";
import { Check, Copy } from "@lucide/vue";
import type { RunArtifactOut } from "../types/api";

defineProps<{
  artifacts: RunArtifactOut[];
}>();

const copiedId = ref<string | null>(null);

async function copyText(id: string, text: string) {
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
  copiedId.value = id;
  window.setTimeout(() => {
    copiedId.value = null;
  }, 1000);
}
</script>

<template>
  <section class="artifacts-list" aria-label="Artifacts">
    <article v-for="artifact in artifacts" :key="artifact.id" class="artifact-row">
      <div class="artifact-main">
        <p class="artifact-type">{{ artifact.artifact_type }}</p>
        <code>{{ artifact.uri }}</code>
        <p class="artifact-meta">
          {{ artifact.size_bytes ?? 0 }} bytes
          <span v-if="artifact.content_hash">/ {{ artifact.content_hash }}</span>
        </p>
      </div>
      <button class="icon-button" type="button" title="复制产物路径" @click="copyText(artifact.id, artifact.uri)">
        <Check v-if="copiedId === artifact.id" :size="17" aria-hidden="true" />
        <Copy v-else :size="17" aria-hidden="true" />
        <span class="sr-only">复制产物路径</span>
      </button>
    </article>
    <p v-if="artifacts.length === 0" class="empty-note">
      暂无产物。run 还未进入 report 阶段，或执行失败发生在产物保存之前。
    </p>
  </section>
</template>

<style scoped>
.artifacts-list {
  display: grid;
  gap: 10px;
}

.artifact-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.78);
}

.artifact-main {
  min-width: 0;
}

.artifact-type {
  margin-bottom: 6px;
  color: var(--ink);
  font-weight: 700;
}

.artifact-row code {
  display: inline-block;
  max-width: 100%;
  overflow: auto;
}

.artifact-meta,
.empty-note {
  margin-top: 7px;
  color: var(--muted);
  font-size: 12px;
}
</style>
