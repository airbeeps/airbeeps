<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { Textarea } from "~/components/ui/textarea";
import { Checkbox } from "~/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "~/components/ui/collapsible";
import {
  Plus,
  Trash2,
  Edit,
  Upload,
  Eye,
  Star,
  ArrowLeft,
  RefreshCw,
  Save,
  ChevronDown,
  FileSpreadsheet,
  Info,
} from "lucide-vue-next";
import { toast } from "vue-sonner";

const { $api } = useNuxtApp();
const { t } = useI18n();

// Get route parameters
const route = useRoute();
const router = useRouter();
const kbId = route.params.id as string;

// Page metadata
definePageMeta({
  breadcrumb: "Ingestion Profiles",
  layout: "admin",
});

// Types
interface ColumnConfig {
  name: string;
  type: string;
  aliases: string[];
}

interface RowTemplate {
  format: string;
  include_labels: boolean;
  omit_empty: boolean;
  field_order: string[] | null;
  custom_template: string | null;
}

interface ProfileConfig {
  columns: ColumnConfig[];
  metadata_fields: Record<string, string>;
  content_fields: string[];
  required_fields: string[];
  validation_mode: string;
  row_template: RowTemplate;
}

interface IngestionProfile {
  id: string;
  knowledge_base_id: string | null;
  owner_id: string;
  name: string;
  description: string | null;
  file_types: string[];
  is_default: boolean;
  is_builtin: boolean;
  config: ProfileConfig;
  status: string;
  created_at: string;
  updated_at: string;
}

interface InferredColumn {
  name: string;
  inferred_type: string;
  sample_values: any[];
  non_null_count: number;
  suggested_metadata_key: string | null;
}

const normalizeKey = (colName: string) =>
  colName
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");

// State
const loading = ref(false);
const profiles = ref<IngestionProfile[]>([]);
const showCreateDialog = ref(false);
const showEditDialog = ref(false);
const showInferDialog = ref(false);
const showPreviewDialog = ref(false);
const showBuiltinProfiles = ref(false);
const selectedProfile = ref<IngestionProfile | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const inferredColumns = ref<InferredColumn[]>([]);
const inferredRowCount = ref(0);
const previewText = ref("");
const previewMetadata = ref<Record<string, any>>({});

// Form state
const formData = ref({
  name: "",
  description: "",
  file_types: ["csv", "xlsx"],
  is_default: false,
  config: {
    columns: [] as ColumnConfig[],
    metadata_fields: {} as Record<string, string>,
    content_fields: [] as string[],
    required_fields: [] as string[],
    validation_mode: "warn",
    row_template: {
      format: "key_value",
      include_labels: true,
      omit_empty: true,
      field_order: null as string[] | null,
      custom_template: null as string | null,
    },
  },
});

const inferredByName = computed(() => {
  const map = new Map<string, InferredColumn>();
  inferredColumns.value.forEach((c) => map.set(c.name, c));
  return map;
});

const ensureColumnsFromMappings = () => {
  if (formData.value.config.columns.length > 0) return;
  const names = new Set<string>([
    ...Object.keys(formData.value.config.metadata_fields || {}),
    ...(formData.value.config.content_fields || []),
    ...(formData.value.config.required_fields || []),
  ]);
  formData.value.config.columns = Array.from(names)
    .sort((a, b) => a.localeCompare(b))
    .map((name) => ({ name, type: "string", aliases: [] }));
};

const addColumnPrompt = () => {
  const name = window.prompt("Column name");
  if (!name) return;
  const trimmed = name.trim();
  if (!trimmed) return;
  if (formData.value.config.columns.some((c) => c.name === trimmed)) {
    toast.error("Column already exists");
    return;
  }
  formData.value.config.columns.push({ name: trimmed, type: "string", aliases: [] });
  if (!formData.value.config.content_fields.includes(trimmed)) {
    formData.value.config.content_fields.push(trimmed);
  }
};

