<script setup lang="ts">
import { computed, h, ref } from "vue";
import { Badge } from "~/components/ui/badge";
import { PlugZap, Search, Copy } from "lucide-vue-next";
import { toast } from "vue-sonner";
import type { ModelViewConfig } from "~/components/model-view/ModelView.vue";
import type { Provider } from "~/types/api";

const { t } = useI18n();
const { $api } = useNuxtApp();

definePageMeta({
  breadcrumb: "admin.pages.modelProviders.breadcrumb",
  layout: "admin",
});

type ProviderTemplate = {
  id: string;
  display_name: string;
  description?: string;
  docs_url?: string;
  default_base_url: string;
  category: string;
};

type ProvidersByCategory = {
  OPENAI_COMPATIBLE: ProviderTemplate[];
  PROVIDER_SPECIFIC: ProviderTemplate[];
  CUSTOM: ProviderTemplate[];
  LOCAL: ProviderTemplate[];
};

const { data: providersByCategory, pending: loadingTemplates } = useAPI<ProvidersByCategory>(
  "/v1/admin/litellm-providers/by-category",
  {
    server: false,
    lazy: true,
  }
);

const providerTemplates = computed(() => {
  if (!providersByCategory.value) return [];
  const all: ProviderTemplate[] = [];
  Object.values(providersByCategory.value).forEach((providers) => {
    all.push(...providers);
  });
  return all;
});

const providerTemplateMap = computed(() => {
  const map: Record<string, ProviderTemplate> = {};
  providerTemplates.value.forEach((p) => {
    map[p.id] = p;
  });
  return map;
});

const providerTemplateOptions = computed(() => {
  if (!providersByCategory.value) return [];

  const options: { label: string; value: string; group?: string }[] = [];

  // Add OpenAI-compatible providers at the top
  if (providersByCategory.value.OPENAI_COMPATIBLE?.length > 0) {
    providersByCategory.value.OPENAI_COMPATIBLE.forEach((p) => {
      options.push({
        label: p.display_name,
        value: p.id,
        group: "OpenAI Compatible",
      });
    });
  }

  // Add custom endpoint option
  if (providersByCategory.value.CUSTOM?.length > 0) {
    providersByCategory.value.CUSTOM.forEach((p) => {
      options.push({
        label: p.display_name,
        value: p.id,
        group: "Custom Endpoint",
      });
    });
  }

  // Add other providers (provider-specific and local)
  if (providersByCategory.value.PROVIDER_SPECIFIC?.length > 0) {
    providersByCategory.value.PROVIDER_SPECIFIC.forEach((p) => {
      options.push({
        label: p.display_name,
        value: p.id,
        group: "Other Providers",
      });
    });
  }

  if (providersByCategory.value.LOCAL?.length > 0) {
    providersByCategory.value.LOCAL.forEach((p) => {
      options.push({
        label: p.display_name,
        value: p.id,
        group: "Other Providers",
      });
    });
  }

  return options;
});

const lastAppliedTemplateId = ref<string | null>(null);

const handleProviderRowAction = async (action: any, row: Provider) => {
  try {
    if (action.key === "test-connection") {
      const res = await $api(`/v1/admin/providers/${row.id}/test-connection`, {
        method: "POST",
      });
      if (res?.ok) {
        toast.success(res.message || t("admin.pages.modelProviders.actions.testConnectionSuccess"));
      } else {
        // Display the error message from backend
        const errorMsg =
          res?.message ||
          res?.detail ||
          t("admin.pages.modelProviders.actions.testConnectionFailed");
        toast.error(errorMsg);
      }
      return;
    }

    if (action.key === "discover-models-quick") {
      const models = await $api<string[]>(
        `/v1/admin/providers/${row.id}/discover-models?method=quick`,
        { method: "GET" }
      );
      toast.success(`Found ${models?.length || 0} models (quick scan)`);
      return;
    }

    if (action.key === "discover-models-comprehensive") {
      toast.info("Discovering models... This may take a moment.");
      const models = await $api<string[]>(
        `/v1/admin/providers/${row.id}/discover-models?method=comprehensive`,
        { method: "GET" }
      );
      toast.success(`Found ${models?.length || 0} models (comprehensive scan)`);
      return;
    }

    // Fallback for old discover-models action
    if (action.key === "discover-models") {
      const models = await $api<string[]>(`/v1/admin/providers/${row.id}/discover-models`, {
        method: "GET",
      });
      toast.success(
        t("admin.pages.modelProviders.actions.discoverModelsSuccess", {
          count: (models ?? []).length,
        })
      );
      return;
    }
  } catch (e: any) {
    toast.error(e?.data?.detail || e?.message || t("common.error"));
  }
};

