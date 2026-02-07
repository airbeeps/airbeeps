<script setup lang="ts">
import { ref, watch, computed } from "vue";
import { Table, Loader2, AlertCircle, Check } from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import { Checkbox } from "~/components/ui/checkbox";
import { Label } from "~/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog";
import { Badge } from "~/components/ui/badge";
import {
  Table as UITable,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table";
import type { ExcelSheetsResponse, ExcelSheetInfo, PreviewRowsResponse } from "~/types/api";

const { $api } = useNuxtApp();

interface Props {
  open: boolean;
  file: File | null;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  "select-sheets": [sheets: string[]];
}>();

const loading = ref(false);
const previewLoading = ref(false);
const error = ref<string | null>(null);
const sheetsInfo = ref<ExcelSheetsResponse | null>(null);
const selectedSheets = ref<Set<string>>(new Set());
const previewData = ref<PreviewRowsResponse | null>(null);
const previewSheet = ref<string | null>(null);

// Load sheets info when dialog opens
watch(
  () => props.open && props.file,
  async (shouldLoad) => {
    if (!shouldLoad || !props.file) {
      sheetsInfo.value = null;
      error.value = null;
      selectedSheets.value = new Set();
      previewData.value = null;
      previewSheet.value = null;
      return;
    }

    loading.value = true;
    error.value = null;

    try {
      const formData = new FormData();
      formData.append("file", props.file);

      const response = (await $api("/v1/admin/rag/documents/excel-sheets", {
        method: "POST",
        body: formData,
      })) as ExcelSheetsResponse;

      sheetsInfo.value = response;

      // Select all sheets by default
      selectedSheets.value = new Set(response.sheets.map((s) => s.name));

      // Preview first sheet
      if (response.sheets.length > 0) {
        await loadPreview(response.sheets[0].name);
      }
    } catch (e: any) {
      error.value = e?.message || "Failed to analyze Excel file";
    } finally {
      loading.value = false;
    }
  },
  { immediate: true }
);

const loadPreview = async (sheetName: string) => {
  if (!props.file || previewSheet.value === sheetName) return;

  previewLoading.value = true;
  previewSheet.value = sheetName;

  try {
    const formData = new FormData();
    formData.append("file", props.file);
    formData.append("sheet", sheetName);
    formData.append("limit", "5");

    const response = (await $api("/v1/admin/rag/documents/preview-rows", {
      method: "POST",
      body: formData,
    })) as PreviewRowsResponse;

    previewData.value = response;
  } catch (e: any) {
    previewData.value = null;
  } finally {
    previewLoading.value = false;
  }
};

const toggleSheet = (sheetName: string) => {
  const newSet = new Set(selectedSheets.value);
  if (newSet.has(sheetName)) {
    newSet.delete(sheetName);
  } else {
    newSet.add(sheetName);
  }
  selectedSheets.value = newSet;
};

const selectAll = () => {
  if (sheetsInfo.value) {
    selectedSheets.value = new Set(sheetsInfo.value.sheets.map((s) => s.name));
  }
};

const selectNone = () => {
  selectedSheets.value = new Set();
};

const confirm = () => {
  emit("select-sheets", Array.from(selectedSheets.value));
  emit("update:open", false);
};

const close = () => emit("update:open", false);

const formatRowCount = (count: number) => {
  if (count >= 1000) return `${(count / 1000).toFixed(1)}k`;
  return count.toString();
};
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="flex max-h-[80vh] flex-col overflow-hidden sm:max-w-2xl">
      <DialogHeader>
        <DialogTitle class="flex items-center gap-2">
          <Table class="h-5 w-5" />
          Excel/CSV Sheet Selection
        </DialogTitle>
        <DialogDescription>
          {{ file?.name || "Excel file" }}
        </DialogDescription>
      </DialogHeader>

      <div class="flex-1 overflow-auto py-4">
        <!-- Loading state -->
        <div v-if="loading" class="flex items-center justify-center py-8">
          <Loader2 class="text-muted-foreground h-6 w-6 animate-spin" />
          <span class="text-muted-foreground ml-2">Analyzing file...</span>
        </div>

        <!-- Error state -->
        <div v-else-if="error" class="text-destructive flex items-center gap-2 py-4">
          <AlertCircle class="h-5 w-5" />
          <span>{{ error }}</span>
        </div>

        <!-- Sheets list -->
        <div v-else-if="sheetsInfo" class="space-y-4">
          <!-- Sheet selection -->
          <div>
            <div class="mb-2 flex items-center justify-between">
              <Label class="text-sm font-medium">Select sheets to process</Label>
              <div class="flex gap-2">
                <Button variant="ghost" size="sm" @click="selectAll">All</Button>
                <Button variant="ghost" size="sm" @click="selectNone">None</Button>
              </div>
            </div>

            <div class="divide-y rounded-lg border">
              <div
                v-for="sheet in sheetsInfo.sheets"
                :key="sheet.name"
                class="hover:bg-muted/50 flex cursor-pointer items-center justify-between p-3"
                @click="toggleSheet(sheet.name)"
              >
                <div class="flex items-center gap-3">
                  <Checkbox
                    :checked="selectedSheets.has(sheet.name)"
                    @update:checked="toggleSheet(sheet.name)"
                  />
                  <div>
                    <div class="font-medium">{{ sheet.name }}</div>
                    <div class="text-muted-foreground text-xs">
                      {{ formatRowCount(sheet.row_count) }} rows, {{ sheet.column_count }} columns
                    </div>
                  </div>
                </div>
                <Button variant="ghost" size="sm" @click.stop="loadPreview(sheet.name)">
                  Preview
                </Button>
              </div>
            </div>
          </div>

          <!-- Data preview -->
          <div v-if="previewData || previewLoading" class="rounded-lg border p-3">
            <div class="mb-2 flex items-center justify-between">
              <Label class="text-sm font-medium"> Preview: {{ previewSheet }} </Label>
              <Badge variant="outline"> {{ previewData?.total_rows || 0 }} total rows </Badge>
            </div>

            <div v-if="previewLoading" class="flex items-center justify-center py-4">
              <Loader2 class="h-4 w-4 animate-spin" />
            </div>

            <div v-else-if="previewData" class="max-h-48 overflow-auto">
              <UITable>
                <TableHeader>
                  <TableRow>
                    <TableHead
                      v-for="col in previewData.columns.slice(0, 6)"
                      :key="col"
                      class="text-xs whitespace-nowrap"
                    >
                      {{ col }}
                    </TableHead>
                    <TableHead v-if="previewData.columns.length > 6" class="text-xs">
                      ...
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow v-for="(row, idx) in previewData.rows" :key="idx">
                    <TableCell
                      v-for="col in previewData.columns.slice(0, 6)"
                      :key="col"
                      class="max-w-32 truncate py-1 text-xs"
                    >
                      {{ row[col] ?? "" }}
                    </TableCell>
                    <TableCell v-if="previewData.columns.length > 6" class="text-xs">
                      ...
                    </TableCell>
                  </TableRow>
                </TableBody>
              </UITable>
            </div>
          </div>
        </div>
      </div>

      <DialogFooter>
        <Button variant="outline" @click="close">Cancel</Button>
        <Button @click="confirm" :disabled="selectedSheets.size === 0">
          <Check class="mr-2 h-4 w-4" />
          Use {{ selectedSheets.size }} sheet(s)
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
