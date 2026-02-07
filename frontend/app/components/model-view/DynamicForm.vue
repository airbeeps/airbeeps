<script setup lang="ts" generic="T extends Record<string, any>">
import { ref, computed, watch, onMounted, onUnmounted, toRaw } from "vue";
import { Save, Loader2, Eye, EyeOff } from "lucide-vue-next";

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  submitText: "",
  showCancel: false,
  cancelText: "",
});

const emit = defineEmits<{
  submit: [data: T];
  cancel: [];
  change: [data: Record<string, any>];
  search: [payload: { fieldName: string; query: string; formData: Record<string, any> }];
}>();

const { t } = useI18n();

import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { Textarea } from "~/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { ImageUpload } from "~/components/ui/image-upload";
import { Switch } from "~/components/ui/switch";

export interface FieldOption {
  label: string;
  value: string | number;
  group?: string;
}

export interface FormField {
  name: string;
  label: string;
  type:
    | "text"
    | "email"
    | "password"
    | "number"
    | "textarea"
    | "select"
    | "multiselect"
    | "radio"
    | "switch"
    | "date"
    | "datetime"
    | "file"
    | "image"
    | "avatar"
    | "json";
  required?: boolean;
  disabled?: boolean;
  placeholder?: string;
  help?: string;
  description?: string;
  defaultValue?: any;

  /**
   * Optional HTML attributes to control browser autofill behavior.
   * When omitted:
   * - password fields default to `autocomplete="new-password"` to avoid credential autofill.
   */
  autocomplete?: string;
  /**
   * Optional HTML `name` attribute for the input element. Useful to avoid
   * password-manager heuristics (e.g. fields named "name" + "password").
   * This does NOT affect the payload key, which always uses `field.name`.
   */
  htmlName?: string;

  // Number field
  min?: number;
  max?: number;
  step?: number;

  // Textarea field
  rows?: number;

  // Select field
  options?: FieldOption[] | ((formData: Record<string, any>) => FieldOption[]);
  searchable?: boolean;

  // File field
  accept?: string;
  multiple?: boolean;

  // Validation rules
  validation?: {
    minLength?: number;
    maxLength?: number;
    pattern?: RegExp;
    custom?: (value: any) => string | null;
  };
}

interface Props {
  fields: FormField[];
  initialData?: Partial<T>;
  loading?: boolean;
  submitText?: string;
  showCancel?: boolean;
  cancelText?: string;
}

// Computed i18n defaults
const computedSubmitText = computed(() => props.submitText || t("components.dynamicForm.save"));
const computedCancelText = computed(() => props.cancelText || t("components.dynamicForm.cancel"));

// State management
const formData = ref<Record<string, any>>({});
const errors = ref<Record<string, string>>({});
const touchedFields = ref<Set<string>>(new Set());
const isInitialized = ref(false);
const passwordVisibility = ref<Record<string, boolean>>({});
// Track which password fields have server values (not returned for security)
const passwordFieldsWithServerValue = ref<Set<string>>(new Set());
// Track search queries for select fields with many options
const selectSearchQueries = ref<Record<string, string>>({});

// Unsaved changes tracking (global)
const unsavedChangesStore = useUnsavedChangesStore();
const sourceId = `dynamic-form-${Math.random().toString(36).slice(2)}`;
const initialSnapshot = ref<Record<string, any>>({});

const deepClone = <V,>(value: V): V => {
  const raw = value && typeof value === "object" ? (toRaw(value as any) as any) : value;
  if (typeof structuredClone === "function") {
    try {
      return structuredClone(raw);
    } catch {
      // fall through to JSON clone (sufficient for our form primitives/arrays/objects)
    }
  }
  // Fallback: sufficient for our form primitives/arrays/objects
  try {
    return JSON.parse(JSON.stringify(raw)) as V;
  } catch {
    // Last resort: return the raw value (best-effort for change events)
    return raw as V;
  }
};

