// audit.js – Interaktivität für das Audit-Logbuch
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {

    // ── 1. Prune-Form Confirmation ──────────────────────────────────────────
    const pruneForm = document.getElementById("pruneForm");
    if (pruneForm) {
      pruneForm.addEventListener("submit", function (e) {
        const year = document.getElementById("prune-year").value;
        const monthSelect = document.getElementById("prune-month");
        const monthName = monthSelect.options[monthSelect.selectedIndex].text.trim();
        const hasMonth = !!monthSelect.value;

        const msg = hasMonth
          ? `⚠ Alle Audit-Logs VOR ${monthName} ${year} unwiderruflich löschen?\n\nDiese Aktion kann nicht rückgängig gemacht werden.`
          : `⚠ Alle Audit-Logs vor dem Jahr ${year} unwiderruflich löschen?\n\nDiese Aktion kann nicht rückgängig gemacht werden.`;

        if (!confirm(msg)) {
          e.preventDefault();
        }
      });
    }

    // ── 2. Timestamp Relative Formatting ───────────────────────────────────
    document.querySelectorAll(".audit-date[data-ts]").forEach(function (el) {
      const raw = el.getAttribute("data-ts");
      if (!raw) return;
      try {
        const d = new Date(raw);
        const now = new Date();
        const diffMs = now - d;
        const diffMin = Math.floor(diffMs / 60000);
        const diffH = Math.floor(diffMs / 3600000);
        const diffD = Math.floor(diffMs / 86400000);

        let relative = "";
        if (diffMin < 1) relative = "gerade eben";
        else if (diffMin < 60) relative = `vor ${diffMin} Min.`;
        else if (diffH < 24) relative = `vor ${diffH} Std.`;
        else if (diffD < 7) relative = `vor ${diffD} Tag${diffD !== 1 ? "en" : ""}`;
        else relative = d.toLocaleDateString("de-DE", { day: "2-digit", month: "short", year: "numeric" });

        el.title = raw;
        el.textContent = raw.replace("T", " ").replace(/\.\d+Z?$/, "");

        const relSpan = document.createElement("span");
        relSpan.className = "block text-text-muted text-xs";
        relSpan.textContent = relative;
        el.parentNode.appendChild(relSpan);
      } catch (_) {}
    });

    // ── 3. Keyboard Shortcut: Ctrl/Cmd+F focuses action filter ─────────────
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "f" && e.shiftKey) {
        e.preventDefault();
        const filterAction = document.getElementById("filter-action");
        if (filterAction) filterAction.focus();
      }
    });

    // ── 4. Action Badge Summary Cards ──────────────────────────────────────
    const summaryContainer = document.getElementById("audit-action-summary");
    if (summaryContainer) {
      const rows = document.querySelectorAll(".audit-row");
      if (rows.length > 0) {
        const counts = {};
        rows.forEach(function (row) {
          const category = row.getAttribute("data-category") || "system";
          counts[category] = (counts[category] || 0) + 1;
        });

        const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
        sorted.forEach(function ([category, count]) {
          const card = document.createElement("a");
          card.href = `?category=${encodeURIComponent(category)}`;
          card.className = "rounded-lg border border-border bg-surface p-2 text-center hover:border-primary transition-colors flex flex-col justify-center";
          card.innerHTML = `<div class="text-lg font-bold text-text">${count}</div><div class="text-[10px] font-semibold uppercase tracking-wider text-text-muted mt-1 truncate" title="${category}">${category}</div>`;
          summaryContainer.appendChild(card);
        });

        summaryContainer.classList.remove("hidden");
      }
    }

    // ── 5. Click-to-expand Details ─────────────────────────────────────────
    document.querySelectorAll("#audit-tbody tr.audit-row").forEach(function (row) {
      const detailCell = row.querySelector("td:nth-child(5) span");
      if (!detailCell) return;
      const fullText = detailCell.getAttribute("title");
      if (!fullText || fullText.length <= 55) return;

      detailCell.style.cursor = "pointer";
      detailCell.classList.add("ring-hover");
      detailCell.title = "Klicken zum Anzeigen";

      detailCell.addEventListener("click", function () {
        if (detailCell.classList.contains("truncate")) {
          detailCell.classList.remove("truncate");
          detailCell.style.whiteSpace = "normal";
          detailCell.textContent = fullText;
          detailCell.title = "Klicken zum Einklappen";
        } else {
          detailCell.classList.add("truncate");
          detailCell.style.whiteSpace = "";
          detailCell.textContent = fullText;
          detailCell.title = "Klicken zum Anzeigen";
        }
      });
    });

  });
})();
