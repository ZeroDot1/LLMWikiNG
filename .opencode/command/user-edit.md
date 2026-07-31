---
description: Bearbeitet einen Systembenutzer (Name, Passwort, Rolle, Status).
---

Rufe das MCP-Tool `okf_update_user` auf, um einen Benutzer zu bearbeiten.

Parameter:
- username: Benutzername (erforderlich)
- new_username: Neuer Benutzername (optional)
- password: Neues Passwort (optional, leer = unverändert)
- role: Neue Rolle (optional, admin/editor/viewer)
- active: Aktivstatus (optional, true/false)

ACHTUNG: Selbst-Deaktivierung, selbst-entzogene Adminrolle und die Entfernung des letzten Administrators sind blockiert.