// Provider configuration
const providerConfig = computed(
  (): ModelViewConfig<Provider> => ({
    title: t("admin.pages.modelProviders.title"),
    description: t("admin.pages.modelProviders.description"),
    apiEndpoint: "/v1/admin/providers",
    onFormChange: ({ formData, mode, setValues }) => {
      if (mode !== "create") return;
      const tplId = (formData?.template_id as string) || "";
      if (!tplId) {
        lastAppliedTemplateId.value = null;
        return;
      }
      if (tplId === lastAppliedTemplateId.value) return;
      const tpl = providerTemplateMap.value[tplId];
      if (!tpl || !setValues) return;

      // Determine is_openai_compatible based on category
      const isOpenAICompatible = tpl.category === "OPENAI_COMPATIBLE" || tpl.category === "CUSTOM";

      setValues({
        template_id: tpl.id,
        name: tpl.id,
        display_name: tpl.display_name,
        description: tpl.description ?? "",
        website: tpl.docs_url ?? "",
        api_base_url: tpl.default_base_url,
        category: tpl.category,
        is_openai_compatible: isOpenAICompatible,
        litellm_provider: tpl.id,
      });
      lastAppliedTemplateId.value = tplId;
    },
    customActions: [
      {
        key: "test-connection",
        label: t("admin.pages.modelProviders.actions.testConnection"),
        icon: h(PlugZap, { class: "h-4 w-4" }),
        variant: "default" as const,
      },
      {
        key: "discover-models-quick",
        label: "Discover Models (Quick)",
        icon: h(Search, { class: "h-4 w-4" }),
        variant: "secondary" as const,
        visible: (row: any) =>
          row.category === "OPENAI_COMPATIBLE" ||
          (row.category === "CUSTOM" && row.is_openai_compatible),
      },
      {
        key: "discover-models-comprehensive",
        label: "Discover Models (Comprehensive)",
        icon: h(Search, { class: "h-4 w-4" }),
        variant: "outline" as const,
      },
    ],

    columns: [
      {
        accessorKey: "display_name",
        header: t("admin.pages.modelProviders.columns.displayName"),
        cell: (ctx) => {
          const value = ctx.getValue() as string;
          if (!value) return "-";
          return h(
            "button",
            {
              class:
                "text-primary font-medium cursor-pointer text-left focus:outline-none focus:ring-2 focus:ring-primary/40 rounded-full bg-muted/30 hover:bg-muted/60 hover:underline px-2 py-0.5 transition-colors",
              onClick: () =>
                ctx.table.options.meta?.triggerRowAction?.(
                  { key: "view", label: "view" },
                  ctx.row.original
                ),
            },
            value
          );
        },
      },
      {
        accessorKey: "category",
        header: "Category",
        cell: (context) => {
          const value = context.getValue() as string;
          const variants: Record<string, any> = {
            OPENAI_COMPATIBLE: "default",
            PROVIDER_SPECIFIC: "secondary",
            CUSTOM: "outline",
            LOCAL: "ghost",
          };
          const labels: Record<string, string> = {
            OPENAI_COMPATIBLE: "OpenAI-Compatible",
            PROVIDER_SPECIFIC: "Provider-Specific",
            CUSTOM: "Custom",
            LOCAL: "Local",
          };
          return h(Badge, { variant: variants[value] || "outline" }, () => labels[value] || value);
        },
      },
      {
        accessorKey: "api_base_url",
        header: t("admin.pages.modelProviders.fields.apiBaseUrl"),
        cell: (context) => {
          const value = context.getValue() as string;
          if (!value) return "-";
          return h("div", { class: "flex items-center gap-2" }, [
            h(
              "span",
              { class: "truncate max-w-[200px]", title: value },
              value.length > 30 ? `${value.substring(0, 30)}...` : value
            ),
            h(
              "button",
              {
                class:
                  "text-muted-foreground hover:text-foreground p-1 rounded hover:bg-muted transition-colors",
                title: t("common.copy"),
                onClick: (e: Event) => {
                  e.stopPropagation();
                  navigator.clipboard.writeText(value);
                  toast.success(t("common.copied"));
                },
              },
              h(Copy, { class: "h-3 w-3" })
            ),
          ]);
        },
      },
      {
        accessorKey: "status",
        header: t("admin.pages.modelProviders.columns.status"),
        cell: (context) => {
          const value = context.getValue() as string;
          // Based on status
          const variant =
            value === "ACTIVE" ? "default" : value === "MAINTENANCE" ? "outline" : "secondary";
          const statusKey =
            value === "ACTIVE" ? "active" : value === "MAINTENANCE" ? "maintenance" : "inactive";
          return h(Badge, { variant }, () => t(`admin.pages.modelProviders.status.${statusKey}`));
        },
      },
      {
        accessorKey: "created_at",
        header: t("admin.pages.modelProviders.columns.createdAt"),
        cell: (context) => {
          const value = context.getValue() as string;
          return new Date(value).toLocaleDateString();
        },
      },
    ],

    detailFields: [
      {
        name: "name",
        label: t("admin.pages.modelProviders.fields.providerId"),
        type: "text",
      },
      {
        name: "display_name",
        label: t("admin.pages.modelProviders.fields.displayName"),
        type: "text",
      },
      {
        name: "category",
        label: "Category",
        type: "text",
      },
      {
        name: "description",
        label: t("admin.pages.modelProviders.fields.description"),
        type: "textarea",
      },
      {
        name: "website",
        label: t("admin.pages.modelProviders.fields.website"),
        type: "text",
      },
      {
        name: "api_base_url",
        label: t("admin.pages.modelProviders.fields.apiBaseUrl"),
        type: "text",
      },
      {
        name: "litellm_provider",
        label: t("admin.pages.modelProviders.fields.litellmProvider"),
        type: "text",
      },
      {
        name: "is_openai_compatible",
        label: "OpenAI-Compatible",
        type: "text",
      },
      {
        name: "status",
        label: t("admin.pages.modelProviders.fields.statusLabel"),
        type: "text",
      },
      {
        name: "created_at",
        label: t("admin.pages.modelProviders.columns.createdAt"),
        type: "datetime",
      },
    ],

    formFields: [
      {
        name: "template_id",
        label: t("admin.pages.modelProviders.fields.providerTemplate"),
        type: "select",
        required: false,
        options: providerTemplateOptions.value,
        placeholder: t("admin.pages.modelProviders.fields.providerTemplatePlaceholder"),
        help: t("admin.pages.modelProviders.fields.providerTemplateHelp"),
      },
      {
        name: "name",
        label: t("admin.pages.modelProviders.fields.providerId"),
        type: "text",
        required: true,
        placeholder: t("admin.pages.modelProviders.fields.providerIdPlaceholder"),
        htmlName: "provider_id",
        autocomplete: "off",
      },
      {
        name: "display_name",
        label: t("admin.pages.modelProviders.fields.displayName"),
        type: "text",
        required: true,
        placeholder: t("admin.pages.modelProviders.fields.displayNamePlaceholder"),
      },
      {
        name: "description",
        label: t("admin.pages.modelProviders.fields.description"),
        type: "textarea",
        placeholder: t("admin.pages.modelProviders.fields.descriptionPlaceholder"),
      },
      {
        name: "website",
        label: t("admin.pages.modelProviders.fields.website"),
        type: "text",
        placeholder: "https://example.com",
      },
      {
        name: "api_base_url",
        label: t("admin.pages.modelProviders.fields.apiBaseUrl"),
        type: "text",
        placeholder: "https://api.example.com/v1",
      },
      {
        name: "api_key",
        label: t("admin.pages.modelProviders.fields.apiKey"),
        type: "password",
        required: false,
        placeholder: t("admin.pages.modelProviders.fields.apiKeyPlaceholder"),
        help: `${t(
          "admin.pages.modelProviders.fields.apiKeyPlaceholder"
        )} (not required for local HuggingFace embeddings)`,
        htmlName: "provider_api_key",
        autocomplete: "new-password",
      },
      {
        name: "category",
        label: "Provider Category",
        type: "select",
        required: true,
        options: [
          { label: "OpenAI-Compatible", value: "OPENAI_COMPATIBLE" },
          { label: "Provider-Specific", value: "PROVIDER_SPECIFIC" },
          { label: "Custom", value: "CUSTOM" },
          { label: "Local", value: "LOCAL" },
        ],
        defaultValue: "PROVIDER_SPECIFIC",
        help: "Choose the provider type for proper integration",
      },
      {
        name: "is_openai_compatible",
        label: "OpenAI-Compatible",
        type: "checkbox",
        required: false,
        help: "Check if your custom endpoint follows OpenAI API format (only for CUSTOM category)",
      },
      {
        name: "litellm_provider",
        label: t("admin.pages.modelProviders.fields.litellmProvider"),
        type: "text",
        required: true,
        placeholder: "e.g., groq, anthropic, gemini, openai",
        help: "LiteLLM provider identifier for routing",
      },
      {
        name: "status",
        label: t("admin.pages.modelProviders.fields.statusLabel"),
        type: "select",
        required: true,
        options: [
          { label: t("admin.pages.modelProviders.status.active"), value: "ACTIVE" },
          { label: t("admin.pages.modelProviders.status.inactive"), value: "INACTIVE" },
          { label: t("admin.pages.modelProviders.status.maintenance"), value: "MAINTENANCE" },
        ],
        defaultValue: "ACTIVE",
      },
    ],
  })
);
</script>

<template>
  <!-- Show loading spinner while templates are loading -->
  <div v-if="loadingTemplates" class="flex h-[60vh] items-center justify-center">
    <div class="flex flex-col items-center gap-4">
      <div class="border-primary h-12 w-12 animate-spin rounded-full border-b-2"></div>
      <p class="text-muted-foreground text-sm">Loading provider templates...</p>
    </div>
  </div>

  <!-- Show ModelView once templates are loaded -->
  <ModelView v-else :config="providerConfig" @row-action="handleProviderRowAction" />
</template>
