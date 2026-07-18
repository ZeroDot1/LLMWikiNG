// search.js – Interaktivität auf der Suchseite (Keyboard-Navigation, Shortcuts)
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    const searchInput = document.querySelector(".search-input");
    const resultItems = document.querySelectorAll(".search-result-item");

    // Auto-Fokus auf das Eingabefeld, falls leer
    if (searchInput && !searchInput.value) {
      searchInput.focus();
    }

    // Zusätzlicher Shortcut: "/" Taste fokussiert die Suche (falls kein Textfeld aktiv ist)
    document.addEventListener("keydown", function (e) {
      const active = document.activeElement;
      const isInput = active.tagName === "INPUT" || active.tagName === "TEXTAREA" || active.isContentEditable;
      if (e.key === "/" && !isInput) {
        e.preventDefault();
        if (searchInput) {
          searchInput.focus();
          searchInput.select();
        }
      }
    });

    // Pfeiltasten-Navigation durch Suchergebnisse
    let currentFocus = -1;

    document.addEventListener("keydown", function (e) {
      if (!resultItems || resultItems.length === 0) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        currentFocus++;
        updateFocus(resultItems);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        currentFocus--;
        updateFocus(resultItems);
      } else if (e.key === "Enter" && currentFocus > -1) {
        const activeLink = resultItems[currentFocus].querySelector("a");
        if (activeLink) {
          e.preventDefault();
          activeLink.click();
        }
      }
    });

    function updateFocus(items) {
      removeFocus(items);
      if (currentFocus >= items.length) currentFocus = 0;
      if (currentFocus < 0) currentFocus = items.length - 1;

      const item = items[currentFocus];
      item.classList.add("border-primary", "bg-primary-subtle/10");
      item.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function removeFocus(items) {
      items.forEach(function (item) {
        item.classList.remove("border-primary", "bg-primary-subtle/10");
      });
    }
  });
})();
