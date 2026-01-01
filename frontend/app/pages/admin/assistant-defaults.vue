<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { Loader2 } from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { Switch } from "~/components/ui/switch";
import { Textarea } from "~/components/ui/textarea";
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import type { SystemConfigItem, SystemConfigListResponse, Model } from "~/types/api";

const { t } = useI18n();

definePageMeta({
  layout: "admin",
  breadcrumb: "admin.assistantDefaults.breadcrumb",
});

const { showError, showSuccess } = useNotifications();
const { $api } = useNuxtApp();

const GENERATION_KEY = "assistant_generation_defaults";
const RAG_KEY = "assistant_rag_defaults";

const defaultGeneration = () => ({
  temperature: 0.7,
  max_tokens: 2048,
  additional_params_text: "{}",
});

const defaultRag = () => ({
  retrieval_count: 5,
  fetch_k: "" as string | number,
  similarity_threshold: 0.7,
  context_max_tokens: 1200,
  search_type: "similarity",
  mmr_lambda: 0.5,
  skip_smalltalk: false,
  skip_patterns_text: "",
  multi_query: false,
  multi_query_count: 3,
  rerank_top_k: "" as string | number,
  rerank_model_id: "__none__" as string,
  hybrid_enabled: false,
  hybrid_corpus_limit: 1000,
});

const { data, pending, error, refresh } = await useAPI<SystemConfigListResponse>(
  "/v1/admin/config",
  { server: false }
);

const configs = computed<SystemConfigItem[]>(() => data.value?.configs ?? []);
const generationCfg = computed(() => configs.value.find((cfg) => cfg.key === GENERATION_KEY));
const ragCfg = computed(() => configs.value.find((cfg) => cfg.key === RAG_KEY));

// Reranker model list (optional)
const { data: rerankModels } = useAPI<Model[]>("/v1/admin/all-models?capabilities=reranker", {
  server: false,
});

const rerankerOptions = computed(() =>
  (rerankModels.value ?? []).map((m) => ({
    label: m.display_name || m.name || m.id,
    value: m.id,
  }))
);

const generation = ref(defaultGeneration());
const rag = ref(defaultRag());

watch(
  configs,
  () => {
    // Generation defaults
    const g = generationCfg.value?.value as any;
    generation.value = {
      temperature:
        typeof g?.temperature === "number" ? g.temperature : defaultGeneration().temperature,
      max_tokens: typeof g?.max_tokens === "number" ? g.max_tokens : defaultGeneration().max_tokens,
      additional_params_text: JSON.stringify(g?.additional_params ?? {}, null, 2),
    };

    // RAG defaults
    const r = ragCfg.value?.value as any;
    rag.value = {
      retrieval_count:
        typeof r?.retrieval_count === "number" ? r.retrieval_count : defaultRag().retrieval_count,
      fetch_k: r?.fetch_k ?? "",
      similarity_threshold:
        typeof r?.similarity_threshold === "number"
          ? r.similarity_threshold
          : defaultRag().similarity_threshold,
      context_max_tokens:
        typeof r?.context_max_tokens === "number"
          ? r.context_max_tokens
          : defaultRag().context_max_tokens,
      search_type: typeof r?.search_type === "string" ? r.search_type : "similarity",
      mmr_lambda: typeof r?.mmr_lambda === "number" ? r.mmr_lambda : 0.5,
      skip_smalltalk: !!r?.skip_smalltalk,
      skip_patterns_text: Array.isArray(r?.skip_patterns) ? r.skip_patterns.join(", ") : "",
      multi_query: !!r?.multi_query,
      multi_query_count:
        typeof r?.multi_query_count === "number"
          ? r.multi_query_count
          : defaultRag().multi_query_count,
      rerank_top_k: r?.rerank_top_k ?? "",
      rerank_model_id: r?.rerank_model_id ? String(r.rerank_model_id) : "__none__",
      hybrid_enabled: !!r?.hybrid_enabled,
      hybrid_corpus_limit:
        typeof r?.hybrid_corpus_limit === "number"
          ? r.hybrid_corpus_limit
          : defaultRag().hybrid_corpus_limit,
    };
  },
  { immediate: true }
);

