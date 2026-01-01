<script setup lang="ts">
import { ref, onMounted, watch, computed } from "vue";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Download, X } from "lucide-vue-next";

const props = defineProps<{
  pdfUrl: string;
  initialPage?: number;
  title?: string;
}>();

const emit = defineEmits<{
  close: [];
}>();

const canvasRef = ref<HTMLCanvasElement | null>(null);
const containerRef = ref<HTMLDivElement | null>(null);
const currentPage = ref(props.initialPage || 1);
const totalPages = ref(0);
const scale = ref(1.2);
const loading = ref(true);
const error = ref<string | null>(null);
const pdfDoc = ref<any>(null);

// PDF.js library reference
let pdfjsLib: any = null;

const canGoBack = computed(() => currentPage.value > 1);
const canGoForward = computed(() => currentPage.value < totalPages.value);

async function loadPdfJs() {
  if (typeof window === "undefined") return null;

  try {
    const pdfjs = await import("pdfjs-dist");
    // Set worker source - use unpkg for reliable CDN hosting
    // For pdfjs-dist 5.x, the worker is at build/pdf.worker.min.mjs
    pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;
    return pdfjs;
  } catch (e) {
    console.error("Failed to load PDF.js:", e);
    return null;
  }
}

async function loadPdf() {
  if (!props.pdfUrl) return;

  loading.value = true;
  error.value = null;

  try {
    pdfjsLib = await loadPdfJs();
    if (!pdfjsLib) {
      error.value = "PDF viewer not available";
      return;
    }

    const loadingTask = pdfjsLib.getDocument(props.pdfUrl);
    pdfDoc.value = await loadingTask.promise;
    totalPages.value = pdfDoc.value.numPages;

    // Ensure initial page is valid
    if (currentPage.value > totalPages.value) {
      currentPage.value = 1;
    }

    await renderPage(currentPage.value);
  } catch (e: any) {
    console.error("Failed to load PDF:", e);
    error.value = e.message || "Failed to load PDF";
  } finally {
    loading.value = false;
  }
}

async function renderPage(pageNum: number) {
  if (!pdfDoc.value || !canvasRef.value) return;

  try {
    const page = await pdfDoc.value.getPage(pageNum);
    const viewport = page.getViewport({ scale: scale.value });

    const canvas = canvasRef.value;
    const context = canvas.getContext("2d");
    if (!context) return;

    canvas.height = viewport.height;
    canvas.width = viewport.width;

    const renderContext = {
      canvasContext: context,
      viewport: viewport,
    };

    await page.render(renderContext).promise;
  } catch (e) {
    console.error("Failed to render page:", e);
  }
}

function goToPreviousPage() {
  if (canGoBack.value) {
    currentPage.value--;
    renderPage(currentPage.value);
  }
}

function goToNextPage() {
  if (canGoForward.value) {
    currentPage.value++;
    renderPage(currentPage.value);
  }
}

function zoomIn() {
  scale.value = Math.min(scale.value + 0.2, 3);
  renderPage(currentPage.value);
}

function zoomOut() {
  scale.value = Math.max(scale.value - 0.2, 0.5);
  renderPage(currentPage.value);
}

function downloadPdf() {
  const link = document.createElement("a");
  link.href = props.pdfUrl;
  link.download = props.title || "document.pdf";
  link.target = "_blank";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

function goToPage(page: number) {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page;
    renderPage(currentPage.value);
  }
}

// Watch for page changes from props
watch(
  () => props.initialPage,
  (newPage) => {
    if (newPage && newPage !== currentPage.value) {
      goToPage(newPage);
    }
  }
);

// Watch for URL changes
watch(
  () => props.pdfUrl,
  () => {
    loadPdf();
  }
);

onMounted(() => {
  loadPdf();
});
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- Toolbar -->
    <div class="bg-muted/50 flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
      <div class="flex items-center gap-2">
        <!-- Page navigation -->
        <Button variant="ghost" size="icon" :disabled="!canGoBack" @click="goToPreviousPage">
          <ChevronLeft class="h-4 w-4" />
        </Button>
        <span class="text-sm tabular-nums">
          <input
            type="number"
            :value="currentPage"
            :min="1"
            :max="totalPages"
            class="bg-background w-12 rounded border px-1 py-0.5 text-center text-sm"
            @change="goToPage(Number(($event.target as HTMLInputElement).value))"
          />
          / {{ totalPages }}
        </span>
        <Button variant="ghost" size="icon" :disabled="!canGoForward" @click="goToNextPage">
          <ChevronRight class="h-4 w-4" />
        </Button>
      </div>

      <div class="flex items-center gap-1">
        <!-- Zoom controls -->
        <Button variant="ghost" size="icon" @click="zoomOut">
          <ZoomOut class="h-4 w-4" />
        </Button>
        <span class="text-muted-foreground w-12 text-center text-xs">
          {{ Math.round(scale * 100) }}%
        </span>
        <Button variant="ghost" size="icon" @click="zoomIn">
          <ZoomIn class="h-4 w-4" />
        </Button>

        <!-- Download -->
        <Button variant="ghost" size="icon" @click="downloadPdf" title="Download PDF">
          <Download class="h-4 w-4" />
        </Button>

        <!-- Close -->
        <Button variant="ghost" size="icon" @click="emit('close')" title="Close">
          <X class="h-4 w-4" />
        </Button>
      </div>
    </div>

    <!-- PDF Canvas -->
    <div
      ref="containerRef"
      class="bg-muted/20 flex flex-1 items-start justify-center overflow-auto p-4"
    >
      <div v-if="loading" class="flex items-center justify-center py-20">
        <div
          class="border-primary h-8 w-8 animate-spin rounded-full border-2 border-t-transparent"
        ></div>
      </div>
      <div
        v-else-if="error"
        class="text-destructive flex flex-col items-center justify-center py-20"
      >
        <p class="text-sm">{{ error }}</p>
        <Button variant="outline" size="sm" class="mt-2" @click="loadPdf"> Retry </Button>
      </div>
      <canvas v-show="!loading && !error" ref="canvasRef" class="shadow-lg"></canvas>
    </div>

    <!-- Page indicator badge -->
    <div
      v-if="totalPages > 0"
      class="bg-primary/10 text-primary absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full px-3 py-1 text-xs font-medium"
    >
      Page {{ currentPage }} of {{ totalPages }}
    </div>
  </div>
</template>