const valuesEqual = (a: any, b: any): boolean => {
  if (a === b) return true;
  // Normalize undefined/null differences
  if ((a === undefined || a === null) && (b === undefined || b === null)) return true;
  // Arrays / objects
  if (typeof a === "object" || typeof b === "object") {
    try {
      return JSON.stringify(a) === JSON.stringify(b);
    } catch {
      return false;
    }
  }
  return false;
};

const getHtmlName = (field: FormField): string => field.htmlName || field.name;

const getAutocomplete = (field: FormField): string | undefined => {
  if (typeof field.autocomplete === "string") return field.autocomplete;
  if (field.type === "password") return "new-password";
  return undefined;
};

const getOptions = (field: FormField): FieldOption[] => {
  if (!field.options) return [];
  return typeof field.options === "function" ? field.options(formData.value) : field.options;
};

const getGroupedOptions = (field: FormField) => {
  const options = getOptions(field);
  const searchQuery = selectSearchQueries.value[field.name]?.toLowerCase() || "";

  // Filter options by search query
  const filteredOptions = searchQuery
    ? options.filter(
        (opt) =>
          opt.label.toLowerCase().includes(searchQuery) ||
          opt.value.toString().toLowerCase().includes(searchQuery)
      )
    : options;

  // Check if any option has a group
  const hasGroups = filteredOptions.some((opt) => opt.group);

  if (!hasGroups) {
    return { hasGroups: false, ungrouped: filteredOptions, grouped: {} };
  }

  // Group options
  const grouped: Record<string, FieldOption[]> = {};
  const ungrouped: FieldOption[] = [];

  filteredOptions.forEach((opt) => {
    if (opt.group) {
      if (!grouped[opt.group]) {
        grouped[opt.group] = [];
      }
      grouped[opt.group].push(opt);
    } else {
      ungrouped.push(opt);
    }
  });

  return { hasGroups: true, ungrouped, grouped };
};

const shouldShowSearch = (field: FormField): boolean => {
  const options = getOptions(field);
  return field.searchable || options.length > 10; // Show search if more than 10 options
};

const handleSelectSearch = (fieldName: string, value: string | number) => {
  emit("search", {
    fieldName,
    query: String(value ?? ""),
    formData: deepClone(formData.value),
  });
};

// Initialize form data
const initializeForm = () => {
  const data: Record<string, any> = {};
  const hasInitialData = props.initialData && Object.keys(props.initialData).length > 0;

  props.fields.forEach((field) => {
    if (props.initialData && props.initialData[field.name] !== undefined) {
      let value = props.initialData[field.name];

      // Auto convert JSON object to string
      if (field.type === "json" && typeof value === "object" && value !== null) {
        value = JSON.stringify(value, null, 2) as any;
      }

      data[field.name] = value;
    } else if (field.defaultValue !== undefined) {
      let value = field.defaultValue;

      // Auto convert default value JSON object to string
      if (field.type === "json" && typeof value === "object" && value !== null) {
        value = JSON.stringify(value, null, 2) as any;
      }

      data[field.name] = value;
    } else {
      // Set type default value
      switch (field.type) {
        case "multiselect":
          data[field.name] = [];
          break;
        case "switch":
          data[field.name] = false;
          break;
        case "number":
          data[field.name] = field.min || 0;
          break;
        case "json":
          data[field.name] = "{}";
          break;
        default:
          data[field.name] = "";
      }
    }

    // Mark password fields that likely have server values (edit mode with no value returned)
    if (field.type === "password" && hasInitialData && !data[field.name]) {
      passwordFieldsWithServerValue.value.add(field.name);
    }
  });

  formData.value = data;
  initialSnapshot.value = deepClone(data);
  isInitialized.value = true;
};

