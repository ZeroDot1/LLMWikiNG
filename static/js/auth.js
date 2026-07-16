// auth.js – login form client-side helpers (password visibility toggle + validation)
(function () {
  "use strict";

  function initLogin() {
    const form = document.getElementById("loginForm");
    if (!form) return;

    const pass = form.querySelector('input[name="password"]');
    const toggle = form.querySelector("[data-toggle-password]");
    if (toggle && pass) {
      toggle.addEventListener("change", function () {
        pass.type = toggle.checked ? "text" : "password";
      });
    }

    form.addEventListener("submit", function (e) {
      const user = form.querySelector('input[name="username"]');
      const pwd = form.querySelector('input[name="password"]');
      if ((!user || !user.value.trim()) || (!pwd || !pwd.value)) {
        e.preventDefault();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initLogin);
  } else {
    initLogin();
  }
})();
