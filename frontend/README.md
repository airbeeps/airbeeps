# Airbeeps Frontend

A Nuxt 3 + Vue 3 + TypeScript SPA for Airbeeps.

## Features

- Auth with email verification and optional OAuth providers (toggle via `AIRBEEPS_ENABLE_OAUTH_PROVIDERS`).
- Assistant catalog: public/private, categories/tags, pinning, translations, avatars.
- Real-time chat: SSE streaming, citations, image uploads, auto titles, shareable links, agent + RAG-aware prompts per assistant.
- Admin consoles: dashboards, assistants (translations, MCP/tools), knowledge bases/documents/chunks, models/providers, OAuth providers, files, system configs, conversations/users.
- Knowledge base utilities: document previews, Excel/CSV row preview, dedup status visibility.
- Responsive UI, dark/light mode, i18n-ready (EN bundled) using shadcn-vue + Tailwind.

## Environment

- `AIRBEEPS_API_BASE_URL`: Backend API base used by the dev proxy (`http://localhost:8500/api` default).
- `AIRBEEPS_APP_NAME`: Browser title (default `Airbeeps`).
- `AIRBEEPS_ENABLE_OAUTH_PROVIDERS`: Show/hide OAuth buttons (default `true`).

## Setup

```bash
# npm / pnpm / yarn / bun
npm install    # or pnpm install / yarn install / bun install
```

## Development

```bash
npm run dev    # or pnpm dev / yarn dev / bun run dev
# serves at http://localhost:3000 with /api proxied to AIRBEEPS_API_BASE_URL
```

## Routes (high level)

- `/`, `/sign-in`, `/sign-up`, `/verify-email`, `/forgot-password`, `/reset-password`
- `/assistants`
- `/chat/:assistantId` and `/chat/:assistantId/:conversationId`
- `/share/:shareId` (public conversation share view)
- `/privacy`, `/terms`
- Admin: `/admin`, `/admin/assistants` (+ `/create`, `/:id`, `/:id/translations`), `/admin/kbs`, `/admin/models`, `/admin/model-providers`, `/admin/oauth-providers`, `/admin/system-config`, `/admin/users`, `/admin/conversations`

## Backend expectations

- Talks to the FastAPI backend at `AIRBEEPS_API_BASE_URL` (`/api/v1`): auth (email + OAuth + refresh), assistants (list/pin/create/update), chat SSE at `/chat`, files upload + public URLs, RAG document preview/search, and admin endpoints for models/providers/kbs/system-config/conversations/users.
- SSE streaming requires the dev proxy (already configured in `nuxt.config.ts`).

## Production

```bash
npm run build   # or pnpm build / yarn build / bun run build
npm run preview # optional local preview
```

See Nuxt deployment docs for hosting details.