// Validate form
const validateField = (field: FormField, value: any): string | null => {
  if (field.required) {
    if (field.type === "multiselect") {
      if (!value || !Array.isArray(value) || value.length === 0) {
        return t("components.dynamicForm.validation.multiselectRequired", {
          label: field.label,
        });
      }
    } else if (!value || value === "") {
      return t("components.dynamicForm.validation.required", {
        label: field.label,
      });
    }
  }

  // Special validation for JSON field
  if (field.type === "json" && value && value !== "") {
    if (!isValidJson(value)) {
      return t("components.dynamicForm.validation.invalidJson", {
        label: field.label,
      });
    }
  }

  if (field.validation) {
    const { minLength, maxLength, pattern, custom } = field.validation;

    if (minLength && value && value.length < minLength) {
      return t("components.dynamicForm.validation.minLength", {
        label: field.label,
        count: minLength,
      });
    }

    if (maxLength && value && value.length > maxLength) {
      return t("components.dynamicForm.validation.maxLength", {
        label: field.label,
        count: maxLength,
      });
    }

    if (pattern && value && !pattern.test(value)) {
      return t("components.dynamicForm.validation.invalidFormat", {
        label: field.label,
      });
    }

    if (custom) {
      return custom(value);
    }
  }

  return null;
};

const validateForm = (): boolean => {
  const newErrors: Record<string, string> = {};

  // Mark all fields as touched
  props.fields.forEach((field) => {
    touchedFields.value.add(field.name);
    const error = validateField(field, formData.value[field.name]);
    if (error) {
      newErrors[field.name] = error;
    }
  });

  errors.value = newErrors;
  return Object.keys(newErrors).length === 0;
};

// Computed properties
const isValid = computed(() => {
  if (!isInitialized.value) return false;

  // Validate all required fields
  for (const field of props.fields) {
    if (field.required) {
      const value = formData.value[field.name];

      if (field.type === "multiselect") {
        if (!value || !Array.isArray(value) || value.length === 0) {
          return false;
        }
      } else if (!value || value === "") {
        return false;
      }
    }
  }

  // Check for any validation errors
  return Object.keys(errors.value).length === 0;
});

// Methods
const handleSubmit = () => {
  if (validateForm() && isValid.value) {
    // Process submit data, convert JSON string back to object
    const submitData = { ...formData.value };

    props.fields.forEach((field) => {
      if (
        field.type === "json" &&
        submitData[field.name] &&
        typeof submitData[field.name] === "string"
      ) {
        try {
          submitData[field.name] = JSON.parse(submitData[field.name]);
        } catch {
          // If parse fails, keep original string value
        }
      }

      // Don't send password fields if empty and they have server values
      // (to avoid overwriting existing passwords with blank)
      if (
        field.type === "password" &&
        !submitData[field.name] &&
        passwordFieldsWithServerValue.value.has(field.name)
      ) {
        delete submitData[field.name];
      }
    });

    emit("submit", submitData as T);
  }
};

const handleCancel = () => {
  emit("cancel");
};

const markFieldAsTouched = (fieldName: string) => {
  touchedFields.value.add(fieldName);
};

// Multiselect related methods
const isMultiSelectOptionSelected = (fieldName: string, value: any): boolean => {
  if (!formData.value[fieldName]) return false;
  const currentValues = formData.value[fieldName] as any[];
  return currentValues.includes(value);
};

const toggleMultiSelectOption = (fieldName: string, value: any, checked: boolean) => {
  markFieldAsTouched(fieldName);

  if (!formData.value[fieldName]) {
    formData.value[fieldName] = [];
  }

  const currentValues = [...(formData.value[fieldName] as any[])];

  if (checked) {
    if (!currentValues.includes(value)) {
      currentValues.push(value);
    }
  } else {
    const index = currentValues.indexOf(value);
    if (index > -1) {
      currentValues.splice(index, 1);
    }
  }

  formData.value[fieldName] = currentValues;
};

// JSON related methods
const isValidJson = (jsonString: string): boolean => {
  if (!jsonString || jsonString.trim() === "") return true; // Empty string is considered valid

  try {
    JSON.parse(jsonString);
    return true;
  } catch {
    return false;
  }
};

const formatJson = (fieldName: string) => {
  const value = formData.value[fieldName];
  if (!value) return;

  try {
    const parsed = JSON.parse(value);
    formData.value[fieldName] = JSON.stringify(parsed, null, 2);
  } catch (error) {
    // If parse fails, do nothing
  }
};

