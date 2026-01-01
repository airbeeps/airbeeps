import MarkdownIt from "markdown-it";
import hljs from "highlight.js";
// @ts-expect-error markdown-it-texmath has no type declarations
import tm from "markdown-it-texmath";
import katex from "katex";
import { useI18n } from "vue-i18n";

const encodeAttr = (value: string) => encodeURIComponent(value);

interface MarkdownPreviewTranslations {
  svgPreviewButton: string;
  svgPreviewTooltip: string;
  svgPreviewTitle: string;
  svgPreviewTab: string;
  svgCodeTab: string;
  svgDownloadButton: string;
  svgDownloadTooltip: string;
  copyButton: string;
  copyButtonCopied: string;
  collapseButton: string;
  expandButton: string;
}

const markdownTranslations: MarkdownPreviewTranslations = {
  svgPreviewButton: "Preview SVG",
  svgPreviewTooltip: "Preview SVG",
  svgPreviewTitle: "SVG Preview",
  svgPreviewTab: "Preview",
  svgCodeTab: "Code",
  svgDownloadButton: "Download SVG",
  svgDownloadTooltip: "Download SVG",
  copyButton: "Copy",
  copyButtonCopied: "Copied",
  collapseButton: "Collapse",
  expandButton: "Expand",
};

const buttonBaseClass =
  "inline-flex items-center justify-center rounded-md px-2 py-1 text-xs font-medium text-gray-400 hover:text-gray-200 hover:bg-white/10 transition-colors gap-1";
const iconClass = "w-3.5 h-3.5 pointer-events-none";

interface RenderMarkdownOptions {
  defaultSvgPanel?: "preview" | "code";
}

let currentRenderOptions: RenderMarkdownOptions | undefined;

