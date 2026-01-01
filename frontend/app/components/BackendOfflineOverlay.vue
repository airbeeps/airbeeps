<script setup lang="ts">
const backendStore = useBackendStore();
const configStore = useConfigStore();
const runtimeConfig = useRuntimeConfig();

const apiBaseUrl = computed(() => runtimeConfig.public.apiBaseUrl as string | undefined);

const retrying = ref(false);

const retry = async () => {
  if (retrying.value) return;
  retrying.value = true;
  try {
    await configStore.loadConfig(true);
  } finally {
    retrying.value = false;
  }
};

const reload = () => {
  window.location.reload();
};
</script>

<template>
  <div
    v-if="backendStore.isOffline"
    class="bg-background/70 fixed inset-0 z-[9999] flex items-center justify-center backdrop-blur"
  >
    <div class="bg-card w-full max-w-xl rounded-lg border p-6 shadow-lg">
      <div class="flex flex-col gap-2">
        <h2 class="text-xl font-semibold">Backend not running</h2>
        <p class="text-muted-foreground text-sm">
          The frontend can't reach the API
          <span v-if="apiBaseUrl" class="font-mono">({{ apiBaseUrl }})</span>. Start the backend,
          then retry or reload this page.
        </p>
      </div>

      <div class="mt-5 space-y-4">
        <div class="space-y-2">
          <div class="text-sm font-medium">Start backend (local)</div>
          <pre
            class="bg-muted overflow-auto rounded-md p-3 text-xs leading-relaxed"
          ><code>cd backend
uv sync --locked
uv run fastapi dev airbeeps/main.py</code></pre>
        </div>

        <div class="flex flex-wrap gap-2">
          <Button :disabled="retrying" @click="retry">
            {{ retrying ? "Retrying…" : "Retry" }}
          </Button>
          <Button variant="outline" @click="reload">Reload</Button>
          <Button variant="ghost" @click="backendStore.dismiss">Dismiss</Button>
        </div>

        <p v-if="backendStore.lastError" class="text-muted-foreground text-xs">
          Last error:
          <span class="font-mono">{{ backendStore.lastError }}</span>
        </p>
      </div>
    </div>
  </div>
</template>
