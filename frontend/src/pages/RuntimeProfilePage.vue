<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Archive, Boxes, RefreshCw, Save, ShieldAlert } from "@lucide/vue";
import { listProjects } from "../api/projects";
import {
  archiveRuntimeProfile,
  createRuntimeProfile,
  getExecutorStatus,
  listRuntimeProfiles,
  updateRuntimeProfile
} from "../api/runtimeProfiles";
import type { ProjectOut, RuntimeProfileOut } from "../types/api";
import type { DataSource } from "../types/ui";
import { useI18n } from "../i18n";

const props = defineProps<{
  dataSource: DataSource;
}>();

const { t } = useI18n();
const projects = ref<ProjectOut[]>([]);
const profiles = ref<RuntimeProfileOut[]>([]);
const selectedProjectId = ref("");
const selectedProfileId = ref("");
const loading = ref(false);
const saving = ref(false);
const errorMessage = ref<string | null>(null);
const executorStatus = ref<Record<string, { available: boolean; warning?: string; unavailable_reason?: string | null }>>({});

const form = reactive({
  name: t("runtime.defaultName"),
  executor: "local_subprocess" as "local_subprocess" | "docker",
  image: "",
  workingDir: "",
  installCommand: "",
  testCommand: "python -m pytest tests -q --rootdir . -p no:cacheprovider",
  networkPolicy: "default" as "default" | "disabled" | "install_only",
  timeoutSeconds: 120
});

const selectedProfile = computed(() => profiles.value.find((profile) => profile.id === selectedProfileId.value) ?? null);

function capabilityMessage(status: { warning?: string; unavailable_reason?: string | null }): string {
  if (status.warning === "local_subprocess is not a security sandbox") {
    return t("runtime.localSubprocessWarningShort");
  }
  return status.warning || status.unavailable_reason || t("runtime.capabilitiesReported");
}

function applyProfile(profile: RuntimeProfileOut | null) {
  form.name = profile?.name ?? t("runtime.defaultName");
  form.executor = profile?.executor ?? "local_subprocess";
  form.image = profile?.image ?? "";
  form.workingDir = profile?.working_dir ?? "";
  form.installCommand = profile?.install_command ?? "";
  form.testCommand = profile?.test_command ?? "python -m pytest tests -q --rootdir . -p no:cacheprovider";
  form.networkPolicy = profile?.network_policy ?? "default";
  form.timeoutSeconds = Number(profile?.resource_limits?.timeout_seconds ?? 120);
}

async function loadAll() {
  if (props.dataSource !== "api") {
    projects.value = [];
    profiles.value = [];
    return;
  }
  loading.value = true;
  errorMessage.value = null;
  try {
    const [nextProjects, status] = await Promise.all([listProjects(), getExecutorStatus()]);
    projects.value = nextProjects;
    executorStatus.value = status.executors;
    if (!selectedProjectId.value) {
      selectedProjectId.value = nextProjects[0]?.id ?? "";
    }
    await loadProfiles();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t("runtime.loadFailed");
  } finally {
    loading.value = false;
  }
}

async function loadProfiles() {
  if (!selectedProjectId.value || props.dataSource !== "api") {
    profiles.value = [];
    return;
  }
  profiles.value = await listRuntimeProfiles(selectedProjectId.value);
  if (!selectedProfileId.value || !profiles.value.some((profile) => profile.id === selectedProfileId.value)) {
    selectedProfileId.value = profiles.value[0]?.id ?? "";
  }
  applyProfile(selectedProfile.value);
}