const minifyJson = (fieldName: string) => {
  const value = formData.value[fieldName];
  if (!value) return;

  try {
    const parsed = JSON.parse(value);
    formData.value[fieldName] = JSON.stringify(parsed);
  } catch (error) {
    // If parse fails, do nothing
  }
};

// Watchers
watch(
  () => props.initialData,
  () => {
    initializeForm();
  },
  { deep: true }
);

// Real-time validation on form data change
watch(
  () => formData.value,
  () => {
    if (isInitialized.value) {
      const newErrors: Record<string, string> = {};

      props.fields.forEach((field) => {
        if (touchedFields.value.has(field.name) || field.required) {
          const error = validateField(field, formData.value[field.name]);
          if (error) {
            newErrors[field.name] = error;
          }
        }
      });

      errors.value = newErrors;
    }
    // Emit a best-effort change event so parents can implement dynamic behaviors
    emit("change", deepClone(formData.value));
  },
  { deep: true, immediate: false }
);

// Track unsaved changes for navigation confirmation (logo click, etc.)
const isDirty = computed(() => {
  if (!isInitialized.value) return false;
  for (const field of props.fields) {
    const key = field.name;
    if (!valuesEqual(formData.value[key], initialSnapshot.value[key])) {
      return true;
    }
  }
  return false;
});

watch(
  () => isDirty.value,
  (dirty) => {
    unsavedChangesStore.setDirty(sourceId, dirty);
  },
  { immediate: true }
);

// Lifecycle
onMounted(() => {
  initializeForm();
});

onUnmounted(() => {
  // Always clear this instance’s flag on unmount so it can’t get “stuck”
  unsavedChangesStore.setDirty(sourceId, false);
});

// Public API for parent components (e.g., ModelView hooks)
const setFieldValue = (name: string, value: any) => {
  if (!(name in formData.value)) return;
  formData.value[name] = value;
  markFieldAsTouched(name);
};

const setValues = (values: Record<string, any>) => {
  if (!values) return;
  for (const [k, v] of Object.entries(values)) {
    if (k in formData.value) {
      formData.value[k] = v;
    }
  }
};

const getValues = () => deepClone(formData.value);

defineExpose({
  setFieldValue,
  setValues,
  getValues,
});
</script>

