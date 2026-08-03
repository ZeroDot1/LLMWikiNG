/* LLMWikiNG – Copyright (C) 2026 ZeroDot1
 * Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */
// auth.js – login form client-side helpers (password visibility toggle + validation)
(function () {
  "use strict";

  function initAuth() {
    const forms = document.querySelectorAll("#loginForm, #registerForm, form");
    forms.forEach((form) => {
      const pass = form.querySelector('input[name="password"]');
      const toggle = form.querySelector("[data-toggle-password]");
      if (toggle && pass && !toggle.dataset.bound) {
        toggle.dataset.bound = "true";
        toggle.addEventListener("change", function () {
          pass.type = toggle.checked ? "text" : "password";
        });
      }

      if ((form.id === "loginForm" || form.id === "registerForm") && !form.dataset.bound) {
        form.dataset.bound = "true";
        form.addEventListener("submit", function (e) {
          const user = form.querySelector('input[name="username"]');
          const pwd = form.querySelector('input[name="password"]');
          if ((!user || !user.value.trim()) || (!pwd || !pwd.value)) {
            e.preventDefault();
          }
        });
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAuth);
  } else {
    initAuth();
  }

})();
