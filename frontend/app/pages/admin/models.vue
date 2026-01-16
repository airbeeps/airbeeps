<script setup lang="ts">
import { computed, h, ref } from "vue";
import { Badge } from "~/components/ui/badge";
import { toast } from "vue-sonner";
import { Search } from "lucide-vue-next";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "~/components/ui/alert-dialog";
import { Button } from "~/components/ui/button";
import type { ModelViewConfig } from "~/components/model-view/ModelView.vue";
import type { Model, Provider } from "~/types/api";

const { t } = useI18n();
const { $api } = useNuxtApp();

definePageMeta({
  breadcrumb: "admin.pages.models.breadcrumb",
  layout: "admin",
});

// Fetch provider list
const { data: providers } = useAPI<Provider[]>("/v1/admin/all-providers", {
  server: false,
});
const providerOptions = computed(() =>
  (providers.value ?? []).map((p) => ({ label: p.display_name, value: p.id }))
);
const providerMap = computed(() => {
  const map: Record<string, Provider> = {};
  (providers.value ?? []).forEach((p) => {
    map[p.id] = p;
  });
  return map;
});

type ModelTemplate = {
  name: string;
  display_name: string;
  description?: string;
  capabilities?: string[];
  generation_config?: Record<string, any>;
  max_context_tokens?: number;
  max_output_tokens?: number;
};

type ModelAsset = {
  id: string;
  identifier: string;
  status: string;
  local_path?: string;
};

type HfResolveResponse = {
  repo_id: string;
  available: boolean;
  source: string;
  local_path?: string | null;
  asset_id?: string | null;
};

const { data: hfEmbeddingAssets, refresh: refreshHfEmbeddingAssets } = useAPI<ModelAsset[]>(
  "/v1/admin/model-assets/huggingface/embeddings?status=READY",
  {
    server: false,
  }
);

const hfInstalledRepoIds = computed(
  () => new Set((hfEmbeddingAssets.value ?? []).map((a) => a.identifier))
);

const modelTemplatesByProviderId = ref<Record<string, ModelTemplate[]>>({});
const templatesLoadingByProviderId = ref<Record<string, boolean>>({});

const ensureModelTemplatesLoaded = async (providerId: string, forceRefresh = false) => {
  if (!providerId) return;
  if (modelTemplatesByProviderId.value[providerId] && !forceRefresh) return;
  if (templatesLoadingByProviderId.value[providerId]) return;
  templatesLoadingByProviderId.value = {
    ...templatesLoadingByProviderId.value,
    [providerId]: true,
  };
  try {
    // Use the new available-models endpoint with live fetching and caching
    const queryParams = forceRefresh ? "?force_refresh=true" : "";
    const response = await $api<{ models: Array<{ id: string; name: string }> }>(
      `/v1/admin/providers/${providerId}/available-models${queryParams}`,
      { method: "GET" }
    );

    // Convert the response format to ModelTemplate format
    const templates: ModelTemplate[] = (response?.models ?? []).map((m) => ({
      name: m.id,
      display_name: m.name,
    }));

    modelTemplatesByProviderId.value = {
      ...modelTemplatesByProviderId.value,
      [providerId]: templates,
    };
  } catch (e) {
    modelTemplatesByProviderId.value = {
      ...modelTemplatesByProviderId.value,
      [providerId]: [],
    };
  } finally {
    templatesLoadingByProviderId.value = {
      ...templatesLoadingByProviderId.value,
      [providerId]: false,
    };
  }
};

const lastProviderId = ref<string | null>(null);
const lastAppliedTemplateKey = ref<string | null>(null);
const isInitialLoad = ref<boolean>(true);

// HF download prompt state (only used when provider is HF local embeddings)
const hfDownloadPromptOpen = ref(false);
const hfDownloadRepoId = ref<string | null>(null);
const lastHfPromptedRepoId = ref<string | null>(null);
const hfResolveInFlight = ref<Record<string, boolean>>({});

