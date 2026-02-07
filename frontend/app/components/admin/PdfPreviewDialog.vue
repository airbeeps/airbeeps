<script setup lang="ts">
import { ref, watch } from "vue";
import { FileText, Loader2, AlertCircle } from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog";
import { Badge } from "~/components/ui/badge";
import type { PdfInfoResponse } from "~/types/api";

const { $api } = useNuxtApp();

interface Props {
  open: boolean;
  file: File | null;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  "select-range": [range: string];
}>();

const loading = ref(false);
const error = ref<string | null>(null);
const pdfInfo = ref<PdfInfoResponse | null>(null);

// Load PDF info when dialog opens
watch(
  () => props.open && props.file,
  async (shouldLoad) => {
    if (!shouldLoad || !props.file) {
      pdfInfo.value = null;
      error.value = null;
      return;
    }

    loading.value = true;
    error.value = null;

    try {
      const formData = new FormData();
      formData.append("file", props.file);

      const response = (await $api("/v1/admin/rag/documents/pdf-info", {
        method: "POST",
        body: formData,
      })) as PdfInfoResponse;

      pdfInfo.value = response;
    } catch (e: any) {
      error.value = e?.message || "Failed to analyze PDF";
    } finally {
      loading.value = false;
    }
  },
  { immediate: true }
);

const formatFileSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const close = () => emit("update:open", false);
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle class="flex items-center gap-2">
          <FileText class="h-5 w-5" />
          PDF Information
        </DialogTitle>
        <DialogDescription>
          {{ file?.name || "PDF file" }}
        </DialogDescription>
      </DialogHeader>

      <div class="py-4">
        <!-- Loading state -->
        <div v-if="loading" class="flex items-center justify-center py-8">
          <Loader2 class="text-muted-foreground h-6 w-6 animate-spin" />
          <span class="text-muted-foreground ml-2">Analyzing PDF...</span>
        </div>

        <!-- Error state -->
        <div v-else-if="error" class="text-destructive flex items-center gap-2 py-4">
          <AlertCircle class="h-5 w-5" />
          <span>{{ error }}</span>
        </div>

        <!-- PDF info -->
        <div v-else-if="pdfInfo" class="space-y-3">
          <div class="grid grid-cols-2 gap-3 text-sm">
            <div class="space-y-1">
              <div class="text-muted-foreground">Page count</div>
              <div class="font-medium">{{ pdfInfo.page_count }} pages</div>
            </div>
            <div class="space-y-1">
              <div class="text-muted-foreground">File size</div>
              <div class="font-medium">{{ formatFileSize(pdfInfo.file_size_bytes) }}</div>
            </div>
          </div>

          <div class="flex flex-wrap gap-2">
            <Badge v-if="pdfInfo.has_text" variant="outline" class="text-green-600">
              Contains text
            </Badge>
            <Badge v-else variant="outline" class="text-orange-600"> Scanned (may need OCR) </Badge>
            <Badge v-if="pdfInfo.is_encrypted" variant="destructive"> Encrypted </Badge>
          </div>

          <div v-if="pdfInfo.title || pdfInfo.author" class="text-muted-foreground text-sm">
            <div v-if="pdfInfo.title">Title: {{ pdfInfo.title }}</div>
            <div v-if="pdfInfo.author">Author: {{ pdfInfo.author }}</div>
          </div>

          <!-- Quick page range suggestions -->
          <div v-if="pdfInfo.page_count > 50" class="border-t pt-2">
            <div class="text-muted-foreground mb-2 text-sm">Quick page range:</div>
            <div class="flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                @click="
                  emit('select-range', '1-50');
                  close();
                "
              >
                First 50 pages
              </Button>
              <Button
                v-if="pdfInfo.page_count > 100"
                variant="outline"
                size="sm"
                @click="
                  emit('select-range', '1-100');
                  close();
                "
              >
                First 100 pages
              </Button>
              <Button
                variant="outline"
                size="sm"
                @click="
                  emit('select-range', `1-${pdfInfo.page_count}`);
                  close();
                "
              >
                All {{ pdfInfo.page_count }} pages
              </Button>
            </div>
          </div>
        </div>
      </div>

      <DialogFooter>
        <Button variant="outline" @click="close">Close</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
