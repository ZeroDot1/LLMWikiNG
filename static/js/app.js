// app.js – global UI helpers (mobile menu, back-to-top, search shortcut)
(function () {
  "use strict";

  function initMenu() {
    const toggle = document.querySelector("[data-menu-toggle]");
    const menu = document.querySelector("[data-menu]");
    const backdrop = document.querySelector("[data-menu-backdrop]");
    if (!toggle || !menu) return;
    function close() {
      menu.classList.add("hidden");
      if (backdrop) backdrop.classList.add("hidden");
      document.body.classList.remove("overflow-hidden");
    }
    function open() {
      menu.classList.remove("hidden");
      if (backdrop) backdrop.classList.remove("hidden");
      document.body.classList.add("overflow-hidden");
    }
    toggle.addEventListener("click", function () {
      if (menu.classList.contains("hidden")) open();
      else close();
    });
    if (backdrop) backdrop.addEventListener("click", close);
    // Close drawer when a nav link is clicked (mobile)
    menu.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function () {
        if (window.matchMedia("(max-width: 767px)").matches) close();
      });
    });
  }

  function initBackToTop() {
    const btn = document.getElementById("backToTop");
    if (!btn) return;
    window.addEventListener("scroll", function () {
      btn.classList.toggle("visible", window.scrollY > 300);
    });
    btn.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  function initSearchShortcut() {
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "/") {
        e.preventDefault();
        const input = document.querySelector(".search-input");
        if (input) input.focus();
      }
    });
  }

  function initShowLoading() {
    window.showLoading = function (btn) {
      const overlay = document.getElementById("loading-overlay");
      if (!overlay) return;
      if (btn) {
        const form = btn.closest("form");
        if (form && typeof form.checkValidity === "function" && !form.checkValidity()) return;
      }
      overlay.classList.remove("hidden");
    };
  }

  document.addEventListener("DOMContentLoaded", function () {
    initMenu();
    initBackToTop();
    initSearchShortcut();
    initShowLoading();
  });
})();
