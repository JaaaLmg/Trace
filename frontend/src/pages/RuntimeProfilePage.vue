<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Archive, Boxes, RefreshCw, Save, ShieldAlert, Stethoscope } from "@lucide/vue";
import { listProjects } from "../api/projects";
import {
  archiveRuntimeProfile,
  createRuntimeProfile,
  getExecutorStatus,
  listRuntimeProfiles,
  preflightRuntimeProfileDraft,
  updateRuntimeProfile
} from "../api/runtimeProfiles";
import type { JsonObject, ProjectOut, RuntimeProfileOut, RuntimeProfileUpsertRequest } from "../types/api";
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
const preflightMessage = ref<string | null>(null);
const preflightResult = ref<PreflightResult | null>(null);
const executorStatus = ref<
  Record<
    string,
    {
      available: boolean;
      isolation_level?: string;
      network_enforced?: boolean;
      resource_limits_enforced?: boolean;
      warning?: string;
      unavailable_reason?: string | null;
    }
  >
>({});

type PreflightCheck = {
  name: string;
  status: string;
  message: string;
  [key: string]: unknown;
};

type PreflightResult = {
  status?: string;
  checks?: PreflightCheck[];
  replay_policy?: Record<string, unknown>;
  audit_only_limitations?: string[];
};

const DEFAULT_ARTIFACT_POLICY: JsonObject = { retain: "evidence" };
const DEFAULT_CLEANUP_POLICY: JsonObject = { mode: "manual", keep_failed: true };

const form = reactive({
  name: t("runtime.defaultName"),
  executor: "local_subprocess" as "local_subprocess" | "docker",
  image: "",
  workingDir: "",
  installCommand: "",
  testCommand: "python -m pytest tests -q --rootdir . -p no:cacheprovider",
  networkPolicy: "default" as "default" | "disabled" | "install_only",
  timeoutSeconds: 120,
  replayConcurrency: 1,
  maxRetries: 0,
  retryBackoffSeconds: 0,
  artifactPolicyText: formatJsonObject(DEFAULT_ARTIFACT_POLICY),
  cleanupPolicyText: formatJsonObject(DEFAULT_CLEANUP_POLICY)
});

const selectedProfile = computed(() => profiles.value.find((profile) => profile.id === selectedProfileId.value) ?? null);

function capabilityMessage(status: { warning?: string; unavailable_reason?: string | null }): string {
  if (status.warning === "local_subprocess is not a security sandbox") {
    return t("runtime.localSubprocessWarningShort");
  }
  return status.warning || status.unavailable_reason || t("runtime.capabilitiesReported");
}

function formatJsonObject(value: JsonObject | null | undefined, fallback?: JsonObject): string {
  return JSON.stringify(value ?? fallback ?? {}, null, 2);
}