const handleHfDownloadConfirm = async () => {
  if (hfDownloadRepoId.value) {
    await queueHfDownload(hfDownloadRepoId.value);
  }
  hfDownloadPromptOpen.value = false;
};

const queueHfDownload = async (repoId: string) => {
  try {
    const asset = await $api<ModelAsset>("/v1/admin/model-assets/huggingface/embeddings/download", {
      method: "POST",
      body: { repo_id: repoId },
    });
    toast.success(t("admin.pages.models.hf.downloadQueued"));
    // Best-effort refresh after a short delay
    setTimeout(() => refreshHfEmbeddingAssets(), 1500);
    return asset;
  } catch (e: any) {
    toast.error(e?.data?.detail || e?.message || t("common.error"));
    return null;
  }
};

const resolveHfAvailable = async (repoId: string): Promise<boolean> => {
  try {
    const res = await $api<HfResolveResponse>(
      `/v1/admin/model-assets/huggingface/embeddings/resolve?repo_id=${encodeURIComponent(repoId)}`,
      { method: "GET" }
    );
    if (res?.available) {
      // Keep installed list in sync (backend will upsert READY when found in HF cache)
      refreshHfEmbeddingAssets();
      return true;
    }
  } catch {
    // ignore
  }
  return false;
};

const maybePromptHfDownload = (repoId: string) => {
  if (!repoId) return;
  if (hfInstalledRepoIds.value.has(repoId)) return;
  if (hfResolveInFlight.value[repoId]) return;

  hfResolveInFlight.value = { ...hfResolveInFlight.value, [repoId]: true };
  void (async () => {
    const available = await resolveHfAvailable(repoId);
    hfResolveInFlight.value = { ...hfResolveInFlight.value, [repoId]: false };
    if (available) return;

    if (repoId !== lastHfPromptedRepoId.value) {
      hfDownloadRepoId.value = repoId;
      hfDownloadPromptOpen.value = true;
      lastHfPromptedRepoId.value = repoId;
    }
  })();
};

// Model capability options
const capabilityOptions = computed(() => [
  { label: t("admin.pages.models.capabilities.chat"), value: "chat" },
  {
    label: t("admin.pages.models.capabilities.completion"),
    value: "completion",
  },
  { label: t("admin.pages.models.capabilities.embedding"), value: "embedding" },
  { label: t("admin.pages.models.capabilities.vision"), value: "vision" },
  { label: t("admin.pages.models.capabilities.audio"), value: "audio" },
  {
    label: t("admin.pages.models.capabilities.function_calling"),
    value: "function_calling",
  },
  { label: t("admin.pages.models.capabilities.tool_use"), value: "tool_use" },
  { label: t("admin.pages.models.capabilities.code"), value: "code" },
  {
    label: t("admin.pages.models.capabilities.image_generation"),
    value: "image_generation",
  },
  { label: t("admin.pages.models.capabilities.reranker"), value: "reranker" },
]);

