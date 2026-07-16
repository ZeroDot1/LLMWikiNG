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
*   **🕸️ Interactive Knowledge Graph**: Visualizes all relationships of your pages in a color-coded, dynamic 2D network (fully offline — custom dependency-free Canvas engine, no external libraries). Contradictions/conflicts are shown in red dashed lines.
*   **📰 Weekly Reports & Email Briefings**: Aggregate weekly changes, generate new briefing files in the wiki, and send them securely via the integrated SMTP client to your recipients. Configuration is done via the web interface (saved in `config.json`) with integrated quick presets for **Gmail**, **ProtonMail Bridge**, and **Mail.ru**.
*   **⏳ Pending Ingest**: Shows un-ingested files in `raw/` and allows ingesting them individually or as a batch ("Ingest All") via the web interface.
*   **📥 Netzwerk- & Web-Ingest**: 
    - **Web-Interface**: Bequemer Upload, URL-Import, Text-Paste oder URL-Merkzettel in `ingestlater.md`.
    - **Direkter Netzwerk-Ingest (API)**: Ermöglicht das vollautomatische Hochladen und sofortige Verarbeiten von Quelltexten, URLs oder Dateien aus der Ferne direkt über das Netzwerk. Du kannst Dokumente via curl oder Client-Skript einsenden, die dann sofort KI-Zusammenfassungen erhalten und OKF-konform in das gewünschte Wiki integriert werden.
*   **📤 Export Management**: View all exported documents in the browser, read them rendered, or download them directly.
*   **🔍 Search with Term Highlighting**: Lightning-fast BM25 search across the entire wiki, raw files, and exports with colored highlights in the text.
*   **🏥 Web Linter**: Shows orphaned pages, stale pages (staleness), broken raw-source references (Raw File Refs), and open link references sorted by their importance (frequency).
*   **⬇️ Self-Update**: Integrated update function — checks for new GitHub versions and updates itself with one click. Protects wiki pages, raw sources, and configuration.
*   **⚙️ Settings**: Central configuration page with tabs for language selection, **Appearance (Dark/Light)**, **User Management**, **API-Key Management** (mit sicherer **API-Key Recovery** nach Passwortverifizierung), SMTP email configuration, health check, and update function.
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
*   `/api-keys/reveal` – **API-Key Recovery**: Sichert nach Passworteingabe die Entschlüsselung und Anzeige existierender Keys im Web-Interface.
*   `/wikis/new` – Create a new wiki via the web UI.
*   `/wiki/<name>/` – Wiki home page (`index.md` of the wiki).
*   `/wiki/<name>/<page>` – Rendered Markdown view of a wiki page with backlinks/trail.
*   `/wiki/<name>/<page>/export` – Copies the page to `output_docs/`.
*   `/wiki/<name>/<page>/delete` – Deletes the page.
*   `/raw`, `/raw/<filename>` – Raw source management.
*   `/pending`, `/pending/ingest/<filename>`, `/pending/ingest-all` – Pending ingest.
*   `/export`, `/export/<filename>` – Export management.
*   `/graph` – Interactive knowledge graph (custom Canvas engine, no external libs).
*   `/graph/data?wiki=<name>` – Graph data as JSON.
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
Upon registration, a **default API key** is automatically generated for the user, which is displayed in plaintext once.
After initial setup, self-registration is automatically disabled to protect the system. The administrator can re-enable or disable registration at any time in the **Settings** (`/settings` -> checkbox "Allow registration of new users"). Additional users and API keys can be managed directly in the administration.

All functions are also accessible via a **JSON API** under `/LLMWikiNG/api/v1`,
protected by **API keys** (`X-API-Key` header). A key can optionally
require that an additional password (`X-API-Password`) is sent:

#### Direkter Netzwerk-Ingest per curl:
Um ein Dokument aus der Ferne in das Wiki `main` zu ingestieren und per Vektor-Index zu synchronisieren:
```bash
# Hochladen einer Markdown-Datei ohne Passwort-Erzwingung:
curl -X POST \
  -H "X-API-Key: llmw_dein_api_key_hier" \
  -F "file=@/pfad/zu/dokument.md" \
  "http://192.168.2.170:8082/LLMWikiNG/wiki/main/api/ingest"
```

| Method | Path | Protection |
|---------|------|--------|
| `GET`  | `/api/v1/wikis` | API key |
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
| `GET`  | `/api/v1/users` | API key (admin) |
| `POST` | `/api/v1/users` | API key (admin) |
| `DELETE` | `/api/v1/users/<id>` | API key (admin) |
| `GET`  | `/api/v1/api-keys` | API key (admin) |
| `POST` | `/api/v1/api-keys` | API key (admin) |
| `DELETE` | `/api/v1/api-keys/<id>` | API key (admin) |
| `POST` | `/wiki/<wiki>/api/ingest` | API key (direct ingest for a specific wiki) |
| `POST` | `/wiki/<wiki>/api/sync` | API key (direct sync for a specific wiki) |

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
├── main.py                 # create_app() + main() (argparse, uvicorn), mounts all routers
├── web.py                  # Jinja2Templates, render(), abort/redirect, base_context()
├── core/
│   ├── config.py           # BASE_PATH, paths, multi-wiki (wikis/<name>), i18n
│   ├── security.py         # Argon2 hashing, signed sessions, API-key management
│   └── storage.py          # JSON store for users & API keys (data/)
├── api/
│   ├── deps.py             # get_current_user, require_login, require_admin, get_api_user
│   └── routes/
│       ├── pages.py        # ALL HTML routes (under BASE_PATH)
│       ├── auth.py         # /login, /logout, /users, /api-keys
│       └── api.py          # /api/v1/* (JSON, key-protected)
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

To secure your installation, you should change the default secret. We have provided a simple script for this:

```bash
./change_secret.sh
```

**What does the script do?**
It generates a new, completely random secret and automatically writes it into your `docker-compose.yml`. After that, simply restart your containers (`docker compose down && docker compose up -d`).

> [!WARNING]
> If you change the secret, already generated API keys can no longer be decrypted. You must recreate them once in the web interface after the change.

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