const removeColumn = (colName: string) => {
  formData.value.config.columns = formData.value.config.columns.filter((c) => c.name !== colName);
  const meta = { ...(formData.value.config.metadata_fields || {}) };
  delete meta[colName];
  formData.value.config.metadata_fields = meta;
  formData.value.config.content_fields = (formData.value.config.content_fields || []).filter(
    (c) => c !== colName
  );
  formData.value.config.required_fields = (formData.value.config.required_fields || []).filter(
    (c) => c !== colName
  );
  const order = formData.value.config.row_template.field_order || null;
  if (order) {
    const next = order.filter((c) => c !== colName);
    formData.value.config.row_template.field_order = next.length ? next : null;
  }
};

const setContentField = (colName: string, include: boolean) => {
  const set = new Set(formData.value.config.content_fields || []);
  if (include) set.add(colName);
  else set.delete(colName);
  formData.value.config.content_fields = Array.from(set);
};

const setMetadataField = (colName: string, include: boolean) => {
  const meta = { ...(formData.value.config.metadata_fields || {}) };
  if (include) {
    if (!meta[colName]) meta[colName] = normalizeKey(colName);
  } else {
    delete meta[colName];
  }
  formData.value.config.metadata_fields = meta;
};

const setMetadataKey = (colName: string, key: string) => {
  const meta = { ...(formData.value.config.metadata_fields || {}) };
  meta[colName] = key;
  formData.value.config.metadata_fields = meta;
};

const setRequiredField = (colName: string, required: boolean) => {
  const set = new Set(formData.value.config.required_fields || []);
  if (required) set.add(colName);
  else set.delete(colName);
  formData.value.config.required_fields = Array.from(set);
};

const getAliasesString = (col: ColumnConfig) => (col.aliases || []).join(", ");
const setAliasesString = (col: ColumnConfig, value: string) => {
  col.aliases = value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
};

const fieldOrderText = computed({
  get: () => (formData.value.config.row_template.field_order || []).join("\n"),
  set: (val: string) => {
    const lines = val
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    formData.value.config.row_template.field_order = lines.length ? lines : null;
  },
});

// Computed
const kbProfiles = computed(() =>
  profiles.value.filter((p) => p.knowledge_base_id === kbId && !p.is_builtin)
);

const builtinProfiles = computed(() => profiles.value.filter((p) => p.is_builtin));

// Load profiles
const loadProfiles = async () => {
  loading.value = true;
  try {
    const response = await $api(`/v1/admin/rag/knowledge-bases/${kbId}/ingestion-profiles`);
    profiles.value = response as IngestionProfile[];
  } catch (error) {
    console.error("Failed to load profiles:", error);
    toast.error("Failed to load ingestion profiles");
  } finally {
    loading.value = false;
  }
};

// Create profile
const createProfile = async () => {
  try {
    ensureColumnsFromMappings();
    await $api(`/v1/admin/rag/knowledge-bases/${kbId}/ingestion-profiles`, {
      method: "POST",
      body: JSON.stringify(formData.value),
    });
    toast.success("Profile created successfully");
    showCreateDialog.value = false;
    resetForm();
    await loadProfiles();
  } catch (error) {
    console.error("Failed to create profile:", error);
    toast.error("Failed to create profile");
  }
};

// Update profile
const updateProfile = async () => {
  if (!selectedProfile.value) return;

  try {
    ensureColumnsFromMappings();
    await $api(`/v1/admin/rag/ingestion-profiles/${selectedProfile.value.id}`, {
      method: "PUT",
      body: JSON.stringify(formData.value),
    });
    toast.success("Profile updated successfully");
    showEditDialog.value = false;
    resetForm();
    await loadProfiles();
  } catch (error) {
    console.error("Failed to update profile:", error);
    toast.error("Failed to update profile");
  }
};

// Delete profile
const deleteProfile = async (profile: IngestionProfile) => {
  if (!confirm(`Delete profile "${profile.name}"?`)) return;

  try {
    await $api(`/v1/admin/rag/ingestion-profiles/${profile.id}`, {
      method: "DELETE",
    });
    toast.success("Profile deleted successfully");
    await loadProfiles();
  } catch (error) {
    console.error("Failed to delete profile:", error);
    toast.error("Failed to delete profile");
  }
};

