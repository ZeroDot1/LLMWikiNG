// graph.js – Wissensgraph-Controller mit Lazy-Loading, Suche, Tag-Filter,
//             Detail-Panel, Zoom-Controls und Vollbild-Unterstützung.
// Nutzt graph-engine.js (Canvas 2D, keine externen Libs).
//
// Lazy-Loading-Strategie:
//  1. Erste Seite (200 Knoten) sofort laden – Graph ist schnell sichtbar.
//  2. Weitere Seiten asynchron im Hintergrund nachladen.
//  3. Bei kleinen Wikis (total_pages=1) kein Unterschied zum Nutzer sichtbar.

import { GraphEngine } from "./graph-engine.js";

const BASE_PATH = window.BASE_PATH || "";
let engine      = null;
let _allNodes   = [];   // vollständige Node-Liste für Suche/Filter
let _allEdges   = [];   // vollständige Edge-Liste
let _currentTag = "";   // aktiver Tag-Filter ("" = alle)

// ─────────────────────────────────────────────────────────────────────────────
// Öffentliche API (aufgerufen aus graph.html)
// ─────────────────────────────────────────────────────────────────────────────

function resetGraph() {
  engine?.reset();
  clearSearch();
  closeDetailPanel();
}
window.resetGraph = resetGraph;

// ─────────────────────────────────────────────────────────────────────────────
// Loader-Hilfsfunktionen
// ─────────────────────────────────────────────────────────────────────────────

function hideLoader() {
  const el = document.getElementById("network-loader");
  if (el) el.style.display = "none";
}

