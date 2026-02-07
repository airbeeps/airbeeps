<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { Calendar, ChevronDown } from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "~/components/ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "~/components/ui/popover";

const { t } = useI18n();

interface DateRange {
  start: string | null;
  end: string | null;
}

const props = defineProps<{
  modelValue?: DateRange;
  label?: string;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: DateRange];
  change: [value: DateRange];
}>();

// Preset options
type PresetKey = "24h" | "7d" | "30d" | "90d" | "all" | "custom";
const selectedPreset = ref<PresetKey>("all");
const customStart = ref("");
const customEnd = ref("");
const showCustom = ref(false);

// Presets configuration
const presets = [
  { key: "24h" as const, label: t("admin.filters.last24h"), hours: 24 },
  { key: "7d" as const, label: t("admin.filters.last7d"), days: 7 },
  { key: "30d" as const, label: t("admin.filters.last30d"), days: 30 },
  { key: "90d" as const, label: "Last 90 Days", days: 90 },
  { key: "all" as const, label: t("admin.filters.allTime"), days: null },
];

// Calculate date from preset
const getDateFromPreset = (preset: (typeof presets)[number]): DateRange => {
  if (preset.days === null) {
    return { start: null, end: null };
  }

  const end = new Date();
  const start = new Date();

  if (preset.hours) {
    start.setTime(end.getTime() - preset.hours * 60 * 60 * 1000);
  } else if (preset.days) {
    start.setDate(end.getDate() - preset.days);
  }

  return {
    start: start.toISOString().split("T")[0],
    end: end.toISOString().split("T")[0],
  };
};

// Current display label
const displayLabel = computed(() => {
  if (selectedPreset.value === "custom") {
    if (customStart.value && customEnd.value) {
      return `${customStart.value} - ${customEnd.value}`;
    }
    return t("admin.filters.custom");
  }

  const preset = presets.find((p) => p.key === selectedPreset.value);
  return preset?.label || t("admin.filters.allTime");
});

// Select preset
const selectPreset = (preset: (typeof presets)[number]) => {
  selectedPreset.value = preset.key;
  showCustom.value = false;

  const range = getDateFromPreset(preset);
  emit("update:modelValue", range);
  emit("change", range);
};

// Apply custom range
const applyCustomRange = () => {
  if (customStart.value && customEnd.value) {
    selectedPreset.value = "custom";
    const range = { start: customStart.value, end: customEnd.value };
    emit("update:modelValue", range);
    emit("change", range);
    showCustom.value = false;
  }
};

// Clear filter
const clearFilter = () => {
  selectedPreset.value = "all";
  customStart.value = "";
  customEnd.value = "";
  showCustom.value = false;
  emit("update:modelValue", { start: null, end: null });
  emit("change", { start: null, end: null });
};

// Initialize from modelValue
watch(
  () => props.modelValue,
  (val) => {
    if (val?.start && val?.end) {
      customStart.value = val.start;
      customEnd.value = val.end;

      // Check if it matches a preset
      const matchingPreset = presets.find((p) => {
        const range = getDateFromPreset(p);
        return range.start === val.start && range.end === val.end;
      });

      if (matchingPreset) {
        selectedPreset.value = matchingPreset.key;
      } else {
        selectedPreset.value = "custom";
      }
    } else {
      selectedPreset.value = "all";
    }
  },
  { immediate: true }
);
</script>

<template>
  <div class="space-y-2">
    <Label v-if="label">{{ label }}</Label>

    <DropdownMenu>
      <DropdownMenuTrigger as-child>
        <Button variant="outline" class="w-full justify-between">
          <div class="flex items-center gap-2">
            <Calendar class="h-4 w-4" />
            <span>{{ displayLabel }}</span>
          </div>
          <ChevronDown class="h-4 w-4 opacity-50" />
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="start" class="w-56">
        <DropdownMenuItem
          v-for="preset in presets"
          :key="preset.key"
          @click="selectPreset(preset)"
          :class="{ 'bg-accent': selectedPreset === preset.key }"
        >
          {{ preset.label }}
        </DropdownMenuItem>

        <DropdownMenuSeparator />

        <div class="p-2">
          <Button
            variant="ghost"
            size="sm"
            class="w-full justify-start"
            @click="showCustom = !showCustom"
          >
            {{ t("admin.filters.custom") }}
          </Button>

          <div v-if="showCustom" class="mt-2 space-y-2">
            <div class="space-y-1">
              <Label class="text-xs">{{ t("admin.filters.from") }}</Label>
              <Input type="date" v-model="customStart" class="h-8 text-sm" />
            </div>
            <div class="space-y-1">
              <Label class="text-xs">{{ t("admin.filters.to") }}</Label>
              <Input type="date" v-model="customEnd" class="h-8 text-sm" />
            </div>
            <div class="flex gap-2">
              <Button size="sm" class="flex-1" @click="applyCustomRange">
                {{ t("admin.filters.apply") }}
              </Button>
              <Button size="sm" variant="outline" @click="clearFilter">
                {{ t("admin.filters.clear") }}
              </Button>
            </div>
          </div>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  </div>
</template>
