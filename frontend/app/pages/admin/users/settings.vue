<script setup lang="ts">
import { Loader2 } from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Label } from "~/components/ui/label";
import { Switch } from "~/components/ui/switch";
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert";
import type { SystemConfigItem, SystemConfigListResponse } from "~/types/api";
import { useConfigStore } from "~/stores/config";

const REGISTRATION_ENABLED_KEY = "registration_enabled";

const { t } = useI18n();

definePageMeta({
  layout: "admin",
  breadcrumb: "User Settings",
});

const { showError, showSuccess } = useNotifications();
const { $api } = useNuxtApp();
const configStore = useConfigStore();

const { data, pending, error, refresh } = await useAPI<SystemConfigListResponse>(
  "/v1/admin/config",
  { server: false }
);

const configs = computed<SystemConfigItem[]>(() => data.value?.configs ?? []);

const registrationEnabledConfig = computed(() =>
  configs.value.find((cfg) => cfg.key === REGISTRATION_ENABLED_KEY)
);
const registrationEnabled = ref(true);

watch(
  configs,
  (newConfigs) => {
    const regConfig = newConfigs.find((cfg) => cfg.key === REGISTRATION_ENABLED_KEY);
    if (!regConfig) {
      registrationEnabled.value = true;
    } else {
      registrationEnabled.value = String(regConfig.value).toLowerCase() !== "false";
    }
  },
  { immediate: true }
);

const isSaving = ref(false);

const handleSaveRegistrationEnabled = async (value: boolean) => {
  isSaving.value = true;
  try {
    const payload = registrationEnabledConfig.value
      ? { value: value, is_enabled: true }
      : {
          key: REGISTRATION_ENABLED_KEY,
          value: value,
          description: t("admin.systemConfig.registration.configDescription"),
          is_public: true,
          is_enabled: true,
        };
    const url = registrationEnabledConfig.value
      ? `/v1/admin/config/${REGISTRATION_ENABLED_KEY}`
      : "/v1/admin/config";
    const method = registrationEnabledConfig.value ? "PUT" : "POST";

    await $api(url, {
      method,
      body: payload,
    });

    await refresh();
    await configStore.loadConfig(true);
    showSuccess(t("admin.systemConfig.messages.saveSuccess"));
  } catch (err: any) {
    showError(err.message || t("admin.systemConfig.messages.saveFailed"));
    registrationEnabled.value = !value;
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
        <CardTitle>{{ t("admin.systemConfig.registration.title") }}</CardTitle>
        <CardDescription>
          {{ t("admin.systemConfig.registration.description") }}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div class="flex items-center space-x-2">
          <Switch
            id="registration-enabled"
            :model-value="registrationEnabled"
            @update:model-value="handleSaveRegistrationEnabled"
            :disabled="isSaving"
          />
          <Label for="registration-enabled">{{
            t("admin.systemConfig.registration.enabledLabel")
          }}</Label>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