const savingGeneration = ref(false);
const savingRag = ref(false);

const parseJsonObject = (text: string) => {
  const trimmed = (text || "").trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed);
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("JSON must be an object");
  }
  return parsed;
};

const parseOptionalInt = (val: any) => {
  if (val === null || val === undefined) return null;
  const str = String(val).trim();
  if (!str) return null;
  const num = Number(str);
  return Number.isFinite(num) ? Math.trunc(num) : null;
};

const parseOptionalFloat = (val: any) => {
  if (val === null || val === undefined) return null;
  const str = String(val).trim();
  if (!str) return null;
  const num = Number(str);
  return Number.isFinite(num) ? num : null;
};

const upsertConfig = async (
  key: string,
  current: SystemConfigItem | undefined,
  value: any,
  description: string
) => {
  const payload = current
    ? { value, is_enabled: true }
    : {
        key,
        value,
        description,
        is_public: false,
        is_enabled: true,
      };

  const url = current ? `/v1/admin/config/${key}` : "/v1/admin/config";
  const method = current ? "PUT" : "POST";
  await $api(url, { method, body: payload });
};

const saveGenerationDefaults = async () => {
  savingGeneration.value = true;
  try {
    const additional_params = parseJsonObject(generation.value.additional_params_text);
    const payload = {
      temperature: Number(generation.value.temperature),
      max_tokens: Number(generation.value.max_tokens),
      additional_params,
    };
    await upsertConfig(
      GENERATION_KEY,
      generationCfg.value,
      payload,
      "Global defaults for assistant generation settings"
    );
    await refresh();
    showSuccess(t("admin.assistantDefaults.messages.saved"));
  } catch (e: any) {
    showError(e?.message || t("admin.assistantDefaults.messages.saveFailed"));
  } finally {
    savingGeneration.value = false;
  }
};