async function saveProfile() {
  if (!selectedProjectId.value) {
    return;
  }
  saving.value = true;
  errorMessage.value = null;
  const body = {
    name: form.name.trim(),
    executor: form.executor,
    image: form.image.trim() || null,
    working_dir: form.workingDir.trim() || null,
    install_command: form.installCommand.trim() || null,
    test_command: form.testCommand.trim(),
    network_policy: form.networkPolicy,
    timeout_seconds: Number(form.timeoutSeconds) || 120
  };
  try {
    const saved = selectedProfile.value
      ? await updateRuntimeProfile(selectedProfile.value.id, body)
      : await createRuntimeProfile(selectedProjectId.value, body);
    await loadProfiles();
    selectedProfileId.value = saved.id;
    applyProfile(saved);
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t("runtime.saveFailed");
  } finally {
    saving.value = false;
  }
}

async function archiveSelected() {
  const profile = selectedProfile.value;
  if (!profile) {
    return;
  }
  saving.value = true;
  errorMessage.value = null;
  try {
    await archiveRuntimeProfile(profile.id);
    selectedProfileId.value = "";
    await loadProfiles();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t("runtime.archiveFailed");
  } finally {
    saving.value = false;
  }
}

function newProfile() {
  selectedProfileId.value = "";
  applyProfile(null);
}

onMounted(() => {
  void loadAll();
});
</script>

<template>
  <main class="runtime-page app-page">
    <section class="page-head">
      <div>
        <p class="eyebrow">{{ t("runtime.eyebrow") }}</p>
        <h1>{{ t("runtime.title") }}</h1>
        <p>{{ t("runtime.subtitle") }}</p>
      </div>
      <button class="text-button" type="button" @click="loadAll">
        <RefreshCw :size="16" aria-hidden="true" />
        {{ t("projects.refresh") }}
      </button>
    </section>

    <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

    <section v-if="props.dataSource !== 'api'" class="subtle-panel empty-panel">
      <Boxes :size="22" aria-hidden="true" />
      <h2>{{ t("runtime.apiRequired") }}</h2>
      <p>{{ t("runtime.apiRequiredBody") }}</p>
    </section>

    <template v-else>
      <section class="summary-grid">
        <article v-for="(status, name) in executorStatus" :key="name" class="subtle-panel summary-tile">
          <span>{{ name }}</span>
          <strong>{{ status.available ? t("runtime.available") : t("runtime.unavailable") }}</strong>
          <small>{{ capabilityMessage(status) }}</small>
        </article>
      </section>

      <section class="runtime-grid">
        <aside class="subtle-panel profile-list">
          <div class="panel-title">
            <div>
              <p class="eyebrow">{{ t("runtime.project") }}</p>
              <select v-model="selectedProjectId" @change="loadProfiles">
                <option v-for="project in projects" :key="project.id" :value="project.id">
                  {{ project.name }}
                </option>
              </select>
            </div>
            <button class="text-button" type="button" @click="newProfile">{{ t("runtime.new") }}</button>
          </div>
          <button
            v-for="profile in profiles"
            :key="profile.id"
            class="profile-row"
            :class="{ selected: profile.id === selectedProfileId }"
            type="button"
            @click="selectedProfileId = profile.id; applyProfile(profile)"
          >
            <span>
              <strong>{{ profile.name }}</strong>
              <small>{{ profile.executor }} / {{ profile.network_policy }}</small>
            </span>
          </button>
          <p v-if="!loading && profiles.length === 0" class="muted-note">{{ t("runtime.empty") }}</p>
        </aside>

        <section class="subtle-panel editor-panel">
          <div class="panel-title">
            <div>
              <p class="eyebrow">{{ t("runtime.profileContract") }}</p>
              <h2>{{ selectedProfile ? t("runtime.editProfile") : t("runtime.createProfile") }}</h2>
            </div>
            <div class="actions">
              <button class="text-button" type="button" :disabled="!selectedProfile || saving" @click="archiveSelected">
                <Archive :size="16" aria-hidden="true" />
                {{ t("runtime.archive") }}
              </button>
              <button class="primary-action" type="button" :disabled="saving" @click="saveProfile">
                <Save :size="16" aria-hidden="true" />
                {{ saving ? t("runtime.saving") : t("runtime.save") }}
              </button>
            </div>
          </div>

          <p v-if="form.executor === 'local_subprocess'" class="policy-warning">
            <ShieldAlert :size="16" aria-hidden="true" />
            {{ t("runtime.localWarning") }}
          </p>

          <div class="form-grid">
            <label>
              <span>{{ t("runtime.name") }}</span>
              <input v-model="form.name" type="text" />
            </label>
            <label>
              <span>{{ t("runtime.executor") }}</span>
              <select v-model="form.executor">
                <option value="local_subprocess">local_subprocess</option>
                <option value="docker">docker</option>
              </select>
            </label>
            <label>
              <span>{{ t("runtime.dockerImage") }}</span>
              <input v-model="form.image" type="text" placeholder="python:3.12-slim" />
            </label>
            <label>
              <span>{{ t("runtime.workingDirectory") }}</span>
              <input v-model="form.workingDir" type="text" placeholder="/workspace" />
            </label>
            <label class="wide">
              <span>{{ t("runtime.installCommand") }}</span>
              <input v-model="form.installCommand" type="text" placeholder="pip install -r requirements.txt" />
            </label>
            <label class="wide">
              <span>{{ t("runtime.pytestCommand") }}</span>
              <input v-model="form.testCommand" type="text" />
            </label>
            <label>
              <span>{{ t("runtime.networkPolicy") }}</span>
              <select v-model="form.networkPolicy">
                <option value="default">default</option>
                <option value="disabled">disabled</option>
                <option value="install_only">install_only</option>
              </select>
            </label>
            <label>
              <span>{{ t("runtime.timeoutSeconds") }}</span>
              <input v-model.number="form.timeoutSeconds" min="1" type="number" />
            </label>
          </div>
        </section>
      </section>
    </template>
  </main>
