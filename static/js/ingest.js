/* LLMWikiNG – Copyright (C) 2026 ZeroDot1
 * Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */
// ingest.js – tab switching for the ingest page (showLoading is global in app.js)
(function () {
  "use strict";

  window.switchTab = function (tabId, btn) {
    var panels = document.querySelectorAll(".tab-content");
    panels.forEach(function (el) { el.style.display = "none"; });
    var btns = document.querySelectorAll(".tab-btn");
    btns.forEach(function (el) {
      el.classList.remove("border-primary", "text-text");
      el.classList.add("border-transparent", "text-text-muted");
    });
    var target = document.getElementById(tabId);
    if (target) target.style.display = "block";
    if (btn) {
      btn.classList.add("border-primary", "text-text");
      btn.classList.remove("border-transparent", "text-text-muted");
    }
  };
})();
