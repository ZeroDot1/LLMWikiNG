# LLMWikiNG (OKF Edition)

A complete pattern for building and maintaining a personal knowledge base (wiki) following the standardized [Open Knowledge Format (OKF) v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf) (developed by Google Cloud), using local LLMs and agents. Inspired by Andrej Karpathy's LLM-Wiki pattern.

**Author:** ZeroDot1

*A big thank you to [tevsa](https://github.com/tevsa) for the great idea and support!*

---

### 💛 Support this project
I invest a lot of **time, money, and passion** into the development of LLMWikiNG. Since this project is completely open-source, local, and ad-free, any support — no matter how small — helps me tremendously to continue development and implement new features!
If you would like to support my work, feel free to take a look at my **[Amazon wishlist](https://www.amazon.de/hz/wishlist/ls/WRMQJT0MKFEL/)**. Every contribution is greatly appreciated! Thank you!

---

Instead of searching documents ad-hoc via RAG (Retrieval-Augmented Generation) on every query and regenerating knowledge from scratch each time, this system compiles information **once** into a structured, cross-linked Markdown wiki. When new sources arrive, the LLM updates existing pages, adds cross-references, and documents contradictions. Knowledge grows and refines continuously.

---

## 🏗️ Architecture

The project is built on three layers:

1. **Raw sources (`raw/`)**: Immutable original documents (articles, PDFs, notes) that serve as the information base.
2. **The Wiki (`wiki/`)**: A collection of LLM-maintained, interlinked Markdown files with a central index (`index.md`) and a chronological log (`log.md`).
3. **The CLI & configuration**: The control script `wiki.sh` and the agent configuration `.agy.yaml` define the workflow and rules for the LLM agent.

---

## 🛠️ Features & Commands (`wiki.sh`)

The CLI script `wiki.sh` bundles all operations for managing the wiki:

*   `./wiki.sh init` – Initializes the folder structure and creates `index.md` and `log.md`. Also creates a `qmd` search collection.
*   `./wiki.sh ingest <source-file>` – Reads a new source, archives it in `raw/`, generates an AI summary, creates/updates the wiki page, links it in the index, and records it in the log.
*   `./wiki.sh search "<search-term>"` – Performs a token-saving hybrid search (BM25 + vector) via `qmd` (JSON output for agents).
*   `./wiki.sh lint` – Runs a health check (finds orphaned pages, missing links, incomplete pages).
*   `./wiki.sh sync` – Updates the search embeddings for local search and rebuilds the index.
*   `./wiki.sh export <page>` – Exports a page for sharing to `output_docs/`.
*   `./wiki.sh list` – Lists all current wiki pages.
*   `./wiki.sh status` – Shows statistics about the wiki, raw sources, and the LLM backend.
*   `./wiki.sh config` – Shows the current configuration.
*   `./wiki.sh update` – Performs a self-update via GitHub (`git fetch origin && git reset --hard origin/main`).
*   `./wiki.sh reindex` – Rebuilds the BM25 search index.
*   `./wiki.sh help` – Shows the help page with all commands.
*   `./wiki.sh --version` – Outputs the current version number.

---

## 🌐 Web Interface (`run.py` / FastAPI)

In addition to the CLI, the project offers a full-featured, extremely performant web interface in a modern **Tokyo-Night/Newsroom design**:

*   **🏠 Dashboard & Navigation**: Overview of all current wiki pages, statistics, and system state.
*   **✍️ Universal Editor (WYSIWYG & Markdown)**: Integrated dual-mode editor for creating and editing wiki pages and raw sources directly in the browser — with WYSIWYG formatting (bold, italic, lists, quotes, code, links, images) and raw Markdown source mode including YAML frontmatter.
*   **🕸️ Interactive Knowledge Graph**: Visualizes all relationships of your pages in a color-coded, dynamic 2D network (fully offline — custom dependency-free Canvas engine, no external libraries). Optimized for large wikis: **Lazy Loading** (first 200 nodes appear instantly, remaining pages load in the background), **Barnes-Hut O(n log n) physics**, **Viewport Culling**, and **Level-of-Detail rendering** keep the graph smooth even with 1,000+ pages. The graph page features a **node search**, **tag filter bar**, **node detail panel** (connections count + direct page link), **stats overlay**, **zoom buttons**, **fullscreen mode**, and a **wiki switcher** directly in the toolbar. Fully optimized with a dedicated, lightweight stylesheet (`graph.css`) resolving layout glitches and size constraints for icon/emoji assets. Contradictions/conflicts are shown in red dashed lines.
*   **📰 Weekly Reports & Email Briefings**: Aggregate weekly changes, generate new briefing files in the wiki, and send them securely via the integrated SMTP client to your recipients. Configuration is done via the web interface (saved in `config.json`) with integrated quick presets for **Gmail**, **ProtonMail Bridge**, and **Mail.ru**.
*   **⏳ Pending Ingest**: Shows un-ingested files in `raw/` and allows ingesting them individually or as a batch ("Ingest All") via the web interface.
*   **📥 Network & Web Ingest**:
    - **Web Interface**: Convenient upload, URL import, text paste, or URL bookmarking in `ingestlater.md`.
    - **Direct Network Ingest (API)**: Enables fully automated uploading and immediate processing of source texts, URLs, or files remotely over the network. You can submit documents via curl or client scripts, which then immediately receive AI summaries and are integrated OKF-compliant into the desired wiki.
*   **📤 Export Management**: View all exported documents in the browser, read them rendered, or download them directly.
*   **🔍 Search with Term Highlighting**: Lightning-fast BM25 search with a new **Cross-Wiki-Search** feature allowing you to search either a single specific wiki or all wikis at once (selecting "All Wikis" or `wiki=all` parameter). Shows colored highlights, displays matching wiki labels on the results, and supports arrow key navigation.
*   **⬇️ Self-Update**: Integrated update function — checks for new GitHub versions and updates itself with one click. Safely backs up all files, wiki pages, raw sources, database registers, and configurations into `/tmp` beforehand, auto-restoring user data post-update.
*   **⚙️ Settings**: Central configuration page with tabs for language selection, **Appearance (Dark/Light)**, **Wiki Management** (create, edit, delete wikis with responsive table view showing page count, file count, total size, and last modified date per wiki), **User Management**, **API-Key Management** (with secure **API-Key Recovery** after password verification), SMTP email configuration, health check, and update function.
*   **🛡️ Audit Logging**: SQLite-based, per-category toggleable logging system recording all security actions (search, ingest, logins, API-keys, pages, wikis). Captures timestamps, usernames, IPs. Admins can search, filter by category/action, and configure logging globally or individually via the Settings tab. Replace logbuch entirely.
*   **🌗 Appearance**: The theme (Dark/Light) is changed exclusively in the settings (`/settings?tab=theme`) and persisted in `config.json`. Dark mode is the default and is loaded server-side — without a toggle in the sidebar.

### Starting the Web Interface:
The web server runs by default on a modern **Uvicorn ASGI server** (standard post-2026 for maximum performance and competitiveness).

Start the server simply via the starter script:
```bash
./start.sh
```
*   *Development mode with live reload:* `./start.sh -d`
*   *Specific port:* `./start.sh 9090`
*   *Set start language:* `./start.sh --lang en`

Then open `http://localhost:8081` (or the assigned port) in your browser.

### Server Parameters

The web server (`run.py`, FastAPI/uvicorn) can be started directly or via `start.sh` with the following parameters:

| Parameter | Via start.sh | Description |
|-----------|--------------|-------------|
| `--port, -p PORT` | `./start.sh 9090` | Port (default: 8080). `start.sh` automatically searches for the next free port. |
| `--host, -H HOST` | — (always `0.0.0.0`) | Bind address (default: `0.0.0.0`) |
| `--debug, -d` | `./start.sh -d` | Debug mode (Uvicorn with live reload) |
| `--lang, -l CODE` | `./start.sh --lang en` | Start language (e.g. `de`, `en`). Overrides the value from `config.json`. |
| `--reset` | `./start.sh --reset` | **Reset server:** Irreversibly deletes all wiki pages, raw sources, and exports. Resets the wiki to factory state. |
| `--reset -y` | `./start.sh --reset -y` | Perform reset non-interactively (without prompt). |

All parameters can also be passed directly to `run.py`:
```bash
python3 run.py --port 9090 --lang en -d
```

The default language is stored in `config.json` under the key `"language"`:
```json
{
  "language": "de"
}
```
If no `--lang` parameter is passed, the server uses the value from `config.json`. If that is also missing, German (`de`) is used as a fallback.

### 🌐 Web Endpoints (Routes)

All web routes are under the configurable base path **`/LLMWikiNG`**
(bypassable via `LLMWIKI_BASE_PATH`, e.g. for `example.com/LLMWikiNG/wiki/<Name>/`).
Multiple **wikis** are managed under `wikis/<name>/`; the original `wiki/`
is automatically moved to `wikis/main/` on first start.

*   `/` – Dashboard: Overview of all wikis + activity.
*   `/login`, `/logout` – Login (username + password, signed cookie).
*   `/register` – User registration (called on first start for setup).
*   `/users`, `/users/<id>/delete` – User management (admin only).
*   `/api-keys`, `/api-keys/<id>/delete` – API-key management (admin only).
*   `/api-keys/reveal` – **API-Key Recovery**: After password entry, securely decrypts and displays existing keys in the web interface.
*   `/wikis/new` – Create a new wiki via the web UI.
*   `/wiki/<name>/` – Wiki home page (`index.md` of the wiki).
*   `/wiki/<name>/<page>` – Rendered Markdown view of a wiki page with backlinks/trail.
*   `/wiki/<name>/<page>/export` – Copies the page to `output_docs/`.
*   `/wiki/<name>/<page>/delete` – Deletes the page.
*   `/raw`, `/raw/<filename>` – Raw source management.
*   `/pending`, `/pending/ingest/<filename>`, `/pending/ingest-all` – Pending ingest.
*   `/export`, `/export/<filename>` – Export management.
*   `/graph` – Interactive knowledge graph (custom Canvas engine, no external libs).
*   `/graph/data?wiki=<name>` – Complete graph data as JSON (cached in-memory).
*   `/graph/data/paginated?wiki=<name>&page=0&page_size=200&tag=` – Paginated graph data for lazy loading (frontend uses this for wikis of any size).
*   `/ingest` (GET/POST) – Ingest center (upload, URL notes, batch).
*   `/search?q=` – BM25 full-text search with match highlighting.
*   `/lang/<code>` – Language switch (cookie).
*   `/about` – About page.
*   `/admin/status`, `/admin/sync`, `/admin/update`, `/admin/clear-log` – Admin tools.
*   `/status`, `/lint`, `/config`, `/settings`, `/briefings` – Statistics, linter, SMTP, settings, weekly reports.
*   `/edit`, `/edit/preview`, `/edit/save` – ✍️ Universal editor (WYSIWYG & Markdown).

### 🔐 Authentication & API

The web interface is **password-protected** (Argon2 hashes, signed sessions).
On **first start** (when the user database is empty), every request is automatically redirected to `/register` to create the first user as administrator.
Upon registration, a **default API key** is automatically generated for the user. Although warned that keys are only displayed once, administrators can securely decrypt and view their API keys again at any time under **Settings** -> **API-Keys** by verifying their password.
After initial setup, self-registration is automatically disabled to protect the system. The administrator can re-enable or disable registration at any time in the **Settings** (`/settings` -> checkbox "Allow registration of new users"). Additional users and API keys can be managed directly in the administration.

All functions are also accessible via a **JSON API** under `/LLMWikiNG/api/v1`,
protected by **API keys** (`X-API-Key` header) or **session cookies** (automatic
fallback for the web browser). A key can optionally
require that an additional password (`X-API-Password`) is sent:

#### Direct Network Ingest via curl:
To ingest a document remotely into the `main` wiki and sync it with the vector index:
```bash
# Upload a Markdown file without requiring a password:
curl -X POST \
  -H "X-API-Key: llmw_dein_api_key_hier" \
  -F "file=@/path/to/document.md" \
  "http://192.168.2.170:8082/LLMWikiNG/wiki/main/api/ingest"
```

| Method | Path | Protection |
|---------|------|--------|
| `GET`  | `/api/v1/wikis` | API key |
| `POST` | `/api/v1/wikis` | API key (admin) |
| `PUT`  | `/api/v1/wikis/<slug>` | API key (admin) |
| `DELETE` | `/api/v1/wikis/<slug>` | API key (admin) |
| `GET`  | `/api/v1/wikis/<wiki>/pages` | API key |
| `GET`  | `/api/v1/wikis/<wiki>/pages/<slug>` | API key |
| `POST` | `/api/v1/wikis/<wiki>/pages` | API key (+ scope `write`) |
| `POST` | `/api/v1/wikis/<wiki>/pages/<slug>/export` | API key |
| `POST` | `/api/v1/wikis/<wiki>/ingest` | API key (file upload) |
| `GET`  | `/api/v1/wikis/<wiki>/pending` | API key |
| `POST` | `/api/v1/wikis/<wiki>/ingest/process` | API key |
| `GET`  | `/api/v1/graph?wiki=` | API key |
| `GET`  | `/api/v1/search?q=&wiki=` | API key |
| `GET`  | `/api/v1/stats?wiki=` | API key |
| `GET`  | `/api/v1/lint?wiki=` | API key |
| `GET`  | `/api/v1/status` | API key |
| `GET`  | `/api/v1/system/status` | API key (admin) |
| `POST` | `/api/v1/system/sync` | API key (admin) |
| `GET`  | `/api/v1/system/audit` | API key (admin) |
| `GET`  | `/api/v1/system/update/check` | API key (admin) |
| `POST` | `/api/v1/system/update/run` | API key (admin) |
| `GET`  | `/api/v1/users` | API key (admin) |
| `POST` | `/api/v1/users` | API key (admin) |
| `DELETE` | `/api/v1/users/<id>` | API key (admin) |
| `GET`  | `/api/v1/api-keys` | API key (admin) |
| `POST` | `/api/v1/api-keys` | API key (admin) |
| `DELETE` | `/api/v1/api-keys/<id>` | API key (admin) |
| `POST` | `/wiki/<wiki>/api/ingest` | API key (direct ingest for a specific wiki) |
| `POST` | `/wiki/<wiki>/api/sync` | API key (direct sync for a specific wiki) |
| `GET`  | `/mcp/sse` | MCP API key (SSE-Kanal für KI-Agenten) |
| `POST` | `/mcp/messages` | MCP API key (JSON-RPC Nachrichten-Kanal) |

Example:
```bash
curl -H "X-API-Key: llmw_xxx" http://localhost:8080/LLMWikiNG/api/v1/wikis
```

### ✍️ Integrated Editor
The web server has an integrated, split editor:
*   **WYSIWYG mode**: Enables comfortable writing with direct visual formatting (bold, italic, lists, quotes, horizontal rules, links, images, inline code) completely without external JS libraries (pure HTML5 ContentEditable).
*   **Markdown mode**: Offers the ability to edit the Markdown source including YAML frontmatter directly.
*   **Folder switch**: The editor automatically loads and saves files in the appropriate directory (either `wiki/` for active pages or `raw/` for drafts), based on the current mode.

### 🌗 Appearance (Theme)

The appearance (Dark/Light) is controlled **exclusively in the settings** and
persisted in `config.json` (`"theme": "dark"` or `"light"`). Dark mode
is the default and is loaded server-side from `config.json` — there is deliberately
**no** toggle button in the sidebar or header (no flash/FOUC).

*   **Change theme:** `Settings → Appearance` (tab `theme`) → choose Dark/Light.
*   **Directly via API:** `POST /LLMWikiNG/theme/set` (form field `value=dark|light`, login required).
*   **Restore default:** Set the `"theme"` entry in `config.json` to `dark`.

---

## 🤖 Model Context Protocol (MCP) & Open Knowledge Format (OKF)

LLMWikiNG natively implements the **Open Knowledge Format (OKF v0.1)** for AI-assisted knowledge allocation. All pages are saved as open, portable Markdown files with standardized YAML frontmatter. This ensures complete human readability and prevents proprietary vendor lock-in.

### 🔌 Enable & Configure MCP Server

The MCP server is enabled by default. You can configure it in two ways:

1. **Via Web UI (Recommended):** Go to `Settings ➜ MCP` in the Web interface, toggle the server activation state, and define your API Key. This persists settings in `config.json`.
2. **Via Environment Variables:** Set the following variables in your environment before startup:

```bash
# Enable MCP (Default: true)
ENABLE_MCP_SERVER=true

# Set API Key for AI Agents
LLMWIKING_MCP_KEY=your_secure_mcp_key_2026
```

Restart the application. The server now exposes two endpoints:
- **SSE Channel:** `http://localhost:8080/LLMWikiNG/mcp/sse`
- **Message Channel:** `http://localhost:8080/LLMWikiNG/mcp/messages`

### 💻 Client Integration (Cursor, OpenCode & Antigravity `agy`)

The LLMWikiNG MCP server can be used by any standard MCP client. Here are the configuration details for supported environments:

#### 1. Cursor
Add a new server in Cursor under *Settings → Features → MCP*:

| Field | Value |
|------|------|
| Name | LLMWikiNG-OKF |
| Type | SSE |
| URL | `http://localhost:8080/LLMWikiNG/mcp/sse` |
| Headers | `{"X-API-Key": "your_secure_mcp_key_2026"}` |

#### 2. OpenCode
Add the MCP server under the `"mcp"` key in your global (`~/.config/opencode/opencode.json`) or project-level (`opencode.json` in project root) configuration file:

```json
{
  "mcp": {
    "llmwiking-okf": {
      "type": "remote",
      "url": "http://localhost:8080/LLMWikiNG/mcp/sse",
      "enabled": true,
      "environment": {
        "X-API-Key": "your_secure_mcp_key_2026"
      }
    }
  }
}
```

Alternatively, add the server interactively via the terminal:
```bash
opencode mcp add
```

#### 3. Antigravity CLI (`agy`) & Antigravity IDE
Both the `agy` CLI tool and the Antigravity IDE can consume global or local MCP servers.

Add the configuration to your global MCP configuration file `~/.gemini/config/mcp_config.json` (or workspace-specific under `.agents/mcp_config.json`):

```json
{
  "mcpServers": {
    "llmwiking-okf": {
      "type": "sse",
      "url": "http://localhost:8080/LLMWikiNG/mcp/sse",
      "env": {
        "X-API-Key": "your_secure_mcp_key_2026"
      }
    }
  }
}
```
The configured tools will then be automatically available to the agent inside `agy`.

> [!IMPORTANT]
> **Security Recommendation:** It is highly recommended to create a dedicated, low-privilege user account and a specific API key for each AI agent/client (in the WebUI under *Settings ➜ Users / API Keys*) instead of sharing main administrator credentials or using the global config key. This isolates agent permissions and ensures clean, audit-logged actions.

#### 💬 Copy-Paste AI Configuration Prompt
You can copy and paste the following instruction directly into your AI assistant (e.g., Cursor Chat, Claude Code, OpenCode, or agy) to tell it to configure itself:
```text
Please configure yourself to connect to the LLMWikiNG MCP server. The server uses SSE (Server-Sent Events) at URL: http://localhost:8080/LLMWikiNG/mcp/sse. You must include the header 'X-API-Key' set to '<YOUR_AGENT_API_KEY>'. In OpenCode, add it under the 'mcp' section in your config file. In Antigravity (agy), add it under the 'mcpServers' object in your ~/.gemini/config/mcp_config.json file.
```

### 📋 Available MCP Tools (31 Tools)

| Tool | Description |
|------|-------------|
| `okf_list_wikis` | Lists all wikis with metadata |
| `okf_create_wiki` | Creates a new wiki |
| `okf_update_wiki` | Edits name/description/slug of a wiki |
| `okf_delete_wiki` | Deletes a wiki (except main) |
| `okf_list_pages` | Lists all pages in a wiki |
| `okf_read_concept` | Reads an OKF concept (frontmatter + markdown) |
| `okf_write_concept` | Creates/updates an OKF concept |
| `okf_delete_page` | Deletes a wiki page |
| `okf_export_page` | Exports a page to output_docs/ |
| `okf_list_pending` | Lists raw sources waiting for ingest |
| `okf_process_pending` | Processes all pending raw sources |
| `okf_ingest_text` | Ingests raw text into a wiki |
| `okf_search` | Full-text search across wiki pages |
| `okf_wiki_stats` | Shows wiki statistics |
| `okf_graph` | Visualizes the knowledge graph |
| `okf_lint` | Runs a wiki health check |
| `okf_read_raw` | Reads a raw source from raw/ |
| `okf_list_raw` | Lists all raw source files |
| `okf_system_status` | Shows system status |
| `okf_system_sync` | Synchronizes wikis |
| `okf_audit_logs` | Shows system audit logs |
| `okf_cache_stats` | Shows cache statistics |
| `okf_cache_clear` | Clears the cache |
| `okf_list_users` | Lists all users |
| `okf_create_user` | Creates a user |
| `okf_delete_user` | Deletes a user |
| `okf_list_api_keys` | Lists all API keys |
| `okf_create_api_key` | Creates an API key |
| `okf_delete_api_key` | Deletes an API key |
| `okf_check_update` | Checks for update via Git |
| `okf_run_update` | Runs the system update |

### 📄 OKF v0.1 Document Format

Every wiki page follows the Open Knowledge Format:

```markdown
---
type: Concept
title: MCP Architecture 2026
description: Technical specification of the SSE-based protocol
tags: [backend, mcp, security]
timestamp: 2026-07-18T16:43:00Z
author: Agent (Cursor-Dev)
status: AI-Generated
---

# MCP Architektur 2026

Hier beginnt der freie, menschenlesbare Markdown-Textkörper.
```

---

## 🚀 Getting Started

### 1. Install Prerequisites
Make sure the following tools are installed on your system:
*   `bash`, `ripgrep` (`rg`), `jq`
*   [qmd](https://github.com/tobi/qmd) (for local hybrid search)
*   [Ollama](https://ollama.com/) (for local summaries, by default with `llama3.2:3b`)

### 2. Initialize the Wiki
Run the following command in the project directory:
```bash
chmod +x wiki.sh
./wiki.sh init
```

### 3. Add a Source (Ingest)
```bash
./wiki.sh ingest path/to/your/note.md
```

### 4. Reset Server & Workspace (Factory State)
To reset the entire wiki to its shipped state and irreversibly delete all personal pages, raw data, and exports:

**Via CLI (wiki.sh):**
```bash
./wiki.sh reset              # Requires manually typing 'RESET' to confirm
./wiki.sh reset --yes        # Performs the reset non-interactively (without prompt)
```

**Via server starter (start.sh):**
```bash
./start.sh --reset           # Requires manually typing 'RESET' to confirm
./start.sh --reset -y        # Performs the reset non-interactively (without prompt)
```

The reset deletes all files in `wiki/`, `raw/`, and `output_docs/` and recreates `index.md` and `log.md` OKF-compliant. The qmd search collection is also reset.

---

## 🚀 FastAPI Backend (full port of `llmWiki.py`)

The entire application runs **completely on FastAPI** (no more Flask). The
original Flask web server `llmWiki.py` has been removed; all routes,
services, and template helpers have been ported 1:1 to FastAPI. The existing
Jinja2 templates are still used.

### Starting

```bash
pip install -r requirements.txt
./start.sh                 # or: python3 run.py --port 8080
```

*   Web interface: http://localhost:8080
*   View wiki page: http://localhost:8080/wiki/llm-wiki
*   The CLI parameters `--port/-p`, `--host/-H`, `--debug/-d`, `--lang/-l`
    are supported by `run.py` and `start.sh`.

### Structure

```
run.py                      # Entry point (adds backend/ to path, calls main.main)
backend/
├── main.py                 # create_app() + main() (argparse, uvicorn), mounts all routers + MCP
├── web.py                  # Jinja2Templates, render(), abort/redirect, base_context()
├── core/
│   ├── config.py           # BASE_PATH, paths, multi-wiki, i18n, MCP-Config
│   ├── security.py         # Argon2 hashing, signed sessions, API-key management
│   └── storage.py          # JSON store for users & API keys (data/)
├── api/
│   ├── deps.py             # get_current_user, require_login, require_admin, get_api_user
│   └── routes/
│       ├── pages.py        # ALL HTML routes (under BASE_PATH)
│       ├── auth.py         # /login, /logout, /users, /api-keys
│       ├── api.py          # /api/v1/* (JSON, key-protected)
│       └── mcp.py          # MCP-Server (OKF v0.1, SSE-Transport, 31 Tools)
└── services/               # wiki, markdown, search, sync, graph, lint,
                            #   analytics, editor, email_sender (all multi-wiki capable)
templates/                  # Jinja2 templates (Tailwind v4, responsive, dark mode)
static/                     # static assets (css/tailwind-build.css, js/*, graph engine)
wikis/<name>/               # multi-wiki storage (wiki/ → wikis/main/ on migration)
data/                       # users.json, api_keys.json
```

### Frontend (Tailwind CSS v4)

The CSS is built via a CSS-first pipeline (Tailwind v4, `@theme` with oklch design tokens,
dark mode, container-capable):

```bash
cd frontend && npm install && npm run build   # produces static/css/tailwind-build.css
```

`base.html` includes exclusively `static/css/tailwind-build.css`; all
JS is located as ES modules under `static/js/` (app.js, navigation.js, auth.js, editor.js, graph.js …).

## 🐋 Docker & UGreen NAS Deployment

The project provides direct support for Docker and is explicitly optimized for **UGreen NAS (UGOS)** to ensure out-of-the-box compatibility.

### UGreen NAS (UGOS) Setup
When importing the exported image into the UGreen Container Manager, the system automatically detects the pre-defined volumes from the `Dockerfile` and maps them correctly under `volume1/docker/llmwiking`:
* `/app/data` -> `/volume1/docker/llmwiking/data` (user & API-key databases)
* `/app/wikis` -> `/volume1/docker/llmwiking/wikis` (all wiki directories)
* `/app/raw` -> `/volume1/docker/llmwiking/raw` (unprocessed sources)
* `/app/output_docs` -> `/volume1/docker/llmwiking/output_docs` (exported documents)

To run it via Docker Compose on your UGreen NAS, the default paths in `docker-compose.yml` are pre-configured to point directly to these directories.

### Local Development / Alternative Host Setup
If you want to build and run the Docker container locally on another host system, you can use the configurable environment variable `DOCKER_VOLUME_BASE` in the `docker-compose.yml`.

1. Create a local `.env` file in the project root:
   ```bash
   DOCKER_VOLUME_BASE=.
   ```
2. Run your compose setup:
   ```bash
   docker compose up --build
   ```
This will mount the files and folders relative to the current project directory (preventing directory-over-file mount issues with `config.json` on local hosts).

## ⚙️ Configuration

The settings of the LLM backend can be controlled via environment variables or stored directly in the configuration `.agy.yaml`:

```bash
# Example: use a different model or backend
LLM_BACKEND=ollama OLLAMA_MODEL=llama3:8b ./wiki.sh ingest file.md
```

*   `LLM_BACKEND`: `ollama`, `agy`, or `opencode` (default: `ollama`)
*   `OLLAMA_MODEL`: The model to use (default: `llama3.2:3b`)

### 🔑 The Cryptographic Secret (`LLMWIKI_SECRET`)
The system uses a central password (the *secret*) to secure your login sessions (session cookies) and to store your API keys encrypted in the database.

By default, the secret is automatically generated upon the first start of the application and saved persistently in the `config.json` file (under the key `secret_key`). 

To view or rotate this secret, log in as an administrator, navigate to **Settings** -> **Backup & Restore**, enter your password, and select either:
- **Reveal**: To display the active secret in plain text.
- **Regenerate**: To securely generate and persist a new random system secret.

> [!WARNING]
> If you rotate the secret, already generated API keys can no longer be decrypted and active user sessions are terminated. 

#### 📋 Steps to follow after changing the secret:
1. **Re-Login**: All active sessions are immediately invalidated. You will be redirected to the login page. Log back in with your username and password.
2. **Recreate API Keys**: Go to **Settings** -> **API-Keys**. Your old keys will show decryption errors since they were encrypted with the old secret. **Delete all existing keys and create new ones**.
3. **Update Client Scripts**: Update any scripts, cron jobs, or curl integrations that query the API with the newly generated API keys.
4. **Restore Existing Installations**: If you updated a running installation that used a different secret in `docker-compose.yml`, copy the old secret string and paste it into `config.json` under `"secret_key"` (or reveal the new secret in the WebUI and recreate your API keys).

### 📦 Self-Update

The project contains an integrated update function:

```bash
./update.sh            # Full self-update from GitHub
./update.sh --check    # Only check if an update is available
./wiki.sh update       # Update via CLI
```

The update script (Git-based):
- Creates an **automatic backup** before the update
- Runs `git fetch origin` and resets to `origin/main` (`git reset --hard`)
- Automatically stashes local changes (if needed: `git stash pop`)
- Protects **wiki pages (`wiki/`), raw sources (`raw/`), exports (`output_docs/`), SMTP configuration (`config.json`), and LLM settings (`.agy.yaml`)**
- Shows the entire update history in the log

---

## ⚖️ License

This project was created by **ZeroDot1** and is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. You may copy, modify, and distribute the code, but must ensure that when provided over a network (Software as a Service), the modified source code is made available to users free of charge.

Special thanks to [tevsa](https://github.com/tevsa) for the great idea and support in realizing this project. See the [LICENSE](LICENSE) file for more details.
