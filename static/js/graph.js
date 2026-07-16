// graph.js – Wissensgraph-Controller (nutzt eigene graph-engine.js statt vis-network)
import { GraphEngine } from "./graph-engine.js";

const BASE_PATH = window.BASE_PATH || "";
let engine = null;

/** Wird vom Reset-Button in graph.html aufgerufen. */
function resetGraph() {
  engine?.reset();
}
window.resetGraph = resetGraph;

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

  fetch(`${BASE_PATH}/graph/data?wiki=${encodeURIComponent(wiki)}`)
    .then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then(data => {
      const loader = document.getElementById("network-loader");
      if (loader) loader.style.display = "none";
      engine.setData(data);
    })
    .catch(err => {
      console.error("[graph.js] Fehler beim Laden des Graphen:", err);
      const loader = document.getElementById("network-loader");
      if (loader) loader.innerHTML = `<p class="text-red-400">⚠️ Graph konnte nicht geladen werden.</p>`;
    });
});
