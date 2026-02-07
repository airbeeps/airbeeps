<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { Settings2, ChevronDown, ChevronUp, FileText, Table, Layers } from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import { Label } from "~/components/ui/label";
import { Input } from "~/components/ui/input";
import { Checkbox } from "~/components/ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "~/components/ui/collapsible";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "~/components/ui/tooltip";
import type { DocumentPreprocessingConfig } from "~/types/api";

const { t } = useI18n();

interface Props {
  files: File[];
}

const props = defineProps<Props>();

const emit = defineEmits<{
  "update:config": [config: DocumentPreprocessingConfig];
}>();

// Panel state
const isOpen = ref(false);

// Config state
const config = ref<DocumentPreprocessingConfig>({
  // PDF options
  pdf_max_pages: undefined,
  pdf_page_range: undefined,
  pdf_enable_ocr: false,
  // Excel options
  sheet_names: undefined,
  header_row: 0,
  skip_rows: 0,
  // Chunking options
  chunking_strategy: "auto",
  chunk_size_override: undefined,
  chunk_overlap_override: undefined,
  // General options
  extract_tables_as_markdown: true,
  clean_data: true,
});

// Detect file types
const hasPdfFiles = computed(() => props.files.some((f) => f.name.toLowerCase().endsWith(".pdf")));

const hasExcelFiles = computed(() =>
  props.files.some((f) => {
    const name = f.name.toLowerCase();
    return name.endsWith(".xlsx") || name.endsWith(".xls") || name.endsWith(".csv");
  })
);

// Watch for config changes and emit
watch(
  config,
  (newConfig) => {
    // Only emit non-default values
    const cleanConfig: DocumentPreprocessingConfig = {};

    // PDF options
    if (newConfig.pdf_max_pages) cleanConfig.pdf_max_pages = newConfig.pdf_max_pages;
    if (newConfig.pdf_page_range) cleanConfig.pdf_page_range = newConfig.pdf_page_range;
    if (newConfig.pdf_enable_ocr) cleanConfig.pdf_enable_ocr = newConfig.pdf_enable_ocr;

    // Excel options
    if (newConfig.sheet_names?.length) cleanConfig.sheet_names = newConfig.sheet_names;
    if (newConfig.header_row && newConfig.header_row > 0)
      cleanConfig.header_row = newConfig.header_row;
    if (newConfig.skip_rows && newConfig.skip_rows > 0) cleanConfig.skip_rows = newConfig.skip_rows;

    // Chunking options
    if (newConfig.chunking_strategy && newConfig.chunking_strategy !== "auto")
      cleanConfig.chunking_strategy = newConfig.chunking_strategy;
    if (newConfig.chunk_size_override)
      cleanConfig.chunk_size_override = newConfig.chunk_size_override;
    if (newConfig.chunk_overlap_override)
      cleanConfig.chunk_overlap_override = newConfig.chunk_overlap_override;

    // General options
    if (newConfig.extract_tables_as_markdown === false)
      cleanConfig.extract_tables_as_markdown = false;
    if (newConfig.clean_data === false) cleanConfig.clean_data = false;

    emit("update:config", Object.keys(cleanConfig).length > 0 ? cleanConfig : {});
  },
  { deep: true }
);

// Auto-expand when files are selected
watch(
  () => props.files.length,
  (length) => {
    if (length > 0 && (hasPdfFiles.value || hasExcelFiles.value)) {
      isOpen.value = true;
    }
  }
);

const chunkingStrategies = [
  { value: "auto", label: t("components.fileUpload.preprocessing.chunking.auto") },
  { value: "semantic", label: t("components.fileUpload.preprocessing.chunking.semantic") },
  { value: "hierarchical", label: t("components.fileUpload.preprocessing.chunking.hierarchical") },
  { value: "sentence", label: t("components.fileUpload.preprocessing.chunking.sentence") },
];
</script>