const md: MarkdownIt = new MarkdownIt({
  html: false,
  xhtmlOut: true,
  breaks: true,
  linkify: true,
  typographer: true,
  highlight: function (str: string, lang?: string): string {
    const normalizedLang = (lang || "").toLowerCase();
    const codeBlockId = `code-block-${Math.random().toString(36).slice(2, 10)}`;
    const containsSvgTag = /<svg[\s>]/i.test(str);
    const showSvgPreview =
      containsSvgTag &&
      (normalizedLang.includes("svg") || normalizedLang === "html" || normalizedLang === "xml");
    const panelContainerId = `${codeBlockId}-panels`;
    const initialPanel = currentRenderOptions?.defaultSvgPanel ?? "preview";
    const isPreviewActive = initialPanel === "preview";
    const isCodeActive = initialPanel === "code";

    const downloadButton = showSvgPreview
      ? `<button type="button" class="${buttonBaseClass}" title="${md.utils.escapeHtml(markdownTranslations.svgDownloadTooltip)}" aria-label="${md.utils.escapeHtml(markdownTranslations.svgDownloadTooltip)}" data-preview-download="svg" data-svg-content="${encodeAttr(str)}" data-download-name="${encodeAttr("preview.svg")}"><svg class="${iconClass}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v10"/><polyline points="8 11 12 15 16 11"/><path d="M5 19h14"/></svg><span>Download</span></button>`
      : "";

    // Use data attributes for copy functionality - handled by event delegation in Message.vue
    const copyButton = `<button type="button" class="${buttonBaseClass} code-copy-btn" title="${md.utils.escapeHtml(markdownTranslations.copyButton)}" aria-label="${md.utils.escapeHtml(markdownTranslations.copyButton)}" data-copy-label="${encodeAttr(markdownTranslations.copyButton)}" data-copied-label="${encodeAttr(markdownTranslations.copyButtonCopied)}" data-action="copy-code"><svg class="${iconClass}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg><span class="copy-text">${md.utils.escapeHtml(markdownTranslations.copyButton)}</span></button>`;

    const headerActions = `<div class="flex items-center gap-1">${downloadButton}${copyButton}</div>`;

    const displayLang = lang || "text";

    const buildCodeBlock = (codeHtml: string) => {
      const svgControls = showSvgPreview
        ? `<div class="svg-inline-toolbar flex flex-wrap items-center justify-between gap-2 px-4 py-2 bg-[#1a1a1a] border-b border-zinc-800"><div class="inline-flex items-center gap-2"><button type="button" class="preview-tab" data-state="${isPreviewActive ? "active" : "inactive"}" data-preview-toggle="preview" data-preview-panels="${panelContainerId}">${md.utils.escapeHtml(markdownTranslations.svgPreviewTab)}</button><button type="button" class="preview-tab" data-state="${isCodeActive ? "active" : "inactive"}" data-preview-toggle="code" data-preview-panels="${panelContainerId}">${md.utils.escapeHtml(markdownTranslations.svgCodeTab)}</button></div></div>`
        : "";
      const svgPanels = showSvgPreview
        ? `<div id="${panelContainerId}" class="code-preview-panels" data-active-panel="${initialPanel}" data-preview-default="${initialPanel}" data-preview-streaming="code" data-preview-final="preview"><div class="preview-panel" data-panel="preview" style="display:${isPreviewActive ? "block" : "none"}"><div class="svg-preview-frame bg-white dark:bg-zinc-900 rounded-lg border border-zinc-200 dark:border-zinc-700 p-4 m-3 flex items-center justify-center"><img src="data:image/svg+xml;utf8,${encodeURIComponent(str)}" alt="${md.utils.escapeHtml(markdownTranslations.svgPreviewTitle)}" class="max-w-full max-h-[360px] object-contain" loading="lazy" /></div></div><div class="preview-panel" data-panel="code" style="display:${isCodeActive ? "block" : "none"}">${codeHtml}</div></div>`
        : codeHtml;
      return `<div class="code-block-container not-prose rounded-lg overflow-hidden my-2 bg-[#0d0d0d] shadow-sm border border-black/10 dark:border-white/10"><div class="code-block-header flex items-center justify-between px-4 py-2 bg-[#202123] dark:bg-[#202123] border-b border-white/5"><span class="text-xs font-sans text-zinc-400 font-medium lowercase select-none">${displayLang}</span>${headerActions}</div><div id="${codeBlockId}" class="code-block-body" data-collapsed="false">${svgControls}${svgPanels}</div></div>`;
    };

    if (lang && hljs.getLanguage(lang)) {
      try {
        const highlighted = hljs.highlight(str, { language: lang });
        const highlightedHtml = `<pre class="hljs px-4 py-4 overflow-x-auto text-sm leading-relaxed m-0 !bg-transparent font-mono"><code class="language-${lang} !bg-transparent">${highlighted.value}</code></pre>`;
        return buildCodeBlock(highlightedHtml);
      } catch {
        // Fallback to plain code block if highlighting fails
      }
    }

    const fallbackHtml = `<pre class="px-4 py-4 overflow-x-auto text-sm leading-relaxed m-0 bg-transparent font-mono"><code class="text-zinc-200">${md.utils.escapeHtml(str)}</code></pre>`;
    return buildCodeBlock(fallbackHtml);
  },
});

// Ensure tm is the correct plugin function (handle CommonJS/ESM interop)
const texmath = tm.default || tm;

md.use(texmath, {
  engine: katex,
  delimiters: "dollars",
  katexOptions: { macros: { "\\RR": "\\mathbb{R}" } },
});

md.use(texmath, {
  engine: katex,
  delimiters: "brackets",
  katexOptions: { macros: { "\\RR": "\\mathbb{R}" } },
});

export const useMarkdown = () => {
  const { t } = useI18n();

  const syncTranslations = () => {
    markdownTranslations.svgPreviewButton = t("chat.preview.svgButton");
    markdownTranslations.svgPreviewTooltip = t("chat.preview.svgButtonTooltip");
    markdownTranslations.svgPreviewTitle = t("chat.preview.svgTitle");
    markdownTranslations.svgPreviewTab = t("chat.preview.previewTab");
    markdownTranslations.svgCodeTab = t("chat.preview.codeTab");
    markdownTranslations.svgDownloadButton = t("chat.preview.downloadButton");
    markdownTranslations.svgDownloadTooltip = t("chat.preview.downloadTooltip");
    markdownTranslations.copyButton = t("common.copy");
    markdownTranslations.copyButtonCopied = t("common.copied");
    markdownTranslations.collapseButton = t("common.collapse");
    markdownTranslations.expandButton = t("common.expand");
  };

  const renderMarkdown = (content: string, options?: RenderMarkdownOptions): string => {
    syncTranslations();
    if (!content) return "";
    currentRenderOptions = options;
    const rendered = md.render(content);
    currentRenderOptions = undefined;
    return rendered;
  };

  return {
    renderMarkdown,
  };
};
