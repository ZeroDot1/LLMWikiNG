---
description: Dokument direkt in den Matrix-Index einpflegen.
---

Rufe das MCP-Tool `okf_matrix_ingest` auf, um ein Dokument manuell in den Matrix-Index einzupflegen.

Parameter:
- wiki_id: Wiki-Slug (Default: main)
- doc_id: Dokument-Slug (erforderlich)
- title: Titel des Dokuments
- content: Markdown-Inhalt (erforderlich)
- tags: Komma-getrennte Tags

Nutze $ARGUMENTS zur Befüllung der Parameter.
