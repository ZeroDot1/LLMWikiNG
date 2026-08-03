/* LLMWikiNG – Copyright (C) 2026 ZeroDot1
 * Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */
// search.js – Interaktivität auf der Suchseite (Keyboard-Navigation, Shortcuts, Tag-Autocomplete)
(function () {
  "use strict";

  // Matrix-Volltextsuche (SQLite-Shards) – asynchrone Suche über die REST-API.
  // Die Standard-Suche wird serverseitig gerendert; dieser Helfer ermöglicht
  // zusätzliche clientseitige Matrix-Suchen (z. B. Live-Nachschlagen).
  window.performMatrixSearch = async function (query, wiki) {
    var base = window.BASE_PATH || "/LLMWikiNG";
    var wikis = (wiki && wiki !== "all") ? wiki : "all";
    var searchTimeEl = document.getElementById("search-time");
    try {
      var url = base + "/api/v1/matrix/search?q=" + encodeURIComponent(query) +
        "&wikis=" + encodeURIComponent(wikis) + "&limit=30";
      var res = await fetch(url);
      if (!res.ok) return null;
      var data = await res.json();
      if (searchTimeEl) {
        searchTimeEl.classList.remove("hidden");
        var n = (data.results || []).length;
        var ms = data.search_time_ms || 0;
        var shards = data.shards_queried || 0;
        searchTimeEl.textContent = n + " Ergebnisse in " + ms + "ms (" + shards + " Shards)";
      }
      return data;
    } catch (e) {
      return null;
    }
  };

  document.addEventListener("DOMContentLoaded", function () {
    const searchInput = document.querySelector(".search-input");
    const resultItems = document.querySelectorAll(".search-result-item");
    const autocompleteBox = document.getElementById("search-autocomplete");

    // Auto-Fokus auf das Eingabefeld, falls leer
    if (searchInput && !searchInput.value) {
      searchInput.focus();
    }

    // Tag-Autocomplete
    let autocompleteTimer = null;
    let autocompleteFocus = -1;

    if (searchInput && autocompleteBox) {
      const autocompleteUrl = searchInput.dataset.autocomplete || "";

      searchInput.addEventListener("input", function () {
        clearTimeout(autocompleteTimer);
        const val = this.value.trim();

        // Nur nach "#" oder "tag:" suchen
        const tagTrigger = val.match(/(?:^|\s)(?:tag:|#)(\w*)$/);
        if (!tagTrigger) {
          autocompleteBox.classList.add("hidden");
          autocompleteBox.innerHTML = "";
          return;
        }

        const partial = tagTrigger[1];
        if (partial.length < 1) {
          autocompleteBox.classList.add("hidden");
          autocompleteBox.innerHTML = "";
          return;
        }

        autocompleteTimer = setTimeout(function () {
          fetch(autocompleteUrl + "?q=" + encodeURIComponent(partial))
            .then(function (r) { return r.json(); })
            .then(function (data) {
              if (!data.tags || data.tags.length === 0) {
                autocompleteBox.classList.add("hidden");
                return;
              }
              autocompleteFocus = -1;
              var html = "";
              data.tags.forEach(function (t, idx) {
                html += '<div class="px-3 py-2 cursor-pointer hover:bg-primary-subtle/20 text-sm border-b border-border last:border-b-0" data-index="' + idx + '">';
                html += '<span class="text-primary font-mono">#' + t.tag + '</span>';
                html += ' <span class="text-text-muted text-xs">(' + t.count + ')</span>';
                html += "</div>";
              });
              autocompleteBox.innerHTML = html;
              autocompleteBox.classList.remove("hidden");

              // Klick auf Autocomplete-Eintrag
              autocompleteBox.querySelectorAll("[data-index]").forEach(function (el) {
                el.addEventListener("click", function () {
                  var tag = this.querySelector(".font-mono").textContent.replace("#", "");
                  insertTag(tag);
                });
              });
            })
            .catch(function () {
              autocompleteBox.classList.add("hidden");
            });
        }, 200);
      });

      function insertTag(tag) {
        var val = searchInput.value;
        // Ersetze das letzte #partiell oder tag:partial durch tag:tag
        val = val.replace(/(?:^|\s)(?:tag:|#)\w*$/, function (match) {
          if (match.endsWith(":") || match.endsWith("#")) {
            return match + tag;
          }
          return match.replace(/[\w-]+$/, tag);
        });
        searchInput.value = val + " ";
        autocompleteBox.classList.add("hidden");
        autocompleteBox.innerHTML = "";
        searchInput.focus();
      }

      // Tastaturnavigation im Autocomplete
      searchInput.addEventListener("keydown", function (e) {
        var items = autocompleteBox.querySelectorAll("[data-index]");
        if (items.length === 0) return;

        if (e.key === "ArrowDown") {
          e.preventDefault();
          autocompleteFocus++;
          if (autocompleteFocus >= items.length) autocompleteFocus = 0;
          updateAutocompleteFocus(items);
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          autocompleteFocus--;
          if (autocompleteFocus < 0) autocompleteFocus = items.length - 1;
          updateAutocompleteFocus(items);
        } else if (e.key === "Enter" && autocompleteFocus > -1) {
          e.preventDefault();
          items[autocompleteFocus].click();
        } else if (e.key === "Escape") {
          autocompleteBox.classList.add("hidden");
          autocompleteFocus = -1;
        }
      });

      function updateAutocompleteFocus(items) {
        items.forEach(function (el, idx) {
          if (idx === autocompleteFocus) {
            el.classList.add("bg-primary-subtle/20");
          } else {
            el.classList.remove("bg-primary-subtle/20");
          }
        });
      }
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

    // Pfeiltasten-Navigation durch Suchergebnisse (nur wenn Autocomplete nicht aktiv)
    let currentFocus = -1;

    document.addEventListener("keydown", function (e) {
      if (!resultItems || resultItems.length === 0) return;
      if (!autocompleteBox.classList.contains("hidden")) return;

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

    // Click outside closes autocomplete
    document.addEventListener("click", function (e) {
      if (autocompleteBox && !autocompleteBox.contains(e.target) && e.target !== searchInput) {
        autocompleteBox.classList.add("hidden");
      }
    });
  });
})();
