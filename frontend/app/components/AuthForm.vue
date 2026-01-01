<script setup lang="ts">
import { cn } from "@/lib/utils";
import { FetchError } from "ofetch";
import type { OAuthProvider } from "~/types/api";
import { toast } from "vue-sonner";
import { useRoute } from "vue-router";

const props = defineProps<{
  scene: "sign-in" | "sign-up";
  redirectUrl?: string;
}>();

const { $api } = useNuxtApp();

// Form data
const formData = reactive({
  email: "",
  password: "",
});

// State management
const loading = ref(false);
const error = ref("");
const success = ref("");

const { t } = useI18n();
const { locale } = useI18n();
const route = useRoute();

const signup = async () => {
  if (!formData.email || !formData.password) {
    error.value = t("auth.fillAllFields");
    return;
  }

  loading.value = true;
  error.value = "";
  success.value = "";

  try {
    // Get current language and normalize (en-US -> en)
    const userLanguage = locale.value.split("-")[0];

    // Register user (do not auto-login; ask user to sign in explicitly)
    await $api("/v1/auth/register", {
      method: "POST",
      body: {
        email: formData.email,
        password: formData.password,
        language: userLanguage, // Pass user language preference
      },
    });

    // Redirect to sign-in with a success message and pre-filled email.
    await navigateTo({
      path: "/sign-in",
      query: {
        email: formData.email,
        registered: "1",
        redirect: props.redirectUrl || undefined,
      },
    });
    return;
  } catch (err) {
    if (!(err instanceof FetchError)) throw err;
    if (err.statusCode === 400 && err.data?.detail === "REGISTER_USER_ALREADY_EXISTS") {
      // User already exists, prompt user to login
      error.value = t("auth.emailAlreadyExists");
      return;
    }

    // Other errors
    error.value = t("auth.registrationFailed");
  } finally {
    loading.value = false;
  }
};

const getRedirectPath = () => {
  const fallback = "/chat";
  return props.redirectUrl && props.redirectUrl.length > 0 ? props.redirectUrl : fallback;
};

// Login
const login = async () => {
  loading.value = true;
  error.value = "";
  success.value = "";

  try {
    const body = new URLSearchParams({
      username: formData.email,
      password: formData.password,
    });
    const response = await $api("/v1/auth/login", {
      method: "POST",
      body,
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
    });

    // Redirect after successful login
    await navigateTo(getRedirectPath());
  } catch (err: unknown) {
    if (!(err instanceof FetchError)) throw err;

    if (err.statusCode === 400 && err.data?.detail === "LOGIN_USER_NOT_VERIFIED") {
      return await navigateToVerifyEmail();
    } else if (err.statusCode === 400 && err.data?.detail === "LOGIN_BAD_CREDENTIALS") {
      // Bad credentials or the user is inactive
      error.value = t("auth.invalidCredentials");
      return;
    }
    error.value = t("auth.loginFailed");
  } finally {
    loading.value = false;
  }
};

const navigateToVerifyEmail = async () => {
  await navigateTo(`/verify-email?email=${encodeURIComponent(formData.email)}`);
};

// Handle form submission
const handleSubmit = async () => {
  if (props.scene === "sign-up") {
    // Sign up mode
    await signup();
  } else {
    // Sign in mode
    await login();
  }
};

const socialLoginLoadingProvider = ref<string | null>(null);

// Social login
const handleSocialLogin = (provider: string) => {
  if (socialLoginLoadingProvider.value) return; // Prevent duplicate clicks

  socialLoginLoadingProvider.value = provider;
  const callbackUrl = window.location.origin + getRedirectPath();
  // Redirect to social login provider
  $api<{ authorization_url: string }>(`/v1/oauth/${provider}/authorize`, {
    method: "POST",
    body: {
      redirect_uri: callbackUrl,
    },
  })
    .then((res) => {
      if (res.authorization_url) {
        window.location.href = res.authorization_url;
        // Keep loading state on successful redirect, do not clear
      } else {
        toast.error(t("auth.gettingAuthUrl"));
        socialLoginLoadingProvider.value = null;
      }
    })
    .catch(() => {
      toast.error(t("auth.gettingAuthUrl"));
      socialLoginLoadingProvider.value = null;
    });
};

// Toggle mode
const toggleMode = () => {
  const redirectQuery = props.redirectUrl ? { redirect: props.redirectUrl } : undefined;
  if (props.scene === "sign-in") {
    navigateTo({ path: "/sign-up", query: redirectQuery });
  } else {
    navigateTo({ path: "/sign-in", query: redirectQuery });
  }
};

const configStore = useConfigStore();

const loadingConfig = computed(() => !configStore.isLoaded);

const { data: authProviders } = useAPI<OAuthProvider[]>("/v1/oauth/providers");

const isFormValid = computed(() => {
  const email = formData.email?.trim();
  const password = formData.password?.trim();
  if (!email || !password) {
    return false;
  }
  return true;
});

