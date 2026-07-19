---
type: Reference
title: "LLMWikiNG MCP Server — Integration & Tool Reference"
description: "Complete guide to embedding the LLMWikiNG MCP (Model Context Protocol) server into Antigravity agy, Claude Desktop, Cursor, OpenCode, and other agents, plus a per-tool reference with copy-paste prompts. Replace the example host/keys with your own."
tags: [mcp, okf, opencode, agy, integration, reference, ai-agent]
timestamp: "2026-07-19T20:05:00Z"
author: "LLMWikiNG Documentation"
status: AI-Generated
---

# LLMWikiNG MCP Server — Integration & Tool Reference

This page explains exactly how to connect the LLMWikiNG **MCP (Model Context Protocol)** server to AI coding agents such as **Antigravity `agy`**, **Claude Desktop**, **Cursor**, **OpenCode**, and any other MCP-compatible client. It also documents **every one of the 31 MCP tools** with ready-to-use prompts you can paste into your agent so it reads from and writes to your wiki automatically.

LLMWikiNG speaks the **Open Knowledge Format (OKF v0.1)**: every wiki page is a plain, human-readable Markdown file with a small YAML frontmatter block. That means the AI never works with a proprietary blob — it reads and writes normal Markdown, and you can open every page in any editor.

> [!NOTE]
> **Placeholders in this guide:** Replace `<host>:<port>` with your server's address and `X-MCP-Key` / `X-API-Key` with your own credentials. The example values shown here are **illustrative only** — never paste real keys into a wiki page that others can read.

---

## Inhaltsverzeichnis

