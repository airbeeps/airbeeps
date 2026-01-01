import { FetchError } from "ofetch";

export type BackendStatus = "unknown" | "online" | "offline";

function formatError(err: unknown): string | null {
  if (!err) return null;
  if (typeof err === "string") return err;
  if (err instanceof Error) return err.message || err.name;
  try {
    return JSON.stringify(err);
  } catch {
    return "Unknown error";
  }
}

export function isBackendConnectionError(err: unknown): boolean {
  if (!err) return false;

  // ofetch network/timeout: FetchError without response
  if (err instanceof FetchError) {
    return !err.response;
  }

  // Browser abort (timeout via AbortController)
  if (err instanceof Error && err.name === "AbortError") {
    return true;
  }

  // Browser network error
  if (err instanceof TypeError && /fetch/i.test(err.message)) {
    return true;
  }

  const anyErr = err as any;
  if (anyErr?.name === "AbortError") return true;
  if (anyErr?.cause?.name === "AbortError") return true;

  return false;
}

export const useBackendStore = defineStore("backend", () => {
  const status = ref<BackendStatus>("unknown");
  const lastError = ref<string | null>(null);
  const lastCheckedAt = ref<number | null>(null);
  const dismissed = ref(false);

  const isOffline = computed(() => status.value === "offline" && !dismissed.value);

  const setOnline = () => {
    status.value = "online";
    lastError.value = null;
    lastCheckedAt.value = Date.now();
    dismissed.value = false;
  };

  const setOffline = (err?: unknown) => {
    status.value = "offline";
    lastError.value = formatError(err);
    lastCheckedAt.value = Date.now();
    dismissed.value = false;
  };

  const dismiss = () => {
    dismissed.value = true;
  };

  const reset = () => {
    status.value = "unknown";
    lastError.value = null;
    lastCheckedAt.value = null;
    dismissed.value = false;
  };

  return {
    status,
    lastError,
    lastCheckedAt,
    isOffline,
    setOnline,
    setOffline,
    dismiss,
    reset,
  };
});
