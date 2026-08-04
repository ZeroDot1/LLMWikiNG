/* LLMWikiNG – Copyright (C) 2026 ZeroDot1 | AGPL-3.0-or-later | SPDX-License-Identifier: AGPL-3.0-or-later */
/* JS für den Settings-Tab "AI Integration" */

(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var msgEl = document.getElementById("ai-msg");
    var dockerNoteEl = document.getElementById("ai-docker-note");
    var saveStatusEl = document.getElementById("ai-save-status");

    // Nach einem Redirect (?ai_msg=…) die Speicher-Meldung anzeigen
    var params = new URLSearchParams(window.location.search);
    var aiMsg = params.get("ai_msg");
    if (aiMsg && msgEl) {
      msgEl.textContent = aiMsg;
      msgEl.classList.add("visible");
      window.setTimeout(function () {
        msgEl.classList.remove("visible");
      }, 5000);
    }

    // Konfiguration + Tool-Verfügbarkeit vom Backend laden
    var basePath = window.LLMWIKI_BASE_PATH || "";
    fetch(basePath + "/settings/ai-config/json", { credentials: "same-origin" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        if (dockerNoteEl) {
          if (data.docker) {
            dockerNoteEl.classList.add("visible");
          } else {
            dockerNoteEl.classList.remove("visible");
          }
        }
        var availability = data.availability || {};
        Object.keys(availability).forEach(function (key) {
          var statusEl = document.getElementById("ai-status-" + key);
          if (!statusEl) return;
          if (data.docker && availability[key]) {
            statusEl.textContent = dockerLabel();
            statusEl.className = "ai-tool-status ai-docker";
          } else if (availability[key]) {
            statusEl.textContent = foundLabel();
            statusEl.className = "ai-tool-status ai-ok";
          } else {
            statusEl.textContent = notFoundLabel();
            statusEl.className = "ai-tool-status ai-missing";
          }
        });
      })
      .catch(function () {
        // JSON-Endpunkt nicht verfügbar – Status-Anzeige still überspringen
      });

    function dockerLabel() {
      var el = document.getElementById("ai-label-docker");
      return el ? el.textContent : "Docker";
    }
    function foundLabel() {
      var el = document.getElementById("ai-label-ok");
      return el ? el.textContent : "OK";
    }
    function notFoundLabel() {
      var el = document.getElementById("ai-label-missing");
      return el ? el.textContent : "Nicht gefunden";
    }

    var form = document.getElementById("ai-config-form");
    if (form) {
      form.addEventListener("submit", function () {
        if (saveStatusEl) {
          saveStatusEl.textContent = savingLabel();
        }
      });
    }

    function savingLabel() {
      var el = document.getElementById("ai-label-saving");
      return el ? el.textContent : "Speichern …";
    }
  });
})();