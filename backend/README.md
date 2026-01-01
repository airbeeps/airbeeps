# Airbeeps

Airbeeps is a **self-hosted, local-first assistant-based RAG system** for individuals and small teams who want to build AI assistants on top of their own documents.

It is designed to be easy to install, simple to run, and fully under your control.

---

## Features

- 🤖 **Pluggable LLM Providers** via LiteLLM (OpenAI-compatible APIs, Gemini, and more)
- 📚 **RAG Knowledge Base** with document upload and semantic search
- 💬 **Real-Time Chat** with streaming responses
- 🔐 **Lightweight Authentication** for trusted environments
- 🎨 **Web UI Included**
- 📦 **Single-command install & run**

---

## Quick Start

### Installation

```bash
pip install airbeeps
```

### Run

```bash
airbeeps run
```

On first run, Airbeeps initializes its local data and starts the web interface.

Open the UI at: **http://localhost:8500**

The **first registered user becomes an admin**.

---

## Data & Configuration

Airbeeps stores all data locally:

- **Linux / macOS**: `~/.local/share/airbeeps`
- **Windows**: `%APPDATA%\airbeeps`

To change the data location:

```bash
AIRBEEPS_DATA_ROOT=/path/to/data
```

---

## Help & Commands

To see all available commands:

```bash
airbeeps --help
airbeeps run --help
```

---

## Documentation

Full documentation and development guides are available on GitHub:

https://github.com/airbeeps/airbeeps

---

## License

MIT License