onMounted(() => {
  // Prefill email on sign-in after a successful registration
  if (props.scene === "sign-in") {
    const qEmail = route.query.email;
    if (typeof qEmail === "string" && qEmail.length > 0) {
      formData.email = qEmail;
    }

    const registered = route.query.registered;
    if (registered === "1" || registered === "true") {
      success.value = t("auth.registrationSuccess");
    }
  }
});
</script>

<template>
  <form @submit.prevent="handleSubmit" :class="cn('flex flex-col gap-6')" autocomplete="off">
    <div class="flex flex-col items-center gap-2 text-center">
      <h1 class="text-2xl font-bold">
        {{ props.scene === "sign-up" ? $t("auth.signUpTitle") : $t("auth.signInTitle") }}
      </h1>
      <p class="text-muted-foreground text-sm text-balance"></p>
    </div>

    <!-- Error message -->
    <div v-if="error" class="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-600">
      {{ error }}
    </div>

    <!-- Success message -->
    <div
      v-if="success"
      class="rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-700"
    >
      {{ success }}
    </div>

    <!-- Loading state -->
    <div v-if="loadingConfig" class="flex justify-center py-4">
      <div class="border-primary h-6 w-6 animate-spin rounded-full border-b-2"></div>
    </div>

    <div v-else class="grid gap-6">
      <!-- Social login -->
      <template v-if="authProviders && authProviders.length > 0">
        <div class="space-y-2">
          <Button
            v-for="provider in authProviders || []"
            :key="provider.id"
            type="button"
            :disabled="!!socialLoginLoadingProvider"
            variant="outline"
            class="h-12 w-full text-base"
            @click="handleSocialLogin(provider.name)"
          >
            <div
              v-if="socialLoginLoadingProvider === provider.name"
              class="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
            />
            <img
              v-else-if="provider.icon_url"
              :src="provider.icon_url"
              alt="icon"
              class="mr-2 h-4 w-4 rounded"
            />
            {{
              $t(
                props.scene === "sign-up" ? "auth.signUpWithProvider" : "auth.signInWithProvider",
                { provider: provider.display_name }
              )
            }}
          </Button>
        </div>

        <div
          class="after:border-border relative text-center text-sm after:absolute after:inset-0 after:top-1/2 after:z-0 after:flex after:items-center after:border-t"
        >
          <span class="bg-background text-muted-foreground relative z-10 px-2">
            {{ $t("common.or") }}
          </span>
        </div>
      </template>

      <!-- Regular sign in/sign up form -->
      <template v-if="!(props.scene === 'sign-up' && !configStore?.config.registration_enabled)">
        <div class="space-y-4">
          <div class="grid gap-2">
            <Label for="email">{{ $t("auth.email") }}</Label>
            <Input
              id="email"
              v-model="formData.email"
              type="email"
              :placeholder="$t('auth.emailPlaceholder')"
              required
              autocomplete="email"
              class="h-12 text-base"
            />
          </div>
          <div class="grid gap-2">
            <div class="flex items-center justify-between">
              <Label for="password">{{ $t("auth.password") }}</Label>
              <NuxtLink
                v-if="props.scene === 'sign-in'"
                to="/forgot-password"
                class="text-muted-foreground hover:text-primary text-xs underline-offset-4 hover:underline"
              >
                {{ $t("auth.forgotPassword") }}
              </NuxtLink>
            </div>
            <Input
              id="password"
              v-model="formData.password"
              type="password"
              required
              autocomplete="new-password"
              class="h-12 text-base"
            />
          </div>

          <!-- Show terms agreement when signing up -->
          <div
            v-if="props.scene === 'sign-up' && configStore?.config.ui_show_signup_terms"
            class="text-muted-foreground text-center text-xs"
          >
            <i18n-t keypath="auth.agreeTerms" tag="span">
              <template #terms>
                <NuxtLink to="/terms" target="_blank" class="text-primary hover:underline">
                  {{ $t("auth.termsOfUse") }}
                </NuxtLink>
              </template>
              <template #privacy>
                <NuxtLink to="/privacy" target="_blank" class="text-primary hover:underline">
                  {{ $t("auth.privacyPolicy") }}
                </NuxtLink>
              </template>
            </i18n-t>
          </div>

          <Button type="submit" class="h-12 w-full text-base" :disabled="loading || !isFormValid">
            {{
              loading
                ? $t("common.processing")
                : props.scene === "sign-up"
                  ? $t("auth.signUp")
                  : $t("auth.signIn")
            }}
          </Button>
        </div>
      </template>
    </div>

    <!-- Toggle sign in/sign up -->
    <div
      v-if="!(props.scene === 'sign-in' && !configStore?.config.registration_enabled)"
      class="text-center text-sm"
    >
      {{ props.scene === "sign-up" ? $t("auth.hasAccount") : $t("auth.noAccount") }}
      <button
        type="button"
        @click="toggleMode"
        class="hover:text-primary underline underline-offset-4"
      >
        {{ props.scene === "sign-up" ? $t("auth.signInNow") : $t("auth.signUpNow") }}
      </button>
    </div>
  </form>
</template>

<style scoped></style>