<template>
  <Collapsible v-model:open="isOpen" class="mt-4">
    <CollapsibleTrigger as-child>
      <Button variant="outline" size="sm" class="w-full justify-between">
        <div class="flex items-center">
          <Settings2 class="mr-2 h-4 w-4" />
          {{ t("components.fileUpload.preprocessing.title") }}
        </div>
        <ChevronDown v-if="!isOpen" class="h-4 w-4" />
        <ChevronUp v-else class="h-4 w-4" />
      </Button>
    </CollapsibleTrigger>

    <CollapsibleContent class="mt-3 space-y-4">
      <!-- PDF Options -->
      <div v-if="hasPdfFiles" class="space-y-3 rounded-lg border p-3">
        <div class="flex items-center gap-2 text-sm font-medium">
          <FileText class="h-4 w-4" />
          {{ t("components.fileUpload.preprocessing.pdf.title") }}
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-1">
            <Label class="text-xs">{{
              t("components.fileUpload.preprocessing.pdf.maxPages")
            }}</Label>
            <Input
              v-model.number="config.pdf_max_pages"
              type="number"
              :placeholder="t('components.fileUpload.preprocessing.pdf.maxPagesPlaceholder')"
              class="h-8"
              min="1"
              max="2000"
            />
          </div>

          <div class="space-y-1">
            <Label class="text-xs">{{
              t("components.fileUpload.preprocessing.pdf.pageRange")
            }}</Label>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger as-child>
                  <Input
                    v-model="config.pdf_page_range"
                    type="text"
                    :placeholder="t('components.fileUpload.preprocessing.pdf.pageRangePlaceholder')"
                    class="h-8"
                  />
                </TooltipTrigger>
                <TooltipContent side="top" class="max-w-xs">
                  {{ t("components.fileUpload.preprocessing.pdf.pageRangeHelp") }}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <Checkbox id="pdf-ocr" v-model:checked="config.pdf_enable_ocr" />
          <Label for="pdf-ocr" class="text-xs font-normal">
            {{ t("components.fileUpload.preprocessing.pdf.enableOcr") }}
          </Label>
        </div>
      </div>

      <!-- Excel/CSV Options -->
      <div v-if="hasExcelFiles" class="space-y-3 rounded-lg border p-3">
        <div class="flex items-center gap-2 text-sm font-medium">
          <Table class="h-4 w-4" />
          {{ t("components.fileUpload.preprocessing.excel.title") }}
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-1">
            <Label class="text-xs">{{
              t("components.fileUpload.preprocessing.excel.headerRow")
            }}</Label>
            <Input
              v-model.number="config.header_row"
              type="number"
              :placeholder="'0'"
              class="h-8"
              min="0"
            />
          </div>

          <div class="space-y-1">
            <Label class="text-xs">{{
              t("components.fileUpload.preprocessing.excel.skipRows")
            }}</Label>
            <Input
              v-model.number="config.skip_rows"
              type="number"
              :placeholder="'0'"
              class="h-8"
              min="0"
            />
          </div>
        </div>
      </div>

      <!-- Chunking Options (always shown) -->
      <div class="space-y-3 rounded-lg border p-3">
        <div class="flex items-center gap-2 text-sm font-medium">
          <Layers class="h-4 w-4" />
          {{ t("components.fileUpload.preprocessing.chunking.title") }}
        </div>

        <div class="space-y-3">
          <div class="space-y-1">
            <Label class="text-xs">{{
              t("components.fileUpload.preprocessing.chunking.strategy")
            }}</Label>
            <Select v-model="config.chunking_strategy">
              <SelectTrigger class="h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem
                  v-for="strategy in chunkingStrategies"
                  :key="strategy.value"
                  :value="strategy.value"
                >
                  {{ strategy.label }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div class="space-y-1">
              <Label class="text-xs">{{
                t("components.fileUpload.preprocessing.chunking.chunkSize")
              }}</Label>
              <Input
                v-model.number="config.chunk_size_override"
                type="number"
                :placeholder="
                  t('components.fileUpload.preprocessing.chunking.chunkSizePlaceholder')
                "
                class="h-8"
                min="100"
                max="8000"
              />
            </div>

            <div class="space-y-1">
              <Label class="text-xs">{{
                t("components.fileUpload.preprocessing.chunking.chunkOverlap")
              }}</Label>
              <Input
                v-model.number="config.chunk_overlap_override"
                type="number"
                :placeholder="
                  t('components.fileUpload.preprocessing.chunking.chunkOverlapPlaceholder')
                "
                class="h-8"
                min="0"
                max="500"
              />
            </div>
          </div>
        </div>
      </div>
    </CollapsibleContent>
  </Collapsible>
</template>
