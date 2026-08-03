/* LLMWikiNG – Copyright (C) 2026 ZeroDot1
 * Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */
// settings.js – tab switching + SMTP preset helper for settings.html
(function () {
  "use strict";

  function init() {
    var tabs = document.querySelectorAll(".settings-tab");
    var panels = {
      "tab-language": document.getElementById("tab-language"),
      "tab-theme": document.getElementById("tab-theme"),
      "tab-config": document.getElementById("tab-config"),
      "tab-users": document.getElementById("tab-users"),
      "tab-apikeys": document.getElementById("tab-apikeys"),
      "tab-health": document.getElementById("tab-health"),
      "tab-update": document.getElementById("tab-update"),
      "tab-backup": document.getElementById("tab-backup"),
      "tab-wikis": document.getElementById("tab-wikis"),
      "tab-audit": document.getElementById("tab-audit"),
      "tab-mcp": document.getElementById("tab-mcp"),
      "tab-matrix": document.getElementById("tab-matrix")
    };

    function switchTab(id) {
      Object.keys(panels).forEach(function (k) { if (panels[k]) panels[k].classList.add("hidden"); });
      tabs.forEach(function (t) {
        t.classList.remove("border-primary", "text-text");
        t.classList.add("border-transparent", "text-text-muted");
      });
      if (panels[id]) panels[id].classList.remove("hidden");
      tabs.forEach(function (t) {
        if (t.dataset.tab === id) {
          t.classList.add("border-primary", "text-text");
          t.classList.remove("border-transparent", "text-text-muted");
        }
      });
    }

    tabs.forEach(function (t) {
      t.addEventListener("click", function () { switchTab(t.dataset.tab); });
    });

    var params = new URLSearchParams(window.location.search);
    var map = {
      language: "tab-language",
      theme: "tab-theme",
      config: "tab-config",
      users: "tab-users",
      apikeys: "tab-apikeys",
      health: "tab-health",
      update: "tab-update",
      backup: "tab-backup",
      wikis: "tab-wikis",
      audit: "tab-audit",
      mcp: "tab-mcp",
      matrix: "tab-matrix"
    };
    switchTab(map[params.get("tab")] || "tab-language");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