// Set as default
const setAsDefault = async (profile: IngestionProfile) => {
  try {
    await $api(`/v1/admin/rag/ingestion-profiles/${profile.id}`, {
      method: "PUT",
      body: JSON.stringify({ is_default: true }),
    });
    toast.success(`"${profile.name}" set as default`);
    await loadProfiles();
  } catch (error) {
    console.error("Failed to set default:", error);
    toast.error("Failed to set default profile");
  }
};

// Open edit dialog
const openEditDialog = (profile: IngestionProfile) => {
  selectedProfile.value = profile;
  formData.value = {
    name: profile.name,
    description: profile.description || "",
    file_types: profile.file_types,
    is_default: profile.is_default,
    config: {
      columns: profile.config.columns || [],
      metadata_fields: profile.config.metadata_fields || {},
      content_fields: profile.config.content_fields || [],
      required_fields: profile.config.required_fields || [],
      validation_mode: profile.config.validation_mode || "warn",
      row_template: {
        format: profile.config.row_template?.format || "key_value",
        include_labels: profile.config.row_template?.include_labels ?? true,
        omit_empty: profile.config.row_template?.omit_empty ?? true,
        field_order: profile.config.row_template?.field_order || null,
        custom_template: profile.config.row_template?.custom_template || null,
      },
    },
  };

  ensureColumnsFromMappings();
  showEditDialog.value = true;
};

// Reset form
const resetForm = () => {
  formData.value = {
    name: "",
    description: "",
    file_types: ["csv", "xlsx"],
    is_default: false,
    config: {
      columns: [],
      metadata_fields: {},
      content_fields: [],
      required_fields: [],
      validation_mode: "warn",
      row_template: {
        format: "key_value",
        include_labels: true,
        omit_empty: true,
        field_order: null,
        custom_template: null,
      },
    },
  };
  selectedProfile.value = null;
  inferredColumns.value = [];
  inferredRowCount.value = 0;
};

// Infer from file
const handleInferFile = async (event: Event) => {
  const target = event.target as HTMLInputElement;
  if (!target.files?.length) return;

  const file = target.files[0];
  const formDataUpload = new FormData();
  formDataUpload.append("file", file);

  try {
    loading.value = true;
    const response: any = await $api("/v1/admin/rag/ingestion-profiles/infer-from-upload", {
      method: "POST",
      body: formDataUpload,
    });

    inferredColumns.value = response.columns;
    inferredRowCount.value = response.row_count;

    const existing = new Map(formData.value.config.columns.map((c) => [c.name, c]));
    formData.value.config.columns = (response.columns || []).map((c: InferredColumn) => {
      const prev = existing.get(c.name);
      return {
        name: c.name,
        type: prev?.type || c.inferred_type || "string",
        aliases: prev?.aliases || [],
      };
    });

    const hasMappings =
      Object.keys(formData.value.config.metadata_fields || {}).length > 0 ||
      (formData.value.config.content_fields || []).length > 0;
    if (!hasMappings && response.suggested_profile) {
      formData.value.config.metadata_fields = response.suggested_profile.metadata_fields || {};
      formData.value.config.content_fields = (response.columns || []).map(
        (c: InferredColumn) => c.name
      );
    }

    showInferDialog.value = true;
  } catch (error) {
    console.error("Failed to infer profile:", error);
    toast.error("Failed to analyze file");
  } finally {
    loading.value = false;
    target.value = "";
  }
};

// Apply inferred columns
const applyInferredColumns = () => {
  const metadataFields: Record<string, string> = {};

  inferredColumns.value.forEach((col) => {
    if (col.suggested_metadata_key) {
      metadataFields[col.name] = col.suggested_metadata_key;
    }
  });

  formData.value.config.metadata_fields = metadataFields;
  formData.value.config.content_fields = inferredColumns.value.map((c) => c.name);

  showInferDialog.value = false;
  toast.success("Column mappings applied");
};

