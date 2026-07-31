---
description: Speichert die Tailscale-Konfiguration.
---

Rufe das MCP-Tool `okf_tailscale_save` auf, um die Tailscale-Konfiguration zu speichern.

Parameter:
- hostname: Hostname (optional, z. B. llmwiking)
- auth_key: Tailscale-Auth-Key (optional)
- app_port: App-Port (optional, Standard 8080)
- proxy_target: Proxy-Ziel (optional)
- funnel_port: Funnel-Port (optional, Standard 443)
- funnel_enabled: Funnel aktivieren (optional, true/false)
- serve_enabled: Serve aktivieren (optional, true/false)
- extra_args: Zusätzliche Tailscale-Argumente (optional)