1. [What the MCP server gives your agent](#1-what-the-mcp-server-gives-your-agent)
2. [Prerequisites](#2-prerequisites)
3. [Connect Antigravity `agy` (and Antigravity IDE)](#3-connect-antigravity-agy-and-antigravity-ide)
4. [Connect Claude Desktop](#4-connect-claude-desktop)
5. [Connect Cursor (and other SSE clients)](#5-connect-cursor-and-other-sse-clients)
6. [Copy-paste "self-configuration" prompt](#6-copy-paste-self-configuration-prompt)
7. [How agents use the wiki automatically (workflows)](#7-how-agents-use-the-wiki-automatically-workflows)
8. [Full tool reference](#8-full-tool-reference)
9. [OKF v0.1 page format](#9-okf-v01-page-format)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. What the MCP server gives your agent

Once connected, your agent can:
*   **Read** any wiki page, raw source, or the knowledge graph.
*   **Write / update** pages in OKF format (with correct frontmatter).
*   **Search** the wiki (full-text + semantic via `qmd`).
*   **Ingest** text, files, and URLs into the wiki.
*   **Manage** wikis, users, API keys, and run system operations.

The agent does this by calling **MCP tools** over an **SSE** (Server-Sent Events) channel. You do not write HTTP code — you just configure the client once, and then talk to the wiki in natural language.

---

## 2. Prerequisites

1.  LLMWikiNG is running and reachable at its base path (default `/LLMWikiNG`). The MCP endpoints are:
    *   SSE channel: `http://<host>:<port>/LLMWikiNG/mcp/sse`
    *   Message channel: `http://<host>:<port>/LLMWikiNG/mcp/messages`
2.  You have two keys:
    *   **MCP Key** (`X-MCP-Key`) — set in `config.json` as `llmwiking_mcp_key`.
    *   **API Key** (`X-API-Key`) — a normal user API key (create one under *Settings → Users / API Keys*).
3.  The MCP server is enabled (`ENABLE_MCP_SERVER=true`, the default).

> [!IMPORTANT]
> **Security:** Create a **dedicated low-privilege user + API key** for each agent instead of reusing the admin key. This isolates the agent's permissions and produces a clean, audited action log.

---

## 3. Connect Antigravity `agy` (and Antigravity IDE)

Both the `agy` CLI and the Antigravity IDE consume MCP servers from a configuration file. Use the **global** file `~/.gemini/antigravity-cli/settings.json` or a **workspace** file `.agents/mcp_config.json`.

Add the following config block (replace `<host>:<port>` and the keys with your own):

```json
{
  "mcpServers": {
    "llmwiking-okf": {
      "type": "sse",
      "url": "http://<host>:<port>/LLMWikiNG/mcp/sse",
      "env": {
        "X-MCP-Key": "YOUR_MCP_KEY",
        "X-API-Key": "YOUR_API_KEY"
      }
    }
  }
}
```

After saving, the tools are available inside `agy`. Example session:
```text
$ agy
> Ingest the URL https://example.com/whitepaper.html into the main wiki as a Reference page titled "Example Whitepaper".
```
`agy` will call `okf_ingest_text` (or `okf_process_pending` after dropping a raw file) and then `okf_system_sync`.

---

## 4. Connect Claude Desktop

Claude Desktop reads MCP servers from its global config file.
*   **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
*   **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add the following config block (replace `<host>:<port>` and the keys with your own):

```json
{
  "mcpServers": {
    "llmwiking-okf": {
      "type": "sse",
      "url": "http://<host>:<port>/LLMWikiNG/mcp/sse",
      "env": {
        "X-MCP-Key": "YOUR_MCP_KEY",
        "X-API-Key": "YOUR_API_KEY"
      }
    }
  }
}
```

---

## 5. Connect Cursor (and other SSE clients)

In Cursor: *Settings → Features → MCP → Add New MCP Server*.

| Field | Value |
| :--- | :--- |
| **Name** | `LLMWikiNG-OKF` |
| **Type** | `SSE` |
| **URL** | `http://<host>:<port>/LLMWikiNG/mcp/sse` |
| **Headers** | `{"X-MCP-Key": "YOUR_MCP_KEY", "X-API-Key": "YOUR_API_KEY"}` |

Any other MCP client that supports the `sse` transport uses the same configuration parameters.

---

## 6. Copy-paste "self-configuration" prompt

Paste this into your agent's chat so it configures itself (adjust the URL and keys as needed):

```text
Configure yourself to use the LLMWikiNG MCP server.
- Transport: SSE
- URL: http://<host>:<port>/LLMWikiNG/mcp/sse
- Send two headers with every request:
    X-MCP-Key: YOUR_MCP_KEY
    X-API-Key: YOUR_API_KEY
In Claude Desktop / agy add it under "mcpServers" in the configuration file.
Once connected, use the okf_* tools to read, search, write and ingest wiki pages in OKF v0.1 format.
```

---

## 7. How agents use the wiki automatically (workflows)

### 7.1 Read data from the wiki
An agent that needs project knowledge just asks in plain language:
> "What does our wiki say about the Rust deployment pipeline?"

The agent calls `okf_search({ query: "Rust deployment pipeline", wiki: "main" })` and then `okf_read_concept` on the best match. Because pages are Markdown, the agent can quote, summarize, or refactor based on them — and you can open the same file yourself.

### 7.2 Ingest a file, URL, or pasted text via a prompt
You do **not** need the terminal. Just tell the agent what to ingest:
> **Prompt A — file:**
> "Ingest the file `./notes/architecture.md` into the `main` wiki as a Concept page titled 'System Architecture'."

> **Prompt B — URL:**
> "Fetch https://docs.python.org/3/library/asyncio.html and ingest the content into the `main` wiki as a Reference page titled 'Python asyncio'."

> **Prompt C — pasted text:**
> "Take the following text and ingest it into the `main` wiki as a Concept page titled 'Meeting Notes 2026-07-19': <paste your text here>"

Under the hood, the agent uses `okf_ingest_text` (for text/URL content) or writes a raw file and calls `okf_process_pending` (for batch ingestion). After ingesting, it runs `okf_system_sync` so the search index and embeddings are up to date.

### 7.3 Keep the wiki in sync
After any write or ingest, ask:
> "Sync the main wiki so the index and embeddings are refreshed."

→ `okf_system_sync({ wiki: "main" })`.

---

## 8. Full tool reference (31 tools)

Each entry shows the tool, what it does, and a **copy-paste prompt** you can give your agent.

### Wikis
*   **`okf_list_wikis`** — List all wikis with metadata.
    > "List all wikis."
*   **`okf_create_wiki`** — Create a new wiki (slug auto-generated).
    > "Create a wiki called 'Project Phoenix'."
*   **`okf_update_wiki`** — Rename / re-describe / re-slug a wiki.
    > "Rename the wiki 'phoenix' to 'Project Phoenix'."
*   **`okf_delete_wiki`** — Delete a wiki (never `main`).
    > "Delete the wiki 'old-draft'."

### Pages
*   **`okf_list_pages`** — List pages in a wiki (with type info).
    > "List all pages in the main wiki."
*   **`okf_read_concept`** — Read a page (frontmatter + Markdown body).
    > "Read the page 'python' from the main wiki."
*   **`okf_write_concept`** — Create or update a page in OKF format.
    > "Create a Reference page 'API Design' in main with tags [api, design] and this content: <text>."
*   **`okf_delete_page`** — Delete a page (system pages protected).
    > "Delete the page 'draft-notes' from main."
*   **`okf_export_page`** — Export a page to `output_docs/`.
    > "Export the page 'python' to a file."

### Ingestion & Raw sources
*   **`okf_list_pending`** — List raw sources waiting for ingest.
    > "What raw files are waiting to be ingested?"
*   **`okf_process_pending`** — Ingest all pending raw sources.
    > "Process all pending raw sources in the main wiki."
*   **`okf_ingest_text`** — Ingest raw text/URL into a wiki.
    > "Ingest this text into main as a Concept titled 'Daily Log': <text>."
    > "Ingest the URL https://example.com/article into main as a Reference."
*   **`okf_read_raw`** — Read a raw source file from `raw/`.
    > "Show me the raw file 'spec.txt'."
*   **`okf_list_raw`** — List all raw source files.
    > "List the raw sources."

### Search & Knowledge
*   **`okf_search`** — Full-text + semantic search across pages.
    > "Search the main wiki for 'deployment pipeline'."
*   **`okf_wiki_stats`** — Wiki statistics (pages, words, types).
    > "Show stats for the main wiki."
*   **`okf_graph`** — Knowledge graph (nodes + edges / links).
    > "Show the knowledge graph of the main wiki."
*   **`okf_lint`** — Wiki health check (orphans, missing links, stale).
    > "Run a lint/health check on the main wiki."

### System
*   **`okf_system_status`** — System status (version, users, wikis).
    > "What's the system status?"
*   **`okf_system_sync`** — Synchronize a wiki (index + embeddings).
    > "Sync the main wiki."
*   **`okf_audit_logs`** — Show audit logs (optionally filtered by action).
    > "Show the audit logs."
*   **`okf_cache_stats`** — Cache statistics.
    > "Show cache stats."
*   **`okf_cache_clear`** — Clear the cache.
    > "Clear the cache."

### Users & API Keys
*   **`okf_list_users`** — List users.
    > "List all users."
*   **`okf_create_user`** — Create a user.
    > "Create a user 'ci-bot' with role 'user'."
*   **`okf_delete_user`** — Delete a user.
    > "Delete the user 'ci-bot'."
*   **`okf_list_api_keys`** — List API keys (no secrets shown).
    > "List API keys."
*   **`okf_create_api_key`** — Create an API key.
    > "Create an API key for user 'ci-bot' named 'ci-key'."
*   **`okf_delete_api_key`** — Delete an API key.
    > "Delete the API key 'ci-key'."

### Updates
*   **`okf_check_update`** — Check GitHub for a newer version.
    > "Is there an update available?"
*   **`okf_run_update`** — Run the Git-based system update.
    > "Run the system update."

---

## 9. OKF v0.1 page format

Every page the agent writes looks like this (you can edit it by hand too):

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

Here begins the free, human-readable Markdown body.
```

Required field: `type` (one of `Concept`, `Reference`, `Playbook`, `API-Doc`, `Trail`, …). The agent sets these automatically when you use `okf_write_concept`.

---

## 10. Troubleshooting

*   **401 Unauthorized** — wrong `X-MCP-Key` or `X-API-Key`. Check `config.json` or regenerate the API key under *Settings → API Keys*.
*   **Connection refused** — check the host/port and that the server is up (`okf_system_status` via the REST API or the Web UI).
*   **Agent can't find the tools** — confirm the MCP block is saved in the correct config file for your client and restart the client.
*   **Ingest seems to do nothing** — run `okf_system_sync` afterwards; search index updates only on sync.

---

*This page is part of the LLMWikiNG source tree and is kept in the `main` wiki so it is always available to both humans and agents.*
