/* LLMWikiNG – Copyright (C) 2026 ZeroDot1
 * Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */
// navigation.js – wiki switcher
(function () {
  "use strict";

  const BASE_PATH = window.BASE_PATH || "";

  function initWikiSwitcher() {
    const switcher = document.querySelector("[data-wiki-switcher]");
    if (!switcher) return;
    switcher.addEventListener("change", function () {
      const value = switcher.value;
      if (value) {
        window.location.href = BASE_PATH + "/wiki/" + encodeURIComponent(value) + "/";
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initWikiSwitcher();
  });
})();
