import { FetchError } from "ofetch";
import { isBackendConnectionError, useBackendStore } from "~/stores/backend";
import { isPublicRoute } from "~/utils/publicRoutes";

export default defineNuxtPlugin(() => {
  const backendStore = useBackendStore();

  let isRefreshing = false;
  let refreshPromise: Promise<void> | null = null;

  const DEFAULT_GET_TIMEOUT_MS = 8000;
  const DEFAULT_TIMEOUT_MS = 30000;

  const applyTimeoutDefaults = (options?: any) => {
    const method = (options?.method || "GET").toString().toUpperCase();
    const isStream = options?.responseType === "stream";

    if (options?.timeout !== undefined) return options;
    if (isStream) return options;

    const timeout = method === "GET" ? DEFAULT_GET_TIMEOUT_MS : DEFAULT_TIMEOUT_MS;
    return { ...options, timeout };
  };

  const markBackend = (error?: unknown) => {
    if (!error) {
      backendStore.setOnline();
      return;
    }

    if (isBackendConnectionError(error)) {
      backendStore.setOffline(error);
      return;
    }

    // If we got a response, the backend is reachable even if the request errored.
    if (error instanceof FetchError && error.response) {
      backendStore.setOnline();
    }
  };

  const redirectToSignIn = async () => {
    const router = useRouter();
    const currentRoute = router.currentRoute.value;
    if (!isPublicRoute({ name: currentRoute.name?.toString() })) {
      await navigateTo("/sign-in");
    }
  };

  // Get cookies
  const getAuthHeaders = () => {
    if (import.meta.server) {
      const accessToken = useCookie("access-token");
      const refreshToken = useCookie("refresh-token");
      const headers: Record<string, string> = {};

      if (accessToken.value) {
        headers["Cookie"] = `access-token=${accessToken.value}`;
        if (refreshToken.value) {
          headers["Cookie"] += `; refresh-token=${refreshToken.value}`;
        }
      }
      return headers;
    }
    return {};
  };

  const refreshToken = async () => {
    if (!isRefreshing) {
      const performRefresh = async () => {
        try {
          await $fetch(
            "/api/v1/auth/refresh",
            applyTimeoutDefaults({
              method: "POST",
              credentials: "include",
              headers: getAuthHeaders(),
            })
          );
          backendStore.setOnline();
        } catch (error) {
          markBackend(error);

          // Clear user state to prevent middleware from re-triggering API calls
          const userStore = useUserStore();
          userStore.clearUser();

          // Use navigateTo instead of window.location.replace to avoid infinite loop
          await redirectToSignIn();
          throw error;
        } finally {
          isRefreshing = false;
          refreshPromise = null;
        }
      };

      isRefreshing = true;
      refreshPromise = performRefresh();
    }
    return refreshPromise;
  };

  const api = async <T = any>(url: string, options?: any): Promise<T> => {
    try {
      const headers = {
        ...getAuthHeaders(),
        ...options?.headers,
      };

      const requestOptions = applyTimeoutDefaults({
        ...options,
        baseURL: "/api",
        credentials: "include",
        headers,
      });

      const result = await $fetch<T>(url, requestOptions);
      backendStore.setOnline();
      return result;
    } catch (error: any) {
      markBackend(error);

      // If it's 401 and not the refresh endpoint
      if (error.response?.status === 401 && !url.includes("/auth/refresh")) {
        try {
          // Refresh token
          await refreshToken();
          // Retry original request
          const headers = {
            ...getAuthHeaders(),
            ...options?.headers,
          };
          const requestOptions = applyTimeoutDefaults({
            ...options,
            baseURL: "/api",
            credentials: "include",
            headers,
          });
          const result = await $fetch<T>(url, requestOptions);
          backendStore.setOnline();
          return result;
        } catch (refreshError) {
          // If refresh fails, throw original error
          throw error;
        }
      }
      // Throw other errors directly
      throw error;
    }
  };

  return {
    provide: {
      api,
    },
  };
});
