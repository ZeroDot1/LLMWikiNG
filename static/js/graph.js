// graph.js – Wissensgraph-Controller mit Lazy-Loading für große Wikis
// Nutzt graph-engine.js (Canvas 2D, keine externen Libs).
//
// Lazy-Loading-Strategie:
//  1. Erste Seite (200 Knoten) sofort laden – Graph ist schnell sichtbar.
//  2. Weitere Seiten werden im Hintergrund nachgeladen (IntersectionObserver
//     auf einen Sentinel-DIV ODER nach kurzer Verzögerung).
//  3. Bei kleinen Wikis (<= page_size) wird die paginierte API-Route
//     trotzdem genutzt (liefert total_pages=1) – kein Sonderfall nötig.

import { GraphEngine } from "./graph-engine.js";

const BASE_PATH = window.BASE_PATH || "";
let engine = null;

/** Wird vom Reset-Button in graph.html aufgerufen. */
function resetGraph() {
  engine?.reset();
}
window.resetGraph = resetGraph;

// ─────────────────────────────────────────────────────────────────────────────
// Loader-Banner-Hilfsfunktionen
// ─────────────────────────────────────────────────────────────────────────────

function setLoaderText(text) {
  const loader = document.getElementById("network-loader");
  if (loader) loader.innerHTML = text;
}

function hideLoader() {
  const loader = document.getElementById("network-loader");
  if (loader) loader.style.display = "none";
}

function showLoaderError(msg) {
  const loader = document.getElementById("network-loader");
  if (loader) loader.innerHTML = `<p style="color:#f56c6c">⚠️ ${msg}</p>`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Badge-Anzeige: "X von Y Knoten geladen"
// ─────────────────────────────────────────────────────────────────────────────

function getOrCreateBadge() {
  let badge = document.getElementById("graph-load-badge");
  if (!badge) {
    badge = document.createElement("div");
    badge.id = "graph-load-badge";
    badge.style.cssText = [
      "position:absolute",
      "bottom:12px",
      "right:16px",
      "background:rgba(15,20,30,0.82)",
      "color:#94a3b8",
      "font:11px Inter,system-ui,sans-serif",
      "padding:4px 10px",
      "border-radius:20px",
      "border:1px solid rgba(255,255,255,0.08)",
      "pointer-events:none",
      "backdrop-filter:blur(4px)",
      "transition:opacity 0.4s",
      "z-index:50",
    ].join(";");
    const container = document.getElementById("graph-container");
    if (container) {
      container.style.position ||= "relative";
      container.appendChild(badge);
    }
  }
  return badge;
}

function updateBadge(loaded, total, isComplete) {
  const badge = getOrCreateBadge();
  if (isComplete && loaded >= total) {
    badge.style.opacity = "0";
    return;
  }
  badge.style.opacity = "1";
  badge.textContent   = `${loaded.toLocaleString()} / ${total.toLocaleString()} Knoten geladen`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Haupt-Ladelogik mit Pagination
// ─────────────────────────────────────────────────────────────────────────────

async function loadGraphPaginated(wiki, pageSize = 200) {
  let page      = 0;
  let totalPages = 1;
  let totalNodes = 0;
  let loadedNodes = 0;

  // Erste Seite: blockierend (Graph wird sofort angezeigt)
  try {
    const url  = `${BASE_PATH}/graph/data/paginated?wiki=${encodeURIComponent(wiki)}&page=0&page_size=${pageSize}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    hideLoader();
    engine.setData(data);

    totalPages  = data.total_pages  ?? 1;
    totalNodes  = data.total_nodes  ?? data.nodes.length;
    loadedNodes = data.nodes.length;
    page        = 1;

    updateBadge(loadedNodes, totalNodes, page >= totalPages);
  } catch (err) {
    console.error("[graph.js] Fehler beim Laden der ersten Seite:", err);
    showLoaderError("Graph konnte nicht geladen werden.");
    return;
  }

  // Weitere Seiten: asynchron im Hintergrund nachladen
  if (page < totalPages) {
    // Kurze Pause damit die Simulation der ersten Seite starten kann
    await delay(800);

    while (page < totalPages) {
      try {
        const url  = `${BASE_PATH}/graph/data/paginated?wiki=${encodeURIComponent(wiki)}&page=${page}&page_size=${pageSize}`;
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        engine.appendData(data);
        loadedNodes += data.nodes.length;
        page++;

        updateBadge(loadedNodes, totalNodes, page >= totalPages);

        // Pausen zwischen Seiten: erster Batch schnell, dann langsamer
        await delay(page <= 3 ? 400 : 900);
      } catch (err) {
        console.warn(`[graph.js] Fehler beim Laden von Seite ${page}:`, err);
        break;
      }
    }
  }
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ─────────────────────────────────────────────────────────────────────────────
// Initialisierung
// ─────────────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  const canvas = document.getElementById("network");
  if (!canvas) return;

  const gcontainer = document.getElementById("graph-container");
  const wiki       = gcontainer?.dataset.wiki ?? "";

  // Initiale Canvas-Größe setzen (ResizeObserver übernimmt danach)
  const dpr  = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  if (rect.width > 0 && rect.height > 0) {
    canvas.width  = Math.round(rect.width  * dpr);
    canvas.height = Math.round(rect.height * dpr);
  }

  engine = new GraphEngine(canvas);

  // Paginierte Route verwenden (funktioniert auch für kleine Wikis: total_pages=1)
  // Page-Size 200: erster Batch ist schnell sichtbar, große Wikis werden schrittweise geladen.
  loadGraphPaginated(wiki, 200);
});