function parseJsonObjectField(value: string, fieldName: string): JsonObject {
  const parsed = JSON.parse(value.trim() || "{}");
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error(`${fieldName} must be a JSON object`);
  }
  return parsed as JsonObject;
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
  form.replayConcurrency = Number(profile?.replay_policy?.replay_concurrency ?? profile?.resource_limits?.replay_concurrency ?? 1);
  form.maxRetries = Number(profile?.replay_policy?.max_retries ?? 0);
  form.retryBackoffSeconds = Number(profile?.replay_policy?.retry_backoff_seconds ?? 0);
  form.artifactPolicyText = formatJsonObject(profile?.artifact_policy, DEFAULT_ARTIFACT_POLICY);
  form.cleanupPolicyText = formatJsonObject(profile?.cleanup_policy, DEFAULT_CLEANUP_POLICY);
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
  errorMessage.value = null;
  let artifactPolicy: JsonObject;
  let cleanupPolicy: JsonObject;
  try {
    artifactPolicy = parseJsonObjectField(form.artifactPolicyText, "artifact_policy");
    cleanupPolicy = parseJsonObjectField(form.cleanupPolicyText, "cleanup_policy");
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t("runtime.saveFailed");
    return;
  }

  saving.value = true;
  const body: RuntimeProfileUpsertRequest = {
    name: form.name.trim(),
    executor: form.executor,
    image: form.image.trim() || null,
    working_dir: form.workingDir.trim() || null,
    install_command: form.installCommand.trim() || null,
    test_command: form.testCommand.trim(),
    network_policy: form.networkPolicy,
    timeout_seconds: Number(form.timeoutSeconds) || 120,
    replay_policy: {
      replay_concurrency: Math.max(1, Number(form.replayConcurrency) || 1),
      max_retries: Math.max(0, Number(form.maxRetries) || 0),
      retry_backoff_seconds: Math.max(0, Number(form.retryBackoffSeconds) || 0)
    },
    artifact_policy: artifactPolicy,
    cleanup_policy: cleanupPolicy
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

async function runPreflight() {
  errorMessage.value = null;
  preflightMessage.value = null;
  let artifactPolicy: JsonObject;
  let cleanupPolicy: JsonObject;
  try {
    artifactPolicy = parseJsonObjectField(form.artifactPolicyText, "artifact_policy");
    cleanupPolicy = parseJsonObjectField(form.cleanupPolicyText, "cleanup_policy");
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t("runtime.saveFailed");
    return;
  }
  const result = (await preflightRuntimeProfileDraft({
    name: form.name.trim(),
    executor: form.executor,
    image: form.image.trim() || null,
    working_dir: form.workingDir.trim() || null,
    install_command: form.installCommand.trim() || null,
    test_command: form.testCommand.trim(),
    network_policy: form.networkPolicy,
    timeout_seconds: Number(form.timeoutSeconds) || 120,
    replay_policy: {
      replay_concurrency: Math.max(1, Number(form.replayConcurrency) || 1),
      max_retries: Math.max(0, Number(form.maxRetries) || 0),
      retry_backoff_seconds: Math.max(0, Number(form.retryBackoffSeconds) || 0)
    },
    artifact_policy: artifactPolicy,
    cleanup_policy: cleanupPolicy
  })) as PreflightResult;
  preflightResult.value = result;
  preflightMessage.value = `Preflight ${String(result.status)} · ${String((result.checks as unknown[] | undefined)?.length ?? 0)} checks`;
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
    <p v-if="preflightMessage" class="mode-note">{{ preflightMessage }}</p>

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
          <small>{{ t("runtime.isolation") }}: {{ status.isolation_level ?? t("common.unknown") }} · {{ t("runtime.networkEnforced") }}: {{ status.network_enforced ? t("common.yes") : t("common.no") }} · {{ t("runtime.resourceLimits") }}: {{ status.resource_limits_enforced ? t("common.yes") : t("common.no") }}</small>
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
              <button class="text-button" type="button" :disabled="saving" @click="runPreflight">
                <Stethoscope :size="16" aria-hidden="true" />
                {{ t("runtime.preflight") }}
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

          <section v-if="preflightResult" class="preflight-panel">
            <div class="preflight-head">
              <span>{{ t("runtime.preflightChecks") }}</span>
              <strong :data-status="preflightResult.status">{{ preflightResult.status }}</strong>
            </div>
            <div class="preflight-grid">
              <article v-for="check in preflightResult.checks ?? []" :key="check.name" :data-status="check.status">
                <span>{{ check.name }}</span>
                <strong>{{ check.status }}</strong>
                <small>{{ check.message }}</small>
              </article>
            </div>
            <div class="preflight-foot">
              <code>{{ t("runtime.replayPolicy") }} {{ JSON.stringify(preflightResult.replay_policy ?? {}) }}</code>
              <code v-for="limitation in preflightResult.audit_only_limitations ?? []" :key="limitation">{{ limitation }}</code>
            </div>
          </section>

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
            <label>
              <span>{{ t("runtime.replayConcurrency") }}</span>
              <input v-model.number="form.replayConcurrency" min="1" type="number" />
            </label>
            <label>
              <span>{{ t("runtime.maxRetries") }}</span>
              <input v-model.number="form.maxRetries" min="0" type="number" />
            </label>
            <label>
              <span>{{ t("runtime.retryBackoff") }}</span>
              <input v-model.number="form.retryBackoffSeconds" min="0" step="0.1" type="number" />
            </label>
            <label class="wide">
              <span>{{ t("runtime.artifactPolicy") }}</span>
              <textarea v-model="form.artifactPolicyText" class="policy-textarea" rows="4" spellcheck="false"></textarea>
            </label>
            <label class="wide">
              <span>{{ t("runtime.cleanupPolicy") }}</span>
              <textarea v-model="form.cleanupPolicyText" class="policy-textarea" rows="4" spellcheck="false"></textarea>
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

.summary-tile small + small {
  margin-top: 2px;
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

.preflight-panel {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.58);
}

.preflight-head {
  display: flex;
  gap: 10px;
  justify-content: space-between;
  align-items: center;
}

.preflight-head span,
.preflight-grid span {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
}

.preflight-head strong[data-status="failed"],
.preflight-grid article[data-status="failed"] strong {
  color: var(--failed);
}

.preflight-head strong[data-status="warning"],
.preflight-grid article[data-status="warning"] strong {
  color: var(--running);
}

.preflight-head strong[data-status="passed"],
.preflight-grid article[data-status="passed"] strong {
  color: var(--passed);
}

.preflight-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.preflight-grid article {
  display: grid;
  gap: 3px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.62);
}

.preflight-grid small,
.preflight-foot code {
  overflow-wrap: anywhere;
  color: var(--muted-strong);
  font-family: var(--font-mono);
  font-size: 11px;
}

.preflight-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.preflight-foot code {
  padding: 4px 7px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: rgba(251, 250, 247, 0.7);
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
select,
textarea {
  width: 100%;
  min-height: 36px;
  padding: 7px 9px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--ink);
}

textarea {
  resize: vertical;
}

.policy-textarea {
  min-height: 96px;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.5;
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
  .form-grid,
  .preflight-grid {
    grid-template-columns: 1fr;
  }

  .page-head,
  .panel-title {
    display: grid;
  }
}
</style>

