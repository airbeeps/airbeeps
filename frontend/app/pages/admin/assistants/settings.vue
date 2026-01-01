<script setup lang="ts">
import { Loader2 } from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Label } from "~/components/ui/label";
import { Switch } from "~/components/ui/switch";
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert";
import type { SystemConfigItem, SystemConfigListResponse } from "~/types/api";
import { useConfigStore } from "~/stores/config";

const ALLOW_CREATE_ASSISTANTS_KEY = "allow_user_create_assistants";

const { t } = useI18n();

definePageMeta({
  layout: "admin",
  breadcrumb: "Assistant Settings",
});

const { showError, showSuccess } = useNotifications();
const { $api } = useNuxtApp();
const configStore = useConfigStore();

const { data, pending, error, refresh } = await useAPI<SystemConfigListResponse>(
  "/v1/admin/config",
  { server: false }
);

const configs = computed<SystemConfigItem[]>(() => data.value?.configs ?? []);

const allowCreateAssistantsConfig = computed(() =>
  configs.value.find((cfg) => cfg.key === ALLOW_CREATE_ASSISTANTS_KEY)
);
const allowCreateAssistants = ref(true);

watch(
  configs,
  (newConfigs) => {
    const allowConfig = newConfigs.find((cfg) => cfg.key === ALLOW_CREATE_ASSISTANTS_KEY);
    if (!allowConfig) {
      allowCreateAssistants.value = true;
    } else {
      allowCreateAssistants.value = String(allowConfig.value).toLowerCase() !== "false";
    }
  },
  { immediate: true }
);

const isSaving = ref(false);

const handleSaveAllowCreateAssistants = async (value: boolean) => {
  isSaving.value = true;
  try {
    const payload = allowCreateAssistantsConfig.value
      ? { value: value, is_enabled: true }
      : {
          key: ALLOW_CREATE_ASSISTANTS_KEY,
          value: value,
          description: t("admin.systemConfig.assistants.configDescription"),
          is_public: true,
          is_enabled: true,
        };
    const url = allowCreateAssistantsConfig.value
      ? `/v1/admin/config/${ALLOW_CREATE_ASSISTANTS_KEY}`
      : "/v1/admin/config";
    const method = allowCreateAssistantsConfig.value ? "PUT" : "POST";

    await $api(url, {
      method,
      body: payload,
    });

    await refresh();
    await configStore.loadConfig(true);
    showSuccess(t("admin.systemConfig.messages.saveSuccess"));
  } catch (err: any) {
    showError(err.message || t("admin.systemConfig.messages.saveFailed"));
    allowCreateAssistants.value = !value;
  } finally {
    isSaving.value = false;
  }
};
</script>

<template>
  <div class="space-y-6">
    <Alert v-if="error" variant="destructive">
      <AlertTitle>{{ t("common.error") }}</AlertTitle>
      <AlertDescription>
        {{ error?.message || t("admin.systemConfig.messages.saveFailed") }}
      </AlertDescription>
    </Alert>

    <Card>
      <CardHeader>
        <CardTitle>{{ t("admin.systemConfig.assistants.title") }}</CardTitle>
        <CardDescription>
          {{ t("admin.systemConfig.assistants.description") }}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div class="flex items-center space-x-2">
          <Switch
            id="allow-create-assistants"
            :model-value="allowCreateAssistants"
            @update:model-value="handleSaveAllowCreateAssistants"
            :disabled="isSaving"
          />
          <Label for="allow-create-assistants">{{
            t("admin.systemConfig.assistants.allowCreateLabel")
          }}</Label>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