// Preview row render
const previewRowRender = async () => {
  const sampleRow: Record<string, any> = {};
  ensureColumnsFromMappings();
  formData.value.config.columns.forEach((col) => {
    const inferred = inferredByName.value.get(col.name);
    sampleRow[col.name] = inferred?.sample_values?.[0] ?? "";
  });

  try {
    const response: any = await $api("/v1/admin/rag/ingestion-profiles/preview-row-render", {
      method: "POST",
      body: JSON.stringify({
        profile_config: formData.value.config,
        row_data: sampleRow,
      }),
    });

    previewText.value = response.row_text;
    previewMetadata.value = response.extracted_metadata;
    showPreviewDialog.value = true;
  } catch (error) {
    console.error("Failed to preview:", error);
    toast.error("Failed to generate preview");
  }
};

// Lifecycle
onMounted(() => {
  loadProfiles();
});
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-4">
        <Button variant="ghost" size="icon" @click="router.push(`/admin/kbs/${kbId}`)">
          <ArrowLeft class="h-5 w-5" />
        </Button>
        <div>
          <h1 class="text-2xl font-bold">Ingestion Profiles</h1>
          <p class="text-muted-foreground text-sm">
            Configure how CSV/Excel files are processed into searchable chunks
          </p>
        </div>
      </div>
      <div class="flex gap-2">
        <Button variant="outline" @click="loadProfiles" :disabled="loading">
          <RefreshCw class="mr-2 h-4 w-4" :class="{ 'animate-spin': loading }" />
          Refresh
        </Button>
        <Button @click="showCreateDialog = true">
          <Plus class="mr-2 h-4 w-4" />
          Create Profile
        </Button>
      </div>
    </div>

    <!-- Info Card -->
    <Card class="bg-muted/30 border-muted">
      <CardContent class="flex items-start gap-3 py-4">
        <Info class="text-muted-foreground mt-0.5 h-5 w-5 shrink-0" />
        <div class="text-sm">
          <p>
            <strong>Ingestion profiles</strong> define how structured files (CSV, Excel) are
            converted into searchable text chunks. Each profile specifies:
          </p>
          <ul class="text-muted-foreground mt-1 list-inside list-disc">
            <li>Which columns become searchable content</li>
            <li>Which columns become filterable metadata</li>
            <li>How each row is formatted as text</li>
          </ul>
        </div>
      </CardContent>
    </Card>

    <!-- Custom Profiles -->
    <Card>
      <CardHeader>
        <CardTitle class="flex items-center gap-2">
          <FileSpreadsheet class="h-5 w-5" />
          Your Profiles
        </CardTitle>
        <CardDescription> Custom profiles for this knowledge base </CardDescription>
      </CardHeader>
      <CardContent>
        <div v-if="kbProfiles.length === 0" class="py-8 text-center">
          <FileSpreadsheet class="text-muted-foreground mx-auto h-12 w-12 opacity-50" />
          <p class="text-muted-foreground mt-2">No custom profiles yet</p>
          <p class="text-muted-foreground mt-1 text-sm">
            Create a profile to customize how CSV/Excel files are processed
          </p>
          <Button class="mt-4" @click="showCreateDialog = true">
            <Plus class="mr-2 h-4 w-4" />
            Create Profile
          </Button>
        </div>
        <Table v-else>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>File Types</TableHead>
              <TableHead>Fields</TableHead>
              <TableHead>Default</TableHead>
              <TableHead class="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="profile in kbProfiles" :key="profile.id">
              <TableCell>
                <div class="font-medium">{{ profile.name }}</div>
                <div
                  v-if="profile.description"
                  class="text-muted-foreground max-w-xs truncate text-xs"
                >
                  {{ profile.description }}
                </div>
              </TableCell>
              <TableCell>
                <div class="flex gap-1">
                  <Badge v-for="ft in profile.file_types" :key="ft" variant="secondary">
                    {{ ft }}
                  </Badge>
                </div>
              </TableCell>
              <TableCell>
                <span class="text-muted-foreground">
                  {{ Object.keys(profile.config.metadata_fields || {}).length }} metadata,
                  {{ (profile.config.content_fields || []).length }} content
                </span>
              </TableCell>
              <TableCell>
                <Badge v-if="profile.is_default" variant="default">
                  <Star class="mr-1 h-3 w-3" />
                  Default
                </Badge>
                <Button v-else variant="ghost" size="sm" @click="setAsDefault(profile)">
                  Set default
                </Button>
              </TableCell>
              <TableCell class="text-right">
                <div class="flex justify-end gap-1">
                  <Button variant="ghost" size="icon" @click="openEditDialog(profile)">
                    <Edit class="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" @click="deleteProfile(profile)">
                    <Trash2 class="h-4 w-4" />
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </CardContent>
    </Card>

    <!-- Built-in Templates (Collapsible) -->
    <Collapsible v-if="builtinProfiles.length > 0" v-model:open="showBuiltinProfiles">
      <Card>
        <CardHeader class="py-3">
          <CollapsibleTrigger asChild>
            <Button variant="ghost" class="w-full justify-between px-0 hover:bg-transparent">
              <div class="flex items-center gap-2">
                <CardTitle class="text-sm font-medium"> Built-in Templates </CardTitle>
                <Badge variant="outline" class="text-xs">{{ builtinProfiles.length }}</Badge>
              </div>
              <ChevronDown
                class="text-muted-foreground h-4 w-4 transition-transform"
                :class="{ 'rotate-180': showBuiltinProfiles }"
              />
            </Button>
          </CollapsibleTrigger>
          <CardDescription class="mt-0">
            Pre-configured templates for common data formats (read-only)
          </CardDescription>
        </CardHeader>
        <CollapsibleContent>
          <CardContent class="pt-0">
            <div class="divide-y">
              <div
                v-for="profile in builtinProfiles"
                :key="profile.id"
                class="flex items-center justify-between py-3 first:pt-0 last:pb-0"
              >
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <span class="font-medium">{{ profile.name }}</span>
                    <Badge variant="secondary" class="text-xs">Built-in</Badge>
                  </div>
                  <p v-if="profile.description" class="text-muted-foreground mt-0.5 text-xs">
                    {{ profile.description }}
                  </p>
                </div>
                <div class="flex items-center gap-2">
                  <div class="flex gap-1">
                    <Badge
                      v-for="ft in profile.file_types"
                      :key="ft"
                      variant="outline"
                      class="text-xs"
                    >
                      {{ ft }}
                    </Badge>
                  </div>
                  <span class="text-muted-foreground text-xs">
                    {{ Object.keys(profile.config.metadata_fields || {}).length }} fields
                  </span>
                </div>
              </div>
            </div>
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>

    <!-- Create/Edit Dialog -->
    <Dialog
      :open="showCreateDialog || showEditDialog"
      @update:open="
        (v) => {
          showCreateDialog = v;
          showEditDialog = v;
          if (!v) resetForm();
        }
      "
    >
      <DialogContent class="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {{ selectedProfile ? "Edit Profile" : "Create Profile" }}
          </DialogTitle>
          <DialogDescription>
            Configure column mappings and row rendering for structured files
          </DialogDescription>
        </DialogHeader>

        <div class="space-y-6 py-4">
          <!-- Basic Info -->
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="space-y-2">
              <Label for="name">Profile Name</Label>
              <Input id="name" v-model="formData.name" placeholder="e.g., Customer Feedback" />
            </div>
            <div class="space-y-2">
              <Label for="validation">Validation Mode</Label>
              <Select v-model="formData.config.validation_mode">
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="warn">Warn (log issues)</SelectItem>
                  <SelectItem value="skip">Skip (skip invalid rows)</SelectItem>
                  <SelectItem value="fail">Fail (stop on first error)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div class="space-y-2">
            <Label for="description">Description</Label>
            <Textarea
              id="description"
              v-model="formData.description"
              placeholder="Describe what data this profile is designed for..."
            />
          </div>

          <!-- Infer from File -->
          <div class="bg-muted/30 rounded-lg border p-4">
            <div class="flex items-center justify-between">
              <div>
                <h4 class="font-medium">Auto-detect Columns</h4>
                <p class="text-muted-foreground text-sm">
                  Upload a sample file to automatically detect columns
                </p>
              </div>
              <div>
                <input
                  ref="fileInput"
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  class="hidden"
                  @change="handleInferFile"
                />
                <Button variant="outline" @click="fileInput?.click()" :disabled="loading">
                  <Upload class="mr-2 h-4 w-4" />
                  Upload Sample
                </Button>
              </div>
            </div>
          </div>

          <!-- Column Mapping -->
          <div class="space-y-3">
            <div class="flex items-center justify-between">
              <Label>Column Mappings</Label>
              <div class="flex gap-2">
                <Button variant="outline" size="sm" @click="addColumnPrompt">
                  <Plus class="mr-2 h-4 w-4" />
                  Add column
                </Button>
                <Button
                  v-if="formData.config.columns.length > 0"
                  variant="outline"
                  size="sm"
                  @click="previewRowRender"
                >
                  <Eye class="mr-2 h-4 w-4" />
                  Preview
                </Button>
              </div>
            </div>

            <div
              v-if="formData.config.columns.length === 0"
              class="text-muted-foreground rounded-lg border border-dashed p-6 text-center text-sm"
            >
              Upload a sample file to auto-detect columns, or add them manually.
            </div>

            <div v-else class="overflow-hidden rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Column</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Aliases</TableHead>
                    <TableHead class="text-center">Content</TableHead>
                    <TableHead>Metadata</TableHead>
                    <TableHead class="text-center">Required</TableHead>
                    <TableHead class="w-10"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow v-for="col in formData.config.columns" :key="col.name">
                    <TableCell class="font-medium">{{ col.name }}</TableCell>
                    <TableCell>
                      <Select v-model="col.type">
                        <SelectTrigger class="h-8 w-24">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="string">string</SelectItem>
                          <SelectItem value="number">number</SelectItem>
                          <SelectItem value="date">date</SelectItem>
                          <SelectItem value="boolean">boolean</SelectItem>
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Input
                        class="h-8"
                        :model-value="getAliasesString(col)"
                        @update:model-value="(v: any) => setAliasesString(col, String(v))"
                        placeholder="alt_name, AltName"
                      />
                    </TableCell>
                    <TableCell class="text-center">
                      <Checkbox
                        :checked="formData.config.content_fields.includes(col.name)"
                        @update:checked="(v: any) => setContentField(col.name, Boolean(v))"
                      />
                    </TableCell>
                    <TableCell>
                      <div class="flex items-center gap-2">
                        <Checkbox
                          :checked="col.name in formData.config.metadata_fields"
                          @update:checked="(v: any) => setMetadataField(col.name, Boolean(v))"
                        />
                        <Input
                          v-if="col.name in formData.config.metadata_fields"
                          class="h-8 w-28"
                          :model-value="formData.config.metadata_fields[col.name]"
                          @update:model-value="(v: any) => setMetadataKey(col.name, String(v))"
                        />
                      </div>
                    </TableCell>
                    <TableCell class="text-center">
                      <Checkbox
                        :checked="formData.config.required_fields.includes(col.name)"
                        @update:checked="(v: any) => setRequiredField(col.name, Boolean(v))"
                      />
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon"
                        class="h-8 w-8"
                        @click="removeColumn(col.name)"
                      >
                        <Trash2 class="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </div>
          </div>

          <!-- Row Template Options -->
          <div class="space-y-3">
            <Label>Row Template</Label>

            <div class="grid gap-4 sm:grid-cols-2">
              <div class="space-y-2">
                <Label class="text-muted-foreground text-xs font-normal">Format</Label>
                <Select v-model="formData.config.row_template.format">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="key_value">Key-Value Pairs</SelectItem>
                    <SelectItem value="custom">Custom Template</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div class="space-y-2">
                <Label class="text-muted-foreground text-xs font-normal"
                  >Field order (one per line)</Label
                >
                <Textarea
                  v-model="fieldOrderText"
                  placeholder="Subject&#10;Description&#10;Resolution"
                  class="min-h-[80px]"
                />
              </div>
            </div>

            <div v-if="formData.config.row_template.format === 'custom'" class="space-y-2">
              <Label class="text-muted-foreground text-xs font-normal"
                >Custom template (Jinja2)</Label
              >
              <Textarea
                v-model="formData.config.row_template.custom_template"
                placeholder="Subject: {{ Subject }}&#10;Description: {{ Description }}"
                class="min-h-[100px] font-mono text-sm"
              />
            </div>

            <div class="flex items-center gap-6">
              <div class="flex items-center gap-2">
                <Checkbox
                  id="include-labels"
                  v-model:checked="formData.config.row_template.include_labels"
                />
                <Label for="include-labels" class="font-normal">Include labels</Label>
              </div>
              <div class="flex items-center gap-2">
                <Checkbox
                  id="omit-empty"
                  v-model:checked="formData.config.row_template.omit_empty"
                />
                <Label for="omit-empty" class="font-normal">Omit empty values</Label>
              </div>
            </div>
          </div>

          <!-- Default checkbox -->
          <div class="flex items-center gap-2">
            <Checkbox id="is-default" v-model:checked="formData.is_default" />
            <Label for="is-default" class="font-normal">
              Set as default profile for this knowledge base
            </Label>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            @click="
              showCreateDialog = false;
              showEditDialog = false;
              resetForm();
            "
          >
            Cancel
          </Button>
          <Button @click="selectedProfile ? updateProfile() : createProfile()">
            <Save class="mr-2 h-4 w-4" />
            {{ selectedProfile ? "Update" : "Create" }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Infer Results Dialog -->
    <Dialog :open="showInferDialog" @update:open="showInferDialog = $event">
      <DialogContent class="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Column Analysis</DialogTitle>
          <DialogDescription>
            Detected {{ inferredColumns.length }} columns from {{ inferredRowCount }} rows
          </DialogDescription>
        </DialogHeader>

        <div class="max-h-[400px] overflow-y-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Column</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Non-null</TableHead>
                <TableHead>Suggested</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="col in inferredColumns" :key="col.name">
                <TableCell class="font-medium">{{ col.name }}</TableCell>
                <TableCell>{{ col.inferred_type }}</TableCell>
                <TableCell>{{ col.non_null_count }}</TableCell>
                <TableCell>
                  <Badge v-if="col.suggested_metadata_key" variant="secondary">
                    {{ col.suggested_metadata_key }}
                  </Badge>
                  <span v-else class="text-muted-foreground">content</span>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>

        <DialogFooter>
          <Button variant="outline" @click="showInferDialog = false"> Cancel </Button>
          <Button @click="applyInferredColumns"> Apply Mappings </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Preview Dialog -->
    <Dialog :open="showPreviewDialog" @update:open="showPreviewDialog = $event">
      <DialogContent class="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Row Render Preview</DialogTitle>
          <DialogDescription> Preview of how a row would be rendered </DialogDescription>
        </DialogHeader>

        <div class="space-y-4">
          <div>
            <Label>Chunk Text</Label>
            <pre
              class="bg-muted mt-2 max-h-[300px] overflow-y-auto rounded-lg p-4 text-sm whitespace-pre-wrap"
              >{{ previewText }}</pre
            >
          </div>

          <div v-if="Object.keys(previewMetadata).length > 0">
            <Label>Extracted Metadata</Label>
            <div class="bg-muted mt-2 rounded-lg p-4">
              <div v-for="(value, key) in previewMetadata" :key="key" class="flex gap-2 text-sm">
                <span class="font-medium">{{ key }}:</span>
                <span>{{ value }}</span>
              </div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button @click="showPreviewDialog = false"> Close </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