</template>

<style scoped>
.page-head,
.panel-title,
.actions,
.policy-warning {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  justify-content: space-between;
}

.page-head {
  padding: 18px 0 24px;
  border-bottom: 1px solid var(--border);
}

.page-head h1 {
  margin: 8px 0 10px;
}

.page-head p {
  max-width: 760px;
  font-family: var(--font-serif);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.summary-tile,
.profile-list,
.editor-panel,
.empty-panel {
  padding: 16px;
}

.summary-tile {
  display: grid;
  gap: 3px;
}

.summary-tile span,
label span {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
}

.summary-tile strong {
  font-size: 20px;
}

.summary-tile small,
.profile-row small,
.muted-note {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  overflow-wrap: anywhere;
}

.runtime-grid {
  display: grid;
  grid-template-columns: minmax(260px, 340px) minmax(0, 1fr);
  gap: 18px;
  margin-top: 18px;
}

.profile-list,
.editor-panel,
.form-grid {
  display: grid;
  gap: 12px;
}

.profile-row {
  width: 100%;
  display: grid;
  justify-items: start;
  gap: 2px;
  padding: 10px;
  text-align: left;
}

.profile-row.selected {
  border-color: var(--tool);
  background: rgba(49, 95, 125, 0.08);
  box-shadow: inset 3px 0 0 var(--tool);
}

.policy-warning {
  justify-content: flex-start;
  padding: 10px;
  border: 1px solid rgba(138, 90, 0, 0.22);
  border-radius: 7px;
  background: var(--running-bg);
  color: var(--running);
  font-size: 13px;
}

.form-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

label {
  display: grid;
  gap: 6px;
}

label.wide {
  grid-column: 1 / -1;
}

input,
select {
  width: 100%;
  min-height: 36px;
  padding: 7px 9px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--ink);
}

.empty-panel {
  display: grid;
  gap: 10px;
  justify-items: center;
  margin-top: 18px;
  text-align: center;
}

@media (max-width: 900px) {
  .summary-grid,
  .runtime-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }

  .page-head,
  .panel-title {
    display: grid;
  }
}
</style>
