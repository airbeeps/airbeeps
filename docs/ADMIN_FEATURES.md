# Admin Features Guide

This guide covers the administrative features available in AirBeeps for customizing your deployment.

## System Configuration

Access the admin panel at `/admin/system-config` to control system-wide settings.

### Chat UI Controls

Toggle visibility of chat interface elements:

- **Share Button** - Share entire conversations
- **Message Share** - Share individual messages  
- **Message Feedback** - Thumbs up/down on responses
- **Message Stats** - Token usage and timing info
- **Pin Button** - Pin conversations to top
- **Create Button** - New conversation button
- **Assistant Dropdown** - Switch assistants mid-chat
- **Agent Thinking** - Show reasoning traces
- **Chat Suggestions** - Starter questions on new chat

### Follow-up Questions

- **Generate Follow-ups** - Auto-suggest next questions after responses
- **Question Count** - How many to generate (1-5)

### Authentication & Legal

- **User Registration** - Enable/disable new signups
- **Terms & Privacy Links** - Show legal documents on signup form (only enable if you have proper documents)

### Conversation Titles

Configure how conversation titles are generated:

- **Auto-generate** - Uses first message as title
- **AI Model** - Select a model to generate smart titles

## Assistant Defaults

Set platform-wide defaults at `/admin/assistant-defaults`:

### Generation Settings
- Temperature, max tokens, and other LiteLLM parameters
- Assistants can override these or inherit globals

### RAG Settings
- Retrieval count, similarity threshold, search type
- Multi-query recall, reranking, hybrid search (BM25 + dense)
- Assistants in RAG mode can use these defaults

## Models & Providers

Manage AI providers and models at `/admin/providers` and `/admin/models`:

- Add custom providers (OpenAI-compatible APIs)
- Configure models with capabilities, token limits
- Set model status (active/inactive/deprecated)

## Knowledge Bases

Manage document collections at `/admin/knowledge-bases`:

- Create knowledge bases with custom embedding models
- Upload documents (PDF, TXT, DOCX, etc.)
- Configure chunking strategy (size, overlap)
- Reindex when changing settings

## User Management

View and manage users at `/admin/users`:

- View user list, activity, registration date
- Mark users as active/inactive
- Grant/revoke superuser access

## OAuth Providers

Configure social login at `/admin/oauth-providers`:

- Add Google, GitHub, Microsoft, or custom OAuth providers
- Set client ID/secret, scopes, user mapping
- Customize icon and display name

## Analytics

View usage statistics at `/admin/analytics`:

- Token usage trends
- Request counts
- Response latency
- Daily/weekly breakdowns

## Tips

- **Refresh frontend** after changing public configs to see changes
- **Test toggles** in incognito to verify behavior for new users
- **Keep terms hidden** unless you have proper legal documents
- **Monitor analytics** to optimize model selection and costs
