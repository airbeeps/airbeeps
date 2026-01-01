# Airbeeps - Assistant-Based RAG System

> **Status**: Alpha  
> APIs, configuration, and behavior may change.


## What is Airbeeps?

Airbeeps is a **self-hosted, local-first assistant-based RAG system** for individuals and small teams who want to build AI assistants on top of their own documents.

You run it yourself, upload your data, and interact with multiple AI assistants backed by your private knowledge base. All data stays on your machine or server.

## Who is this for?

Airbeeps is well suited for:
- Individuals running personal or local AI assistants
- Small teams sharing internal documents
- Internal tools, labs, and early production setups
- Developers who want a hackable, self-hosted RAG system

## Scope

Airbeeps targets local and private deployments, with simple and lightweight authentication suitable for individuals and small teams.


## Current Features

- **Multi-Assistant Platform**: Create multiple assistants with configurable system prompts, model parameters, and knowledge base access
- **RAG Knowledge Base**: Upload documents (PDF, DOCX, TXT, Markdown, Excel, CSV), automatic chunking, vector embedding, and semantic search with citations
- **Real-Time Chat**:  Streaming responses via SSE, conversation history, image attachments, and shareable conversations.
- **Pluggable LLM Providers**: Uses LiteLLM to support OpenAI-compatible APIs, Gemini, and other providers, with configurable embedding models.
- **Basic Admin UI**: Manage users, assistants, models, providers, and system settings.
- **Local Storage**: All data (database, files, vectors) stored locally with no external dependencies

## Planned

- Agent capabilities
- MCP integration
- Improved authentication options
- External object storage support
- Docker-based distribution

See [ROADMAP.md](ROADMAP.md) for details.

---

## 📚 Documentation

- **[Quick Start Guide](docs/QUICKSTART.md)** - Get up and running quickly
- **[Configuration Guide](docs/configuration.md)** - Environment variables and settings
- **[Admin Features](docs/ADMIN_FEATURES.md)** - System settings and UI toggles
- **[Legal Documents](docs/LEGAL_DOCUMENTS.md)** - Setup Terms & Privacy Policy
- **[Development Setup](DEVELOPMENT.md)** - Contributing and local development
- **[Distribution Guide](docs/DISTRIBUTION.md)** - Building and deploying as a package
- **[Roadmap](ROADMAP.md)** - Planned features and future development
- **[Security Policy](SECURITY.md)** - Security best practices and reporting
- **[Contributing](CONTRIBUTING.md)** - How to contribute to the project

---

## 🚀 Quick Start

### Run as an Installed Package

```bash
pip install airbeeps
airbeeps run
```

Open `http://localhost:8500` and sign up - the first user becomes admin.

### For Developers (Local Development)

**Prerequisites**: Python 3.13+, Node.js 20+, pnpm, [uv](https://docs.astral.sh/uv/)

```bash
# Clone repository
git clone https://github.com/airbeeps/airbeeps.git
cd airbeeps

# Backend setup
cd backend
cp .env.example .env          # Copy example config and edit as needed
uv sync --locked              # Install dependencies
uv run scripts/bootstrap.py init  # Initialize database
uv run fastapi dev --port 8500 airbeeps/main.py  # Start backend (http://localhost:8500)

# Frontend setup (in another terminal)
cd frontend
cp .env.example .env          # Copy example config and edit as needed
pnpm install  # Install dependencies
pnpm dev      # Start frontend (http://localhost:3000)
```

Backend runs at `http://localhost:8500`, frontend at `http://localhost:3000`.

See [docs/QUICKSTART.md](docs/QUICKSTART.md) for detailed instructions.

## ❤️ Acknowledgements

Airbeeps builds upon the excellent work of the open-source community. Special thanks to:

**Inspiration & Reference**
- [ChatGPT UI](https://github.com/wongsaang/chatgpt-ui) - Multi-user ChatGPT web interface
- [RiceBall](https://github.com/riceball-ai/riceball) - AI knowledge base & agent platform

**Core Backend**
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [FastAPI Users](https://frankie567.github.io/fastapi-users/) - Authentication system
- [LangChain](https://www.langchain.com/) - LLM orchestration and RAG
- [LiteLLM](https://docs.litellm.ai/) - Unified LLM API client
- [ChromaDB](https://www.trychroma.com/) - Vector database
- [SQLAlchemy](https://www.sqlalchemy.org/) - Database ORM
- [Alembic](https://alembic.sqlalchemy.org/) - Database migrations
- [Pydantic](https://docs.pydantic.dev/) - Data validation

**Core Frontend**
- [Nuxt 3](https://nuxt.com/) - Vue.js framework
- [Vue 3](https://vuejs.org/) - Progressive JavaScript framework
- [Reka UI](https://reka-ui.com/) - Headless UI components
- [TailwindCSS](https://tailwindcss.com/) - Utility-first CSS framework
- [Pinia](https://pinia.vuejs.org/) - State management
- [VeeValidate](https://vee-validate.logaretm.com/) - Form validation
- [Markdown-it](https://github.com/markdown-it/markdown-it) - Markdown parser

## 🤝 Contributing

We welcome contributions! Please see:

- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines
- [DEVELOPMENT.md](DEVELOPMENT.md) - Development setup and tooling
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) - Community standards
- [SECURITY.md](SECURITY.md) - Security policy and reporting

## 📄 License

This project is licensed under the [MIT License](LICENSE).