function showLoaderError(msg) {
  const el = document.getElementById("network-loader");
  if (el) el.innerHTML = `<p style="color:#f56c6c;font-size:13px">⚠️ ${msg}</p>`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Progress-Badge
// ─────────────────────────────────────────────────────────────────────────────

function getOrCreateBadge() {
  let badge = document.getElementById("graph-load-badge");
  if (!badge) {
    badge = document.createElement("div");
    badge.id = "graph-load-badge";
    badge.style.cssText = [
      "position:absolute", "bottom:12px", "right:16px",
      "background:rgba(15,20,30,0.82)", "color:#94a3b8",
      "font:11px Inter,system-ui,sans-serif",
      "padding:4px 12px", "border-radius:20px",
      "border:1px solid rgba(255,255,255,0.08)",
      "pointer-events:none", "backdrop-filter:blur(4px)",
      "transition:opacity 0.5s", "z-index:50",
    ].join(";");
    const container = document.getElementById("graph-container");
    if (container) { container.style.position ||= "relative"; container.appendChild(badge); }
  }
  return badge;
}

function updateBadge(loaded, total, isComplete) {
  const badge = getOrCreateBadge();
  if (isComplete && loaded >= total) { badge.style.opacity = "0"; return; }
  badge.style.opacity = "1";
  badge.textContent   = `${loaded.toLocaleString()} / ${total.toLocaleString()} Knoten geladen`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Stats-Overlay
// ─────────────────────────────────────────────────────────────────────────────

function updateStatsOverlay(nodes, edges, selectedId) {
  const overlay = document.getElementById("graph-stats-overlay");
  if (!overlay) return;
  overlay.classList.remove("hidden");
  const nEl = document.getElementById("graph-stat-nodes");
  const eEl = document.getElementById("graph-stat-edges");
  if (nEl) nEl.textContent = nodes.toLocaleString();
  if (eEl) eEl.textContent = edges.toLocaleString();

  const selRow = document.getElementById("graph-stat-selected-row");
  const selEl  = document.getElementById("graph-stat-selected");
  if (selRow && selEl) {
    if (selectedId) {
      selRow.classList.remove("hidden");
      selEl.textContent = selectedId;
    } else {
      selRow.classList.add("hidden");
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Tag-Filter-Leiste
// ─────────────────────────────────────────────────────────────────────────────

function buildTagBar(nodes) {
  const bar = document.getElementById("graph-tag-bar");
  if (!bar) return;

  // Tags aus allen Nodes sammeln
  const tagSet = new Set();
  for (const n of nodes) {
    if (n.group?.startsWith("tag-")) tagSet.add(n.group.slice(4));
  }
  if (tagSet.size === 0) { bar.classList.add("hidden"); return; }

  // "Alle"-Button bleibt, weitere Tags anhängen
  const existing = bar.querySelectorAll("[data-tag]:not([data-tag=''])");
  existing.forEach(b => b.remove());

  for (const tag of [...tagSet].sort()) {
    const btn = document.createElement("button");
    btn.dataset.tag = tag;
    btn.className   = "graph-tag-btn rounded-full border border-border bg-surface px-2.5 py-0.5 text-xs font-medium text-text-secondary hover:border-primary hover:text-primary transition-colors";
    btn.textContent = tag;
    bar.appendChild(btn);
  }

  bar.classList.remove("hidden");
  bar.querySelectorAll(".graph-tag-btn").forEach(btn => {
    btn.addEventListener("click", () => applyTagFilter(btn.dataset.tag));
  });
}

function applyTagFilter(tag) {
  _currentTag = tag;
  // Aktiven Button markieren
  document.querySelectorAll(".graph-tag-btn").forEach(b => {
    const isActive = b.dataset.tag === tag;
    b.classList.toggle("graph-tag-active", isActive);
    b.classList.toggle("border-primary",     isActive);
    b.classList.toggle("bg-primary-subtle",  isActive);
    b.classList.toggle("text-primary",       isActive);
    b.classList.toggle("border-border",      !isActive);
    b.classList.toggle("bg-surface",         !isActive);
    b.classList.toggle("text-text-secondary",!isActive);
  });

  // Graph neu filtern
  const filteredNodes = tag
    ? _allNodes.filter(n => n.group === `tag-${tag}` || n.group === "page")
    : _allNodes;
  const visibleIds = new Set(filteredNodes.map(n => n.id));
  const filteredEdges = tag
    ? _allEdges.filter(e => visibleIds.has(e.from) && visibleIds.has(e.to))
    : _allEdges;

  engine?.setData({ nodes: filteredNodes, edges: filteredEdges, total_nodes: filteredNodes.length, total_pages: 1, page: 0, page_size: filteredNodes.length });
  updateStatsOverlay(filteredNodes.length, filteredEdges.length, null);
  closeDetailPanel();
  clearSearch();
}

// ─────────────────────────────────────────────────────────────────────────────
// Node-Suche
// ─────────────────────────────────────────────────────────────────────────────

function initSearch() {
  const input = document.getElementById("graph-search");
  if (!input) return;

  let searchTimeout = null;
  input.addEventListener("input", () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => applySearch(input.value.trim()), 180);
  });
  input.addEventListener("keydown", e => {
    if (e.key === "Escape") { clearSearch(); input.blur(); }
  });
}

function applySearch(q) {
  if (!engine || !q) { clearSearch(); return; }
  const lower = q.toLowerCase();
  const match = _allNodes.find(n =>
    n.label?.toLowerCase().includes(lower) || n.id?.toLowerCase().includes(lower)
  );
  if (match) {
    engine._select(match.id);
    // Zur Node scrollen (View zentrieren)
    const node = engine._nodeMap.get(match.id);
    if (node) {
      const w = engine.canvas.clientWidth  || engine.canvas.width  / engine._dpr;
      const h = engine.canvas.clientHeight || engine.canvas.height / engine._dpr;
      engine.view.x = w / 2 - node.x * engine.view.scale;
      engine.view.y = h / 2 - node.y * engine.view.scale;
      engine._dirty = true;
    }
    openDetailPanel(match.id);
  }
}

function clearSearch() {
  const input = document.getElementById("graph-search");
  if (input) input.value = "";
  engine?._select(null);
  closeDetailPanel();
}

// ─────────────────────────────────────────────────────────────────────────────
// Knoten-Detail-Panel
// ─────────────────────────────────────────────────────────────────────────────

function openDetailPanel(nodeId) {
  const node = engine?._nodeMap.get(nodeId);
  if (!node) return;

  const panel = document.getElementById("graph-detail-panel");
  if (!panel) return;

  const titleEl   = document.getElementById("graph-detail-title");
  const groupEl   = document.getElementById("graph-detail-group");
  const connEl    = document.getElementById("graph-detail-connections");
  const linkEl    = document.getElementById("graph-detail-link");

  if (titleEl) titleEl.textContent = node.label || node.id;
  if (groupEl) groupEl.textContent = node.group || "page";
  if (connEl)  connEl.textContent  = engine.adjacency.get(nodeId)?.size ?? 0;
  if (linkEl)  linkEl.href         = node.url || "#";

  // Stats aktualisieren
  const selRow = document.getElementById("graph-stat-selected-row");
  const selEl  = document.getElementById("graph-stat-selected");
  if (selRow && selEl) { selRow.classList.remove("hidden"); selEl.textContent = node.label || nodeId; }

  panel.classList.remove("hidden");
}

function closeDetailPanel() {
  document.getElementById("graph-detail-panel")?.classList.add("hidden");
  const selRow = document.getElementById("graph-stat-selected-row");
  if (selRow) selRow.classList.add("hidden");
}

// ─────────────────────────────────────────────────────────────────────────────
// Zoom-Buttons
// ─────────────────────────────────────────────────────────────────────────────

function initZoomButtons() {
  document.getElementById("graph-zoom-in")?.addEventListener("click", () => {
    if (!engine) return;
    const factor = 1.25;
    const w = engine.canvas.clientWidth  / 2;
    const h = engine.canvas.clientHeight / 2;
    engine.view.x     = w - (w - engine.view.x) * factor;
    engine.view.y     = h - (h - engine.view.y) * factor;
    engine.view.scale = Math.min(engine.view.scale * factor, 6);
    engine._dirty = true;
  });
  document.getElementById("graph-zoom-out")?.addEventListener("click", () => {
    if (!engine) return;
    const factor = 1 / 1.25;
    const w = engine.canvas.clientWidth  / 2;
    const h = engine.canvas.clientHeight / 2;
    engine.view.x     = w - (w - engine.view.x) * factor;
    engine.view.y     = h - (h - engine.view.y) * factor;
    engine.view.scale = Math.max(engine.view.scale * factor, 0.05);
    engine._dirty = true;
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Vollbild
// ─────────────────────────────────────────────────────────────────────────────

function initFullscreen() {
  const btn      = document.getElementById("graph-fullscreen-btn");
  const container = document.getElementById("graph-container");
  const iconExp  = document.getElementById("graph-fs-icon-expand");
  const iconComp = document.getElementById("graph-fs-icon-compress");
  const label    = document.getElementById("graph-fs-label");
  if (!btn || !container) return;

  function setFsState(isFs) {
    iconExp?.classList.toggle("hidden", isFs);
    iconComp?.classList.toggle("hidden", !isFs);
    if (label) label.textContent = isFs ? "Exit" : (label.dataset.enter || "Vollbild");
  }

  btn.addEventListener("click", () => {
    if (!document.fullscreenElement) {
      container.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.();
    }
  });

  document.addEventListener("fullscreenchange", () => {
    const isFs = !!document.fullscreenElement;
    setFsState(isFs);
    // Canvas-Größe nach Vollbild-Wechsel neu setzen
    setTimeout(() => engine?.fit(), 120);
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Wiki-Switcher
// ─────────────────────────────────────────────────────────────────────────────

function initWikiSwitcher() {
  const sel = document.getElementById("graph-wiki-select");
  if (!sel) return;
  sel.addEventListener("change", () => {
    const wiki = sel.value;
    // URL anpassen und Seite neu laden
    const url = new URL(window.location.href);
    url.searchParams.set("wiki", wiki);
    window.location.href = url.toString();
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Engine-Event-Hooks (Selection → Detail-Panel)
// ─────────────────────────────────────────────────────────────────────────────

function patchEngineForDetailPanel(eng) {
  // Monkey-patch _select um Detail-Panel zu öffnen/schließen
  const orig = eng._select.bind(eng);
  eng._select = (id) => {
    orig(id);
    if (id) openDetailPanel(id);
    else    closeDetailPanel();
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Haupt-Ladelogik mit Pagination
// ─────────────────────────────────────────────────────────────────────────────

async function loadGraphPaginated(wiki, pageSize = 200) {
  let page        = 0;
  let totalPages  = 1;
  let totalNodes  = 0;
  let loadedNodes = 0;

  // Erste Seite: blockierend (Graph erscheint sofort)
  try {
    const url  = `${BASE_PATH}/graph/data/paginated?wiki=${encodeURIComponent(wiki)}&page=0&page_size=${pageSize}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    hideLoader();
    engine.setData(data);

    // Interne Vollständige Listen aufbauen
    _allNodes   = [...(data.nodes || [])];
    _allEdges   = [...(data.edges || [])];
    totalPages  = data.total_pages  ?? 1;
    totalNodes  = data.total_nodes  ?? data.nodes.length;
    loadedNodes = data.nodes.length;
    page        = 1;

    buildTagBar(_allNodes);
    updateStatsOverlay(loadedNodes, _allEdges.length, null);
    updateBadge(loadedNodes, totalNodes, page >= totalPages);
  } catch (err) {
    console.error("[graph.js] Fehler beim Laden der ersten Seite:", err);
    showLoaderError("Graph konnte nicht geladen werden.");
    return;
  }

  // Weitere Seiten im Hintergrund
  if (page < totalPages) {
    await delay(800);
    while (page < totalPages) {
      try {
        const url  = `${BASE_PATH}/graph/data/paginated?wiki=${encodeURIComponent(wiki)}&page=${page}&page_size=${pageSize}`;
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        engine.appendData(data);
        _allNodes.push(...(data.nodes || []));
        _allEdges.push(...(data.edges || []));
        loadedNodes += (data.nodes || []).length;
        page++;

        // Tag-Leiste ggf. erweitern
        buildTagBar(_allNodes);
        updateStatsOverlay(loadedNodes, _allEdges.length, null);
        updateBadge(loadedNodes, totalNodes, page >= totalPages);

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
  const canvas     = document.getElementById("network");
  const gcontainer = document.getElementById("graph-container");
  if (!canvas || !gcontainer) return;

  const wiki = gcontainer.dataset.wiki ?? "";

  // Initiale Canvas-Größe
  const dpr  = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  if (rect.width > 0 && rect.height > 0) {
    canvas.width  = Math.round(rect.width  * dpr);
    canvas.height = Math.round(rect.height * dpr);
  }

  engine = new GraphEngine(canvas);
  patchEngineForDetailPanel(engine);

  // Detail-Panel schließen-Button
  document.getElementById("graph-detail-close")?.addEventListener("click", () => {
    engine._select(null);
    closeDetailPanel();
  });

  // UI-Module initialisieren
  initWikiSwitcher();
  initSearch();
  initZoomButtons();
  initFullscreen();

  // Daten laden
  loadGraphPaginated(wiki, 200);
});
