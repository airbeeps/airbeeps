import { defineStore } from "pinia";

/**
 * Store for persisting chat preferences like model selection and web search toggle
 * across page navigations.
 */
export const useChatPreferencesStore = defineStore("chatPreferences", () => {
  // Per-session model override (null means use assistant default)
  const selectedModelId = ref<string | null>(null);

  // Per-session web search toggle state
  const webSearchEnabled = ref(false);

  const setSelectedModelId = (modelId: string | null) => {
    selectedModelId.value = modelId;
  };

  const setWebSearchEnabled = (enabled: boolean) => {
    webSearchEnabled.value = enabled;
  };

  const clearPreferences = () => {
    selectedModelId.value = null;
    webSearchEnabled.value = false;
  };

  return {
    selectedModelId,
    webSearchEnabled,
    setSelectedModelId,
    setWebSearchEnabled,
    clearPreferences,
  };
});