<template>
  <form class="space-y-4" autocomplete="off" @submit.prevent="handleSubmit">
    <div v-for="field in fields" :key="field.name" class="space-y-2">
      <Label :for="field.name" class="text-sm font-medium">
        {{ field.label }}
        <span v-if="field.required" class="text-destructive">*</span>
      </Label>

      <!-- Text/Email input -->
      <Input
        v-if="field.type === 'text' || field.type === 'email'"
        :id="field.name"
        v-model="formData[field.name]"
        :name="getHtmlName(field)"
        :autocomplete="getAutocomplete(field)"
        :type="field.type"
        :placeholder="field.placeholder"
        :disabled="field.disabled || loading"
        :class="{ 'border-destructive': errors[field.name] }"
        @focus="markFieldAsTouched(field.name)"
        @blur="markFieldAsTouched(field.name)"
      />

      <!-- Password input with show/hide toggle -->
      <div v-else-if="field.type === 'password'" class="space-y-1">
        <div class="relative">
          <Input
            :id="field.name"
            v-model="formData[field.name]"
            :name="getHtmlName(field)"
            :autocomplete="getAutocomplete(field)"
            :type="passwordVisibility[field.name] ? 'text' : 'password'"
            :placeholder="
              passwordFieldsWithServerValue.has(field.name) && !formData[field.name]
                ? '••••••••••••••••••••'
                : field.placeholder || '••••••••'
            "
            :disabled="field.disabled || loading"
            :class="{ 'border-destructive': errors[field.name], 'pr-10': true }"
            @focus="
              markFieldAsTouched(field.name);
              passwordFieldsWithServerValue.delete(field.name);
            "
            @blur="markFieldAsTouched(field.name)"
          />
          <button
            v-if="formData[field.name]"
            type="button"
            class="text-muted-foreground hover:text-foreground absolute top-1/2 right-2 -translate-y-1/2"
            :disabled="field.disabled || loading"
            @click="passwordVisibility[field.name] = !passwordVisibility[field.name]"
          >
            <Eye v-if="!passwordVisibility[field.name]" class="h-4 w-4" />
            <EyeOff v-else class="h-4 w-4" />
          </button>
        </div>
        <p
          v-if="passwordFieldsWithServerValue.has(field.name) && !formData[field.name]"
          class="text-muted-foreground text-xs"
        >
          {{ t("components.dynamicForm.passwordExists") }}
        </p>
      </div>

      <!-- Number input -->
      <Input
        v-else-if="field.type === 'number'"
        :id="field.name"
        v-model.number="formData[field.name]"
        :name="getHtmlName(field)"
        :autocomplete="getAutocomplete(field)"
        type="number"
        :placeholder="field.placeholder"
        :disabled="field.disabled || loading"
        :min="field.min"
        :max="field.max"
        :step="field.step"
        :class="{ 'border-destructive': errors[field.name] }"
        @focus="markFieldAsTouched(field.name)"
        @blur="markFieldAsTouched(field.name)"
      />

      <!-- Textarea -->
      <Textarea
        v-else-if="field.type === 'textarea'"
        :id="field.name"
        v-model="formData[field.name]"
        :placeholder="field.placeholder"
        :disabled="field.disabled || loading"
        :rows="field.rows || 3"
        :class="{ 'border-destructive': errors[field.name] }"
        @focus="markFieldAsTouched(field.name)"
        @blur="markFieldAsTouched(field.name)"
      />

      <!-- Select -->
      <Select
        v-else-if="field.type === 'select'"
        v-model="formData[field.name]"
        :disabled="field.disabled || loading"
        @update:model-value="() => markFieldAsTouched(field.name)"
      >
        <SelectTrigger :class="{ 'border-destructive': errors[field.name] }">
          <SelectValue :placeholder="field.placeholder" />
        </SelectTrigger>
        <SelectContent>
          <!-- Search input for large lists - sticky at top -->
          <div
            v-if="shouldShowSearch(field)"
            class="bg-popover sticky top-0 z-10 border-b px-2 py-1.5"
          >
            <Input
              v-model="selectSearchQueries[field.name]"
              :placeholder="t('components.dynamicForm.searchPlaceholder')"
              class="h-8"
              @update:model-value="(value) => handleSelectSearch(field.name, value)"
              @click.stop
              @keydown.stop
            />
          </div>

          <template v-if="getGroupedOptions(field).hasGroups">
            <!-- Ungrouped options first -->
            <template v-if="getGroupedOptions(field).ungrouped.length > 0">
              <SelectItem
                v-for="option in getGroupedOptions(field).ungrouped"
                :key="option.value"
                :value="option.value.toString()"
              >
                {{ option.label }}
              </SelectItem>
            </template>

            <!-- Grouped options -->
            <SelectGroup
              v-for="(groupOptions, groupName) in getGroupedOptions(field).grouped"
              :key="groupName"
            >
              <SelectLabel>{{ groupName }}</SelectLabel>
              <SelectItem
                v-for="option in groupOptions"
                :key="option.value"
                :value="option.value.toString()"
              >
                {{ option.label }}
              </SelectItem>
            </SelectGroup>
          </template>

          <!-- Non-grouped options -->
          <template v-else>
            <SelectItem
              v-for="option in getGroupedOptions(field).ungrouped"
              :key="option.value"
              :value="option.value.toString()"
            >
              {{ option.label }}
            </SelectItem>
          </template>

          <!-- No results message -->
          <div
            v-if="
              shouldShowSearch(field) &&
              getGroupedOptions(field).ungrouped.length === 0 &&
              Object.keys(getGroupedOptions(field).grouped).length === 0
            "
            class="text-muted-foreground px-2 py-6 text-center text-sm"
          >
            {{ t("components.dynamicForm.noResults") }}
          </div>
        </SelectContent>
      </Select>

      <!-- Multiselect -->
      <div v-else-if="field.type === 'multiselect'" class="space-y-3">
        <div
          :class="[
            'grid grid-cols-1 gap-2 rounded-md border p-2',
            errors[field.name] ? 'border-destructive bg-destructive/5' : 'border-border',
          ]"
        >
          <div
            v-for="option in getOptions(field)"
            :key="option.value"
            class="flex items-center space-x-2"
          >
            <input
              :id="`${field.name}-${option.value}`"
              type="checkbox"
              :checked="isMultiSelectOptionSelected(field.name, option.value)"
              :disabled="field.disabled || loading"
              class="text-primary focus:ring-primary h-4 w-4 rounded border-gray-300"
              @change="
                (event: Event) => {
                  const target = event.target as HTMLInputElement;
                  toggleMultiSelectOption(field.name, option.value, target.checked);
                }
              "
            />
            <Label
              :for="`${field.name}-${option.value}`"
              class="flex-1 cursor-pointer text-sm font-normal"
            >
              {{ option.label }}
            </Label>
          </div>
        </div>
        <div
          v-if="formData[field.name] && formData[field.name].length > 0"
          class="text-muted-foreground text-xs"
        >
          {{
            t("components.dynamicForm.selected", {
              count: formData[field.name].length,
            })
          }}
        </div>
      </div>

      <!-- Switch -->
      <div v-else-if="field.type === 'switch'" class="flex items-center space-x-3">
        <Switch
          :id="field.name"
          v-model="formData[field.name]"
          :disabled="field.disabled || loading"
          @update:model-value="() => markFieldAsTouched(field.name)"
        />
        <Label :for="field.name" class="cursor-pointer text-sm">
          {{ field.description || field.label }}
        </Label>
      </div>

      <!-- Avatar upload -->
      <AvatarUpload
        v-else-if="field.type === 'avatar'"
        :id="field.name"
        v-model="formData[field.name]"
        :disabled="field.disabled || loading"
        :class="{ 'border-destructive': errors[field.name] }"
      />

      <!-- JSON editor -->
      <div v-else-if="field.type === 'json'" class="space-y-2">
        <Textarea
          :id="field.name"
          v-model="formData[field.name]"
          :placeholder="field.placeholder || t('components.dynamicForm.jsonPlaceholder')"
          :disabled="field.disabled || loading"
          :rows="field.rows || 6"
          :class="{ 'border-destructive': errors[field.name] }"
          class="font-mono text-sm"
          @focus="markFieldAsTouched(field.name)"
          @blur="markFieldAsTouched(field.name)"
        />
        <div class="flex items-center justify-between text-xs">
          <span class="text-muted-foreground">
            {{ t("components.dynamicForm.jsonHint") }}
          </span>
          <div class="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              :disabled="field.disabled || loading"
              class="h-6 px-2 text-xs"
              @click="formatJson(field.name)"
            >
              {{ t("components.dynamicForm.formatJson") }}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              :disabled="field.disabled || loading"
              class="h-6 px-2 text-xs"
              @click="minifyJson(field.name)"
            >
              {{ t("components.dynamicForm.minifyJson") }}
            </Button>
          </div>
        </div>
      </div>

      <!-- Error message -->
      <div v-if="errors[field.name]" class="text-destructive text-sm">
        {{ errors[field.name] }}
      </div>

      <!-- Help text -->
      <div v-if="field.help" class="text-muted-foreground text-sm">
        {{ field.help }}
      </div>
    </div>

    <!-- Form action buttons -->
    <slot name="actions" :on-submit="handleSubmit" :on-cancel="handleCancel">
      <div class="flex justify-end gap-2 pt-4">
        <Button
          v-if="showCancel"
          type="button"
          variant="outline"
          :disabled="loading"
          @click="handleCancel"
        >
          {{ computedCancelText }}
        </Button>
        <Button type="submit" :disabled="loading || !isValid">
          <Loader2 v-if="loading" class="mr-1 h-4 w-4 animate-spin" />
          <Save v-else class="mr-1 h-4 w-4" />
          {{ computedSubmitText }}
        </Button>
      </div>
    </slot>
  </form>
</template>
