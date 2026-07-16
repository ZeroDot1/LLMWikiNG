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
