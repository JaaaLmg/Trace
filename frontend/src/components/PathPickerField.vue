<script setup lang="ts">
import { ref } from "vue";
import { FolderOpen, Loader2 } from "@lucide/vue";
import { pickLocalDirectory } from "../api/local";
import { useI18n } from "../i18n";

type DirectoryHandle = {
  name: string;
  path?: string;
};

type DirectoryPickerWindow = Window & {
  showDirectoryPicker?: (options?: { mode?: "read" }) => Promise<DirectoryHandle>;
};

type BrowserDirectoryFile = File & {
  path?: string;
  mozFullPath?: string;
  webkitRelativePath: string;
};

const props = withDefaults(
  defineProps<{
    modelValue: string;
    label: string;
    placeholder?: string;
    required?: boolean;
    disabled?: boolean;
    initialPath?: string | null;
    pickerTitle?: string;
  }>(),
  {
    placeholder: "",
    required: false,
    disabled: false,
    initialPath: null,
    pickerTitle: ""
  }
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();

const { t } = useI18n();
const folderInput = ref<HTMLInputElement | null>(null);
const picking = ref(false);
const pickerMessage = ref<string | null>(null);

function updateValue(value: string) {
  emit("update:modelValue", value);
  pickerMessage.value = null;
}

function directoryFromFile(file: BrowserDirectoryFile): string | null {
  const absolutePath = file.path || file.mozFullPath;
  if (!absolutePath) {
    return null;
  }

  const relativePath = file.webkitRelativePath.replace(/\//g, "\\");
  if (relativePath && absolutePath.endsWith(relativePath)) {
    return absolutePath.slice(0, -relativePath.length).replace(/[\\/]+$/, "");
  }

  return absolutePath.replace(/[\\/][^\\/]*$/, "");
}

async function pickWithBrowserApi(): Promise<boolean> {
  const picker = (window as DirectoryPickerWindow).showDirectoryPicker;
  if (!picker) {
    return false;
  }

  const handle = await picker({ mode: "read" });
  if (handle.path) {
    updateValue(handle.path);
    return true;
  }

  pickerMessage.value = t("pathPicker.browserOnly", { name: handle.name });
  return true;
}

async function chooseDirectory() {
  if (props.disabled || picking.value) {
    return;
  }

  picking.value = true;
  pickerMessage.value = null;
  try {
    const result = await pickLocalDirectory(props.modelValue || props.initialPath, props.pickerTitle || t("pathPicker.dialogTitle"));
    if (!result.cancelled && result.path) {
      updateValue(result.path);
    }
    return;
  } catch {
    try {
      const handled = await pickWithBrowserApi();
      if (handled) {
        return;
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      pickerMessage.value = null;
    }
    folderInput.value?.click();
  } finally {
    picking.value = false;
  }
}

function handleBrowserFolder(event: Event) {
  const input = event.target as HTMLInputElement;
  const firstFile = input.files?.[0] as BrowserDirectoryFile | undefined;
  if (!firstFile) {
    input.value = "";
    return;
  }

  const directory = directoryFromFile(firstFile);
  if (directory) {
    updateValue(directory);
  } else {
    const folderName = firstFile.webkitRelativePath.split(/[\\/]/)[0] || firstFile.name;
    pickerMessage.value = t("pathPicker.browserOnly", { name: folderName });
  }
  input.value = "";
}
</script>

<template>
  <label class="path-picker-field">
    <span>{{ props.label }}</span>
    <span class="path-control">
      <input
        :value="props.modelValue"
        :required="props.required"
        :disabled="props.disabled"
        type="text"
        :placeholder="props.placeholder"
        @input="updateValue(($event.target as HTMLInputElement).value)"
      />
      <button
        class="path-pick-button"
        type="button"
        :disabled="props.disabled || picking"
        :title="t('pathPicker.pickFolder')"
        @click="chooseDirectory"
      >
        <Loader2 v-if="picking" class="spinner" :size="17" aria-hidden="true" />
        <FolderOpen v-else :size="17" aria-hidden="true" />
        <span class="sr-only">{{ t("pathPicker.pickFolder") }}</span>
      </button>
      <input
        ref="folderInput"
        class="sr-only"
        type="file"
        webkitdirectory
        directory
        multiple
        tabindex="-1"
        @change="handleBrowserFolder"
      />
    </span>
    <small v-if="pickerMessage" class="path-picker-message">{{ pickerMessage }}</small>
  </label>
</template>

<style scoped>
.path-picker-field {
  display: grid;
  gap: 5px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}

.path-control {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 38px;
  align-items: stretch;
}

.path-control input[type="text"] {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 6px 0 0 6px;
  background: var(--panel);
  color: var(--ink);
  padding: 8px 9px;
}

.path-pick-button {
  display: grid;
  place-items: center;
  border-left: 0;
  border-radius: 0 6px 6px 0;
  color: var(--muted-strong);
}

.path-pick-button:hover:not(:disabled) {
  color: var(--ink);
}

.path-pick-button svg {
  transition: transform var(--motion-fast) var(--ease-standard);
}

.path-pick-button:hover:not(:disabled) svg {
  transform: translateY(-1px);
}

.path-pick-button .spinner {
  animation: spin 900ms linear infinite;
}

.path-picker-message {
  color: var(--muted);
  font-weight: 500;
  overflow-wrap: anywhere;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
