export default defineNuxtRouteMiddleware(async (to, from) => {
  const userStore = useUserStore();
  const backendStore = useBackendStore();

  // If backend is offline, allow unauthenticated users to continue
  // without blocking on `/users/me`.
  if (backendStore.isOffline) {
    return;
  }

  // If user state is not initialized, try to fetch user info first
  if (!userStore.user && !userStore.loading) {
    await userStore.fetchUser();

    if (userStore.verificationRequired) {
      return navigateTo("/verify-email");
    }
  }

  // If user is already logged in, redirect to home page
  if (userStore.user) {
    return navigateTo("/chat");
  }

  // Unauthenticated users can continue to access
});
