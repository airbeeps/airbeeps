import type { ConfigResponse, PublicConfig } from "~/types/api";

export const useConfigStore = defineStore("config", () => {
  const config = ref<PublicConfig>({
    registration_enabled: true,
  });

  const isLoaded = ref(false);
  const lastLoadTime = ref<number>(0);
  const CACHE_DURATION = 30000; // 30 seconds cache to reduce API calls

  const loadConfig = async (force = false) => {
    // Check if cache is still valid unless force reload is requested
    const now = Date.now();
    const isCacheValid = isLoaded.value && now - lastLoadTime.value < CACHE_DURATION;

    if (isCacheValid && !force) {
      return;
    }

    try {
      const { $api } = useNuxtApp();
      const response = await $api<ConfigResponse>("/v1/config/public", {
        timeout: 2500,
        // Use browser cache for 30 seconds to align with our internal cache
        cache: "default",
      });
      config.value = response.configs;
      isLoaded.value = true;
      lastLoadTime.value = now;
    } catch {
      // Config loading failed - use defaults
      isLoaded.value = true;
      lastLoadTime.value = now;
    }
  };

  const getConfig = async (): Promise<PublicConfig> => {
    if (!isLoaded.value) {
      await loadConfig();
    }
    return config.value;
  };

  const getConfigValue = async <K extends keyof PublicConfig>(key: K): Promise<PublicConfig[K]> => {
    const configData = await getConfig();
    return configData[key];
  };

  return {
    config,
    isLoaded,
    loadConfig,
    getConfig,
    getConfigValue,
  };
});
