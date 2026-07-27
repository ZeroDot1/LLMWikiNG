#!/usr/bin/env python3
"""
LLMWikiNG – Remote Update via MCP (Model Context Protocol)

Verbindet sich per MCP-SSE zum Remote-Server und ruft okf_run_update auf.

Nutzt den globalen MCP-Key aus der lokalen config.json sowie einen
lokal generierten API-Key (muss auf dem Remote-Server registriert sein).
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Lokales Projekt-Root
PROJECT_ROOT = Path(__file__).resolve().parent

# Konfiguration aus config.json laden
config_path = PROJECT_ROOT / "config.json"
try:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    MCP_KEY = config.get("llmwiking_mcp_key", "")
except Exception as e:
    print(f"❌ Konnte config.json nicht lesen: {e}")
    sys.exit(1)

if not MCP_KEY:
    print("❌ Kein MCP-Key in config.json gefunden (llmwiking_mcp_key)")
    sys.exit(1)

REMOTE_URL = "http://192.168.2.247:44419/LLMWikiNG/mcp"
SSE_URL = f"{REMOTE_URL}/sse"

# Versuche einen API-Key aus den lokalen API-Keys zu entschlüsseln
def get_api_key_from_local():
    """Versucht einen lokal gespeicherten API-Key zu entschlüsseln."""
    try:
        from core.security import decrypt_api_key
        from core.storage import list_keys
        keys = list_keys()
        for k in keys:
            if k.get("encrypted_key"):
                raw = decrypt_api_key(k["encrypted_key"])
                if raw:
                    return raw
        return None
    except Exception as e:
        print(f"  ⚠ Entschlüsselung der API-Keys fehlgeschlagen: {e}")
        return None

async def main():
    print(f"🌐 Verbinde zu Remote MCP-Server: {SSE_URL}")
    print(f"🔑 MCP-Key: {MCP_KEY[:20]}...")

    # MCP-Key und API-Key aus Kommandozeilen-Argumenten
    mcp_key = MCP_KEY
    api_key = None
    
    if len(sys.argv) >= 3:
        mcp_key = sys.argv[1]
        api_key = sys.argv[2]
        print(f"🔑 MCP-Key aus Argument: {mcp_key[:20]}...")
        print(f"🔑 API-Key aus Argument: {api_key[:15]}...")
    elif len(sys.argv) == 2:
        api_key = sys.argv[1]
        print(f"🔑 MCP-Key aus config.json: {mcp_key[:20]}...")
        print(f"🔑 API-Key aus Argument: {api_key[:15]}...")
    else:
        api_key = get_api_key_from_local()
        if api_key:
            print(f"🔑 MCP-Key aus config.json: {mcp_key[:20]}...")
            print(f"🔑 API-Key lokal entschlüsselt: {api_key[:15]}...")
        else:
            print("❌ Kein API-Key gefunden.")
            print("")
            print("Nutze: python3 update_remote_mcp.py [<MCP-Key>] <API-Key>")
            print("")
            print("Beispiel: python3 update_remote_mcp.py mcp_DEIN_KEY llmw_DEIN_API_KEY")
            sys.exit(1)

    try:
        from mcp.client.session import ClientSession
        from mcp.client.sse import sse_client
    except ImportError as e:
        print(f"❌ MCP-Client-Bibliothek nicht verfügbar: {e}")
        print("   Bitte installieren: pip install mcp")
        sys.exit(1)

    headers = {
        "X-MCP-Key": mcp_key,
        "X-API-Key": api_key,
    }

    print("\n🔄 Baue SSE-Verbindung auf...")
    try:
        async with sse_client(
            url=SSE_URL,
            headers=headers,
            timeout=30,
        ) as (read, write):
            async with ClientSession(read, write) as session:
                print("✅ Verbindung hergestellt!")
                
                # Zuerst das Update prüfen (okf_check_update)
                print("\n🔍 Prüfe Update-Status...")
                try:
                    check_result = await session.call_tool("okf_check_update")
                    for content_item in check_result.content:
                        if hasattr(content_item, 'text'):
                            print(content_item.text)
                        else:
                            print(str(content_item))
                except Exception as e:
                    print(f"  ⚠ check_update fehlgeschlagen: {e}")
                
                # Update ausführen
                print("\n🚀 Führe Update aus (okf_run_update)...")
                try:
                    result = await session.call_tool("okf_run_update")
                    print("\n📋 Update-Ergebnis:")
                    print("=" * 60)
                    for content_item in result.content:
                        if hasattr(content_item, 'text'):
                            print(content_item.text)
                        else:
                            print(str(content_item))
                    print("=" * 60)
                    print("\n✅ Update erfolgreich ausgeführt!")
                except Exception as e:
                    print(f"\n❌ Update fehlgeschlagen: {e}")
                    import traceback
                    traceback.print_exc()
                    
    except Exception as e:
        print(f"\n❌ Verbindung fehlgeschlagen: {e}")
        print("\nMögliche Ursachen:")
        print("  - Falscher MCP-Key oder API-Key")
        print("  - Remote-Server nicht erreichbar")
        print("  - MCP-Server auf Remote nicht aktiviert")
        print("  - MCP-Key auf Remote ist anders als lokal")
        print("\nTipp: Prüfe den MCP-Key in den Einstellungen des Remote-Servers:")
        print("  http://192.168.2.247:44419/LLMWikiNG/settings")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