const saveRagDefaults = async () => {
  savingRag.value = true;
  try {
    const skip_patterns = (rag.value.skip_patterns_text || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    const payload = {
      retrieval_count: Number(rag.value.retrieval_count),
      fetch_k: parseOptionalInt(rag.value.fetch_k),
      similarity_threshold: parseOptionalFloat(rag.value.similarity_threshold),
      context_max_tokens: Number(rag.value.context_max_tokens),
      search_type: rag.value.search_type,
      mmr_lambda: Number(rag.value.mmr_lambda),
      skip_smalltalk: !!rag.value.skip_smalltalk,
      skip_patterns,
      multi_query: !!rag.value.multi_query,
      multi_query_count: Number(rag.value.multi_query_count),
      rerank_top_k: parseOptionalInt(rag.value.rerank_top_k),
      rerank_model_id:
        rag.value.rerank_model_id && rag.value.rerank_model_id !== "__none__"
          ? rag.value.rerank_model_id
          : null,
      hybrid_enabled: !!rag.value.hybrid_enabled,
      hybrid_corpus_limit: Number(rag.value.hybrid_corpus_limit),
    };

    await upsertConfig(
      RAG_KEY,
      ragCfg.value,
      payload,
      "Global defaults for assistant RAG retrieval settings"
    );
    await refresh();
    showSuccess(t("admin.assistantDefaults.messages.saved"));
  } catch (e: any) {
    showError(e?.message || t("admin.assistantDefaults.messages.saveFailed"));
  } finally {
    savingRag.value = false;
  }
};
</script>

<template>
  <div class="space-y-6">
    <Alert v-if="error" variant="destructive">
      <AlertTitle>{{ t("common.error") }}</AlertTitle>
      <AlertDescription>
        {{ error?.message || t("admin.assistantDefaults.messages.loadFailed") }}
      </AlertDescription>
    </Alert>

    <!-- Generation Defaults -->
    <Card>
      <CardHeader>
        <CardTitle>{{ t("admin.assistantDefaults.generation.title") }}</CardTitle>
        <CardDescription>
          {{ t("admin.assistantDefaults.generation.description") }}
        </CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div class="space-y-2">
            <Label for="gen-temperature">{{
              t("admin.assistantDefaults.generation.temperature")
            }}</Label>
            <Input
              id="gen-temperature"
              type="number"
              v-model.number="generation.temperature"
              min="0"
              max="2"
              step="0.1"
              :disabled="pending || savingGeneration"
            />
          </div>
          <div class="space-y-2">
            <Label for="gen-max-tokens">{{
              t("admin.assistantDefaults.generation.maxTokens")
            }}</Label>
            <Input
              id="gen-max-tokens"
              type="number"
              v-model.number="generation.max_tokens"
              min="1"
              max="100000"
              :disabled="pending || savingGeneration"
            />
          </div>
        </div>

        <div class="space-y-2">
          <Label for="gen-additional">{{
            t("admin.assistantDefaults.generation.additionalParams")
          }}</Label>
          <Textarea
            id="gen-additional"
            v-model="generation.additional_params_text"
            :rows="8"
            :disabled="pending || savingGeneration"
            class="font-mono text-xs"
          />
          <p class="text-muted-foreground text-xs">
            {{ t("admin.assistantDefaults.generation.additionalParamsHelp") }}
          </p>
        </div>

        <div class="flex gap-2">
          <Button @click="saveGenerationDefaults" :disabled="pending || savingGeneration">
            <Loader2 v-if="savingGeneration" class="mr-2 h-4 w-4 animate-spin" />
            {{ t("common.save") }}
          </Button>
        </div>
      </CardContent>
    </Card>

    <!-- RAG Defaults -->
    <Card>
      <CardHeader>
        <CardTitle>{{ t("admin.assistantDefaults.rag.title") }}</CardTitle>
        <CardDescription>
          {{ t("admin.assistantDefaults.rag.description") }}
        </CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div class="space-y-2">
            <Label for="rag-k">{{ t("admin.assistantDefaults.rag.retrievalCount") }}</Label>
            <Input
              id="rag-k"
              type="number"
              v-model.number="rag.retrieval_count"
              min="1"
              max="50"
              :disabled="pending || savingRag"
            />
          </div>
          <div class="space-y-2">
            <Label for="rag-fetch-k">{{ t("admin.assistantDefaults.rag.fetchK") }}</Label>
            <Input
              id="rag-fetch-k"
              type="number"
              :model-value="rag.fetch_k"
              placeholder="Auto (3x K)"
              :disabled="pending || savingRag"
              @update:modelValue="(v: any) => (rag.fetch_k = v)"
            />
          </div>
          <div class="space-y-2">
            <Label for="rag-threshold">{{
              t("admin.assistantDefaults.rag.similarityThreshold")
            }}</Label>
            <Input
              id="rag-threshold"
              type="number"
              v-model.number="rag.similarity_threshold"
              min="0"
              max="1"
              step="0.01"
              :disabled="pending || savingRag"
            />
          </div>
        </div>

        <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div class="space-y-2">
            <Label for="rag-context-max">{{
              t("admin.assistantDefaults.rag.contextMaxTokens")
            }}</Label>
            <Input
              id="rag-context-max"
              type="number"
              v-model.number="rag.context_max_tokens"
              min="200"
              max="6000"
              :disabled="pending || savingRag"
            />
          </div>

          <div class="space-y-2">
            <Label for="rag-search-type">{{ t("admin.assistantDefaults.rag.searchType") }}</Label>
            <Select v-model="rag.search_type" :disabled="pending || savingRag">
              <SelectTrigger>
                <SelectValue placeholder="similarity" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="similarity">similarity</SelectItem>
                <SelectItem value="mmr">mmr</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div class="space-y-2">
            <Label for="rag-mmr-lambda">{{ t("admin.assistantDefaults.rag.mmrLambda") }}</Label>
            <Input
              id="rag-mmr-lambda"
              type="number"
              v-model.number="rag.mmr_lambda"
              min="0"
              max="1"
              step="0.05"
              :disabled="pending || savingRag"
            />
          </div>
        </div>

        <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div class="space-y-2 rounded-md border p-3">
            <div class="flex items-center space-x-2">
              <Switch
                id="rag-skip-smalltalk"
                :model-value="rag.skip_smalltalk"
                @update:model-value="(v: boolean) => (rag.skip_smalltalk = v)"
                :disabled="pending || savingRag"
              />
              <Label for="rag-skip-smalltalk">
                {{ t("admin.assistantDefaults.rag.skipSmalltalk") }}
              </Label>
            </div>
            <div class="mt-3 space-y-2" v-if="rag.skip_smalltalk">
              <Label for="rag-skip-patterns">{{
                t("admin.assistantDefaults.rag.skipPatterns")
              }}</Label>
              <Input
                id="rag-skip-patterns"
                v-model="rag.skip_patterns_text"
                placeholder="hi, hello, thanks"
                :disabled="pending || savingRag"
              />
            </div>
          </div>

          <div class="space-y-2 rounded-md border p-3">
            <div class="flex items-center space-x-2">
              <Switch
                id="rag-multi-query"
                :model-value="rag.multi_query"
                @update:model-value="(v: boolean) => (rag.multi_query = v)"
                :disabled="pending || savingRag"
              />
              <Label for="rag-multi-query">
                {{ t("admin.assistantDefaults.rag.multiQuery") }}
              </Label>
            </div>
            <div class="mt-3 space-y-2" v-if="rag.multi_query">
              <Label for="rag-multi-query-count">{{
                t("admin.assistantDefaults.rag.multiQueryCount")
              }}</Label>
              <Input
                id="rag-multi-query-count"
                type="number"
                v-model.number="rag.multi_query_count"
                min="1"
                max="5"
                :disabled="pending || savingRag"
              />
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div class="space-y-2 rounded-md border p-3">
            <div class="text-sm font-medium">
              {{ t("admin.assistantDefaults.rag.rerankTitle") }}
            </div>
            <div class="mt-2 grid grid-cols-1 gap-3 md:grid-cols-2">
              <div class="space-y-2">
                <Label for="rag-rerank-top-k">{{
                  t("admin.assistantDefaults.rag.rerankTopK")
                }}</Label>
                <Input
                  id="rag-rerank-top-k"
                  type="number"
                  :model-value="rag.rerank_top_k"
                  placeholder="Optional"
                  :disabled="pending || savingRag"
                  @update:modelValue="(v: any) => (rag.rerank_top_k = v)"
                />
              </div>
              <div class="space-y-2">
                <Label for="rag-rerank-model">{{
                  t("admin.assistantDefaults.rag.rerankModel")
                }}</Label>
                <Select v-model="rag.rerank_model_id" :disabled="pending || savingRag">
                  <SelectTrigger>
                    <SelectValue :placeholder="t('admin.notSet')" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">None</SelectItem>
                    <SelectItem v-for="m in rerankerOptions" :key="m.value" :value="m.value">
                      {{ m.label }}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          <div class="space-y-2 rounded-md border p-3">
            <div class="flex items-center space-x-2">
              <Switch
                id="rag-hybrid"
                :model-value="rag.hybrid_enabled"
                @update:model-value="(v: boolean) => (rag.hybrid_enabled = v)"
                :disabled="pending || savingRag"
              />
              <Label for="rag-hybrid">
                {{ t("admin.assistantDefaults.rag.hybridEnabled") }}
              </Label>
            </div>
            <div class="mt-3 space-y-2" v-if="rag.hybrid_enabled">
              <Label for="rag-hybrid-limit">{{
                t("admin.assistantDefaults.rag.hybridCorpusLimit")
              }}</Label>
              <Input
                id="rag-hybrid-limit"
                type="number"
                v-model.number="rag.hybrid_corpus_limit"
                min="100"
                max="5000"
                :disabled="pending || savingRag"
              />
            </div>
          </div>
        </div>

        <div class="flex gap-2">
          <Button @click="saveRagDefaults" :disabled="pending || savingRag">
            <Loader2 v-if="savingRag" class="mr-2 h-4 w-4 animate-spin" />
            {{ t("common.save") }}
          </Button>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