// Model configuration
const providerConfig = computed(
  (): ModelViewConfig<Model> => ({
    title: t("admin.pages.models.title"),
    description: t("admin.pages.models.description"),
    apiEndpoint: "/v1/admin/models",
    onFormChange: ({ formData, mode, setValues }) => {
      const providerId = (formData?.provider_id as string) || "";
      const provider = providerId ? providerMap.value[providerId] : undefined;

      // Load suggestions when provider changes (for both create and edit modes)
      if (providerId && providerId !== lastProviderId.value) {
        lastProviderId.value = providerId;
        lastAppliedTemplateKey.value = null;
        lastHfPromptedRepoId.value = null;
        isInitialLoad.value = true;
        ensureModelTemplatesLoaded(providerId);
      }

      const templateName = (formData?.template_id as string) || "";

      // If template is cleared (empty string), reset to empty state
      if (templateName === "" && lastAppliedTemplateKey.value !== null) {
        lastAppliedTemplateKey.value = null;
        return;
      }

      if (!providerId || !templateName || !setValues) return;

      const templateKey = `${providerId}:${templateName}`;

      // Skip if this is the same template we already applied
      if (templateKey === lastAppliedTemplateKey.value) return;

      // In edit mode, skip initial load (when form opens with existing data)
      // but allow subsequent template selections to update fields
      if (mode === "edit" && isInitialLoad.value) {
        isInitialLoad.value = false;
        lastAppliedTemplateKey.value = templateKey;
        return;
      }

      const templates = modelTemplatesByProviderId.value[providerId] ?? [];
      const tpl = templates.find((m) => m.name === templateName);

      if (tpl) {
        // For HF providers: if selected model isn't installed, offer a download prompt
        if (provider?.category === "LOCAL") {
          maybePromptHfDownload(templateName);
        }

        setValues({
          name: tpl.name,
          display_name: tpl.display_name || tpl.name,
          description: tpl.description ?? "",
          capabilities: tpl.capabilities ?? [],
          generation_config: JSON.stringify(tpl.generation_config ?? {}, null, 2),
          max_context_tokens: tpl.max_context_tokens ?? 0,
          max_output_tokens: tpl.max_output_tokens ?? 0,
        });
        lastAppliedTemplateKey.value = templateKey;
      } else if (templateName) {
        // If template name is provided but not found, just prefill the name
        setValues({
          name: templateName,
          display_name: templateName,
        });
        lastAppliedTemplateKey.value = templateKey;
      }

      // Mark as no longer initial load after first template processing
      isInitialLoad.value = false;
    },

    columns: [
      {
        accessorKey: "name",
        header: t("admin.pages.models.columns.modelName"),
        cell: (ctx) => {
          const value = ctx.getValue() as string;
          if (!value) return "-";
          const viewAction = {
            key: "view",
            label: t("components.modelView.view"),
          };
          return h(
            "button",
            {
              class:
                "text-primary font-medium cursor-pointer text-left focus:outline-none focus:ring-2 focus:ring-primary/40 rounded-full bg-muted/30 hover:bg-muted/60 hover:underline px-2 py-0.5 transition-colors",
              type: "button",
              onClick: (e: Event) => {
                e.stopPropagation();
                ctx.table.options.meta?.triggerRowAction?.(viewAction, ctx.row.original);
              },
            },
            value
          );
        },
      },
      {
        accessorKey: "display_name",
        header: t("admin.pages.models.columns.displayName"),
        cell: (ctx) => {
          const value = ctx.getValue() as string;
          if (!value) return "-";
          const viewAction = {
            key: "view",
            label: t("components.modelView.view"),
          };
          return h(
            "button",
            {
              class:
                "text-primary font-medium cursor-pointer text-left focus:outline-none focus:ring-2 focus:ring-primary/40 rounded-full bg-muted/30 hover:bg-muted/60 hover:underline px-2 py-0.5 transition-colors",
              type: "button",
              onClick: (e: Event) => {
                e.stopPropagation();
                ctx.table.options.meta?.triggerRowAction?.(viewAction, ctx.row.original);
              },
            },
            value
          );
        },
      },
      {
        accessorKey: "provider_id",
        header: t("admin.pages.models.columns.provider"),
        cell: (ctx) => {
          const id = ctx.getValue() as string;
          const provider = providerMap.value[id];
          return provider ? provider.display_name : id;
        },
      },
      {
        accessorKey: "capabilities",
        header: t("admin.pages.models.columns.capabilities"),
        cell: (ctx) => {
          const capabilities = (ctx.getValue() as string[]) || [];
          return h(
            "div",
            { class: "flex flex-wrap gap-1" },
            capabilities.map((cap) => {
              const option = capabilityOptions.value.find((opt) => opt.value === cap);
              return h(
                Badge,
                {
                  key: cap,
                  variant: "secondary",
                  class: "text-xs",
                },
                () => option?.label || cap
              );
            })
          );
        },
      },
      {
        accessorKey: "created_at",
        header: t("admin.pages.models.columns.createdAt"),
        cell: (context) => {
          const value = context.getValue() as string;
          return new Date(value).toLocaleDateString();
        },
      },
    ],

    detailFields: [
      {
        name: "id",
        label: t("admin.pages.models.detailFields.id"),
        type: "text",
      },
      {
        name: "name",
        label: t("admin.pages.models.detailFields.modelName"),
        type: "text",
      },
      {
        name: "display_name",
        label: t("admin.pages.models.detailFields.displayName"),
        type: "text",
      },
      {
        name: "provider_id",
        label: t("admin.pages.models.detailFields.provider"),
        type: "text",
        render: (val: string) => providerMap.value[val]?.display_name || val,
      },
      {
        name: "description",
        label: t("admin.pages.models.detailFields.description"),
        type: "textarea",
      },
      {
        name: "capabilities",
        label: t("admin.pages.models.detailFields.capabilities"),
        type: "text",
        render: (val: string[]) => {
          if (!val || val.length === 0)
            return t("admin.pages.models.detailFields.capabilitiesNotSet");
          return val
            .map((cap) => {
              const option = capabilityOptions.value.find((opt) => opt.value === cap);
              return option?.label || cap;
            })
            .join(", ");
        },
      },
      {
        name: "generation_config",
        label: t("admin.pages.models.detailFields.generationConfig"),
        type: "json",
      },
      {
        name: "status",
        label: t("admin.pages.models.detailFields.status"),
        type: "text",
      },
      {
        name: "max_context_tokens",
        label: t("admin.pages.models.detailFields.maxContextTokens"),
        type: "text",
        render: (val: number) =>
          val ? val.toLocaleString() : t("admin.pages.models.detailFields.notSet"),
      },
      {
        name: "max_output_tokens",
        label: t("admin.pages.models.detailFields.maxOutputTokens"),
        type: "text",
        render: (val: number) =>
          val ? val.toLocaleString() : t("admin.pages.models.detailFields.notSet"),
      },
      {
        name: "created_at",
        label: t("admin.pages.models.detailFields.createdAt"),
        type: "datetime",
      },
    ],

    formFields: [
      {
        name: "provider_id",
        label: t("admin.pages.models.formFields.provider"),
        type: "select",
        required: true,
        options: providerOptions.value,
        placeholder: t("admin.pages.models.formFields.providerPlaceholder"),
      },
      {
        name: "template_id",
        label: t("admin.pages.models.formFields.modelTemplate"),
        type: "select",
        required: false,
        options: (formData) => {
          const providerId = (formData?.provider_id as string) || "";
          const provider = providerId ? providerMap.value[providerId] : undefined;
          const templates = providerId ? (modelTemplatesByProviderId.value[providerId] ?? []) : [];

          // Build options list
          const opts: { label: string; value: string; group?: string }[] = [];

          // Add "None" option at the top
          opts.push({
            label: t("admin.pages.models.formFields.noTemplate"),
            value: "",
          });

          // For HuggingFace: Add installed models
          if (provider?.category === "LOCAL") {
            const installedIds = hfInstalledRepoIds.value;
            const installedOnly = [...installedIds].filter(
              (id) => !templates.some((t) => t.name === id)
            );
            installedOnly.forEach((id) => {
              opts.push({
                label: `${t("admin.pages.models.hf.installedPrefix")}: ${id}`,
                value: id,
                group: "Installed Models",
              });
            });
          }

          // Show available models from the provider (fetched live via available-models endpoint)
          if (templates.length > 0) {
            templates.forEach((m) => {
              const suffix =
                provider?.category === "LOCAL" && hfInstalledRepoIds.value.has(m.name)
                  ? ` (${t("admin.pages.models.hf.installedSuffix")})`
                  : "";
              const displayLabel =
                m.display_name && m.display_name !== m.name
                  ? `${m.display_name} — ${m.name}${suffix}`
                  : `${m.name}${suffix}`;
              opts.push({
                label: displayLabel,
                value: m.name,
                group: "Available Models",
              });
            });
          }

          return opts;
        },
        placeholder: t("admin.pages.models.formFields.modelTemplatePlaceholder"),
        help: t("admin.pages.models.formFields.modelTemplateHelp"),
      },
      {
        name: "name",
        label: t("admin.pages.models.formFields.modelName"),
        type: "text",
        required: true,
        placeholder: t("admin.pages.models.formFields.modelNamePlaceholder"),
      },
      {
        name: "display_name",
        label: t("admin.pages.models.formFields.displayName"),
        type: "text",
        required: true,
        placeholder: t("admin.pages.models.formFields.displayNamePlaceholder"),
      },
      {
        name: "description",
        label: t("admin.pages.models.formFields.description"),
        type: "textarea",
        placeholder: t("admin.pages.models.formFields.descriptionPlaceholder"),
      },
      {
        name: "capabilities",
        label: t("admin.pages.models.formFields.capabilities"),
        type: "multiselect",
        required: true,
        options: capabilityOptions.value,
        placeholder: t("admin.pages.models.formFields.capabilitiesPlaceholder"),
        help: t("admin.pages.models.formFields.capabilitiesHelp"),
      },
      {
        name: "generation_config",
        label: t("admin.pages.models.formFields.generationConfig"),
        type: "json",
        placeholder: t("admin.pages.models.formFields.generationConfigPlaceholder"),
        help: t("admin.pages.models.formFields.generationConfigHelp"),
        defaultValue: {},
      },
      {
        name: "max_context_tokens",
        label: t("admin.pages.models.formFields.maxContextTokens"),
        type: "number",
        placeholder: t("admin.pages.models.formFields.maxContextTokensPlaceholder"),
        help: t("admin.pages.models.formFields.maxContextTokensHelp"),
      },
      {
        name: "max_output_tokens",
        label: t("admin.pages.models.formFields.maxOutputTokens"),
        type: "number",
        placeholder: t("admin.pages.models.formFields.maxOutputTokensPlaceholder"),
        help: t("admin.pages.models.formFields.maxOutputTokensHelp"),
      },
      {
        name: "status",
        label: t("admin.pages.models.formFields.status"),
        type: "select",
        required: true,
        options: [
          {
            label: t("admin.pages.models.formFields.statusActive"),
            value: "ACTIVE",
          },
          {
            label: t("admin.pages.models.formFields.statusInactive"),
            value: "INACTIVE",
          },
          {
            label: t("admin.pages.models.formFields.statusUnavailable"),
            value: "UNAVAILABLE",
          },
          {
            label: t("admin.pages.models.formFields.statusDeprecated"),
            value: "DEPRECATED",
          },
        ],
        defaultValue: "ACTIVE",
      },
    ],
  })
);
</script>

<template>
  <ModelView :config="providerConfig">
    <template #actions>
      <!-- Optional: Add discover models button in the header if needed -->
    </template>
  </ModelView>

  <AlertDialog v-model:open="hfDownloadPromptOpen">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>{{ t("admin.pages.models.hf.downloadTitle") }}</AlertDialogTitle>
        <AlertDialogDescription>
          {{
            t("admin.pages.models.hf.downloadDescription", {
              repo: hfDownloadRepoId || "",
            })
          }}
        </AlertDialogDescription>
      </AlertDialogHeader>

      <AlertDialogFooter>
        <AlertDialogCancel>{{ t("common.cancel") }}</AlertDialogCancel>
        <AlertDialogAction @click="handleHfDownloadConfirm">
          {{ t("admin.pages.models.hf.downloadAction") }}
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
