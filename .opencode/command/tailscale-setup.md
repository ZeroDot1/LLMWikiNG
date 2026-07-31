---
description: Fuehrt das Tailscale-One-Click-Setup aus (up + serve/funnel).
---

Rufe das MCP-Tool `okf_tailscale_setup` auf, um Tailscale einzurichten.

Parameter:
- auth_key: Tailscale-Auth-Key (erforderlich)
- hostname: Hostname (optional, Standard llmwiking)
- app_port: App-Port (optional, Standard 8080)
- proxy_target: Proxy-Ziel (optional)
- funnel_enabled: Funnel aktivieren (optional, true/false)
- serve_enabled: Serve aktivieren (optional, Standard true)
- extra_args: Zusätzliche Argumente (optional)

ACHTUNG: Setzt Tailscale up und konfiguriert Serve/Funnel inkl. Zertifikat!
