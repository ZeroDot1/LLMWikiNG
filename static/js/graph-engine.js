/**
 * graph-engine.js – Vanilla-JS Wissensgraph-Engine (Canvas 2D, keine externen Libs)
 * Ersetzt vis-network vollständig. 2026-Standard: ES2022+, Pointer Events, ResizeObserver.
 *
 * Optimierungen für große Wikis (1000+ Knoten):
 *  - Viewport Culling: Nur sichtbare Knoten/Kanten werden gerendert.
 *  - Level-of-Detail (LOD): Ab Zoom < 0.3 werden Labels ausgeblendet, Nodes als Punkte.
 *  - Barnes-Hut-Approximation (Quadtree): O(n log n) statt O(n²) Repulsion.
 *  - Lazy-Render: Kein Render wenn nichts animiert wird (alpha < alphaMin & kein Hover).
 *  - Kanten-Batching: Canvas-Pfade werden vor dem Stroke gebatcht (weniger State-Wechsel).
 */
export class GraphEngine {
  /** @param {HTMLCanvasElement} canvas */
  constructor(canvas, options = {}) {
    this.canvas = canvas;
    this.ctx    = canvas.getContext("2d");

    /** @type {Array<{id:string, label:string, group:string, url:string, title:string, x:number, y:number, vx:number, vy:number, opacity:number, _w:number, _h:number}>} */
    this.nodes     = [];
    /** @type {Array<{from:string, to:string, color:string, dashes:boolean, title:string, width:number}>} */
    this.edges     = [];
    /** @type {Map<string, object>} id → node (O(1) lookup) */
    this._nodeMap  = new Map();
    /** @type {Map<string, Set<string>>} id → Set of connected ids */
    this.adjacency = new Map();

    this.view = { x: 0, y: 0, scale: 1 };
    this.dragNode  = null;
    this.hoverNode = null;
    this.selected  = null;

    this.sim = { alpha: 1, alphaDecay: 0.02, alphaMin: 0.005 };
    this.opts = {
      gravitationalConstant: -2000,
      centralGravity:        0.3,
      springLength:          120,
      springConstant:        0.04,
      // Schwellenwert ab dem Barnes-Hut Quadtree genutzt wird
      barnesHutThreshold:    0.9,
      // Ab dieser Knotenanzahl wird Viewport-Culling aktiviert
      cullingThreshold:      100,
      ...options,
    };

    // Tooltip-Element (absolut über dem Canvas-Container)
    this._tooltip = this._createTooltip();
    this._raf     = null;
    this._dpr     = window.devicePixelRatio || 1;
    // Dirty-Flag: Erzwingt mindestens einen weiteren Render nach Interaktion
    this._dirty   = true;

    this._bindEvents();
    this._observeResize();

    this._loop = this._loop.bind(this);
    this._raf  = requestAnimationFrame(this._loop);
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // Public API
  // ─────────────────────────────────────────────────────────────────────────────

  /** Lade Graph-Daten und starte Simulation. */
  setData(data) {
    const TWO_PI = Math.PI * 2;
    const total  = data.nodes.length;

    this.nodes = data.nodes.map((n, i) => ({
      id:      n.id,
      label:   n.label,
      group:   n.group  || "page",
      url:     n.url    || "",
      title:   n.title  || n.label,
      // Spirale als Startlayout – verhindert initiale Überlagerungen
      x: Math.cos((i / total) * TWO_PI) * (100 + i * 2) + (Math.random() - 0.5) * 30,
      y: Math.sin((i / total) * TWO_PI) * (100 + i * 2) + (Math.random() - 0.5) * 30,
      vx: 0, vy: 0,
      opacity: 1,
      _w: 0, _h: 0,
    }));

    this.edges = data.edges.map(e => ({
      from:   e.from,
      to:     e.to,
      color:  e.color  || "#475569",
      dashes: !!e.dashes,
      title:  e.title  || "",
      width:  e.color  ? 2.5 : 1.5,
    }));

    // Schnelles id → node Mapping
    this._nodeMap.clear();
    this.nodes.forEach(n => this._nodeMap.set(n.id, n));

    // Adjazenzliste
    this.adjacency.clear();
    this.nodes.forEach(n => this.adjacency.set(n.id, new Set()));
    this.edges.forEach(e => {
      this.adjacency.get(e.from)?.add(e.to);
      this.adjacency.get(e.to)?.add(e.from);
    });

    // Metadaten für Lazy-Render und Pagination
    this._totalNodes    = data.total_nodes ?? total;
    this._currentPage   = data.page        ?? 0;
    this._totalPages    = data.total_pages  ?? 1;

    this.sim.alpha = 1;
    this.selected  = null;
    this._dirty    = true;
    this.fit();
  }

  /**
   * Hängt weitere Knoten/Kanten aus einer paginierten API-Antwort an.
   * Bereits vorhandene Knoten werden nicht dupliziert.
   */
  appendData(data) {
    const TWO_PI = Math.PI * 2;
    const existing = this._nodeMap;
    const total    = this.nodes.length + (data.nodes?.length ?? 0);

    for (const n of (data.nodes || [])) {
      if (existing.has(n.id)) continue;
      const i   = this.nodes.length;
      const node = {
        id:    n.id,
        label: n.label,
        group: n.group  || "page",
        url:   n.url    || "",
        title: n.title  || n.label,
        x: Math.cos((i / total) * TWO_PI) * (100 + i * 2) + (Math.random() - 0.5) * 30,
        y: Math.sin((i / total) * TWO_PI) * (100 + i * 2) + (Math.random() - 0.5) * 30,
        vx: 0, vy: 0,
        opacity: 0,   // einblenden via fade-in
        _w: 0, _h: 0,
      };
      this.nodes.push(node);
      existing.set(n.id, node);
      this.adjacency.set(n.id, new Set());
    }

    for (const e of (data.edges || [])) {
      // Keine Duplikate
      const alreadyExists = this.edges.some(ex => ex.from === e.from && ex.to === e.to);
      if (!alreadyExists) {
        this.edges.push({
          from:   e.from,
          to:     e.to,
          color:  e.color  || "#475569",
          dashes: !!e.dashes,
          title:  e.title  || "",
          width:  e.color  ? 2.5 : 1.5,
        });
        this.adjacency.get(e.from)?.add(e.to);
        this.adjacency.get(e.to)?.add(e.from);
      }
    }

    this._currentPage = data.page        ?? this._currentPage;
    this._totalPages  = data.total_pages  ?? this._totalPages;
    this._totalNodes  = data.total_nodes  ?? this._totalNodes;

    // Simulation kurz aufwärmen für neue Knoten
    this.sim.alpha = Math.max(this.sim.alpha, 0.35);
    this._dirty    = true;
  }

  /** Ansicht auf alle Knoten einpassen. */
  fit() {
    if (!this.nodes.length) return;
    const xs = this.nodes.map(n => n.x);
    const ys = this.nodes.map(n => n.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);

    const w   = this.canvas.clientWidth  || this.canvas.width  / this._dpr;
    const h   = this.canvas.clientHeight || this.canvas.height / this._dpr;
    const pad = 80;
    const sx  = (w - pad * 2) / (maxX - minX || 1);
    const sy  = (h - pad * 2) / (maxY - minY || 1);
    this.view.scale = Math.min(sx, sy, 2);
    const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
    this.view.x = w / 2 - cx * this.view.scale;
    this.view.y = h / 2 - cy * this.view.scale;
    this._dirty = true;
  }

  /** Selektion zurücksetzen + fit(). */
  reset() {
    this._select(null);
    this.fit();
  }

  /** Ressourcen freigeben (falls Engine nicht mehr benötigt). */
  destroy() {
    cancelAnimationFrame(this._raf);
    this._ro?.disconnect();
    this._tooltip.remove();
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // Physik: Barnes-Hut-Approximation + Force-Directed-Algorithmus
  // ─────────────────────────────────────────────────────────────────────────────

  _tick() {
    if (this.sim.alpha < this.sim.alphaMin) return;
    const α       = this.sim.alpha;
    const repulse = -this.opts.gravitationalConstant; // positiver Wert
    const k       = this.opts.springLength;
    const kSpring = this.opts.springConstant;
    const nodes   = this.nodes;
    const n       = nodes.length;

    // ── Repulsion ──────────────────────────────────────────────────────────
    // Barnes-Hut für n > cullingThreshold, sonst O(n²) (schneller bei wenig Knoten)
    if (n > this.opts.cullingThreshold) {
      this._barnesHutRepulsion(nodes, repulse, α);
    } else {
      // O(n²) – für kleine Wikis performant genug
      for (let i = 0; i < n; i++) {
        const a = nodes[i];
        for (let j = i + 1; j < n; j++) {
          const b  = nodes[j];
          let dx   = a.x - b.x;
          let dy   = a.y - b.y;
          const d2 = dx * dx + dy * dy || 0.01;
          const d  = Math.sqrt(d2);
          const f  = (repulse / d2) * α;
          const fx = (dx / d) * f;
          const fy = (dy / d) * f;
          a.vx += fx; a.vy += fy;
          b.vx -= fx; b.vy -= fy;
        }
      }
    }

    // Attraktion entlang Kanten (Federkraft)
    for (const e of this.edges) {
      const a = this._nodeMap.get(e.from);
      const b = this._nodeMap.get(e.to);
      if (!a || !b) continue;
      const dx = b.x - a.x, dy = b.y - a.y;
      const d  = Math.hypot(dx, dy) || 0.01;
      const f  = kSpring * (d - k) * α;
      const fx = (dx / d) * f, fy = (dy / d) * f;
      a.vx += fx; a.vy += fy;
      b.vx -= fx; b.vy -= fy;
    }

    // Zentralkraft + Euler-Integration + Dämpfung + Opacity Fade-in
    const cg = this.opts.centralGravity * 0.01 * α;
    for (const nd of nodes) {
      if (nd === this.dragNode) { nd.vx = 0; nd.vy = 0; continue; }
      nd.vx += -nd.x * cg;
      nd.vy += -nd.y * cg;
      nd.x  += nd.vx;
      nd.y  += nd.vy;
      nd.vx *= 0.85;  // Dämpfung
      nd.vy *= 0.85;
      // Fade-in für neue Knoten
      if (nd.opacity < 1) nd.opacity = Math.min(1, nd.opacity + 0.04);
    }

    this.sim.alpha *= (1 - this.sim.alphaDecay);
    this._dirty = true;
  }

  /**
   * Barnes-Hut Quadtree-basierte Repulsion.
   * O(n log n) statt O(n²) für große Wikis.
   */
  _barnesHutRepulsion(nodes, repulse, α) {
    // Bounding Box
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of nodes) {
      if (n.x < minX) minX = n.x;
      if (n.y < minY) minY = n.y;
      if (n.x > maxX) maxX = n.x;
      if (n.y > maxY) maxY = n.y;
    }
    const size = Math.max(maxX - minX, maxY - minY) + 1;

    // Quadtree aufbauen
    const root = { x: minX, y: minY, size, mass: 0, cx: 0, cy: 0, children: null, node: null };
    for (const nd of nodes) {
      this._qtInsert(root, nd);
    }

    // Kräfte berechnen
    const theta = this.opts.barnesHutThreshold;
    for (const nd of nodes) {
      this._qtForce(root, nd, repulse, α, theta);
    }
  }

  _qtInsert(cell, nd) {
    if (cell.node === null && cell.children === null) {
      // Leere Zelle
      cell.node = nd;
      cell.mass = 1;
      cell.cx   = nd.x;
      cell.cy   = nd.y;
      return;
    }
    // Zelle aufteilen falls nötig
    if (cell.children === null) {
      cell.children = [null, null, null, null];
      if (cell.node) {
        this._qtPlace(cell, cell.node);
        cell.node = null;
      }
    }
    this._qtPlace(cell, nd);
    // Massenschwerpunkt aktualisieren
    cell.cx   = (cell.cx * cell.mass + nd.x) / (cell.mass + 1);
    cell.cy   = (cell.cy * cell.mass + nd.y) / (cell.mass + 1);
    cell.mass++;
  }

  _qtPlace(cell, nd) {
    const hx = cell.x + cell.size / 2;
    const hy = cell.y + cell.size / 2;
    const qi = (nd.x >= hx ? 1 : 0) + (nd.y >= hy ? 2 : 0);
    if (!cell.children[qi]) {
      const hs = cell.size / 2;
      cell.children[qi] = {
        x: qi & 1 ? hx : cell.x,
        y: qi & 2 ? hy : cell.y,
        size: hs,
        mass: 0, cx: 0, cy: 0,
        children: null, node: null,
      };
    }
    this._qtInsert(cell.children[qi], nd);
  }

  _qtForce(cell, nd, repulse, α, theta) {
    if (!cell || cell.mass === 0) return;
    if (cell.node === nd) return;

    const dx = nd.x - cell.cx;
    const dy = nd.y - cell.cy;
    const d2 = dx * dx + dy * dy || 0.01;
    const d  = Math.sqrt(d2);

    // Barnes-Hut-Kriterium: Zelle weit genug weg → als Einheit behandeln
    if (cell.children === null || (cell.size / d) < theta) {
      const f  = (repulse * cell.mass / d2) * α;
      nd.vx   += (dx / d) * f;
      nd.vy   += (dy / d) * f;
      return;
    }
    // Rekursiv in Kinder
    if (cell.children) {
      for (const child of cell.children) {
        if (child) this._qtForce(child, nd, repulse, α, theta);
      }
    }
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // Rendering mit Viewport Culling und LOD
  // ─────────────────────────────────────────────────────────────────────────────

  _loop() {
    this._tick();

    // Lazy-Render: Nur rendern wenn Simulation läuft, Hover aktiv oder dirty
    const simActive = this.sim.alpha >= this.sim.alphaMin;
    if (simActive || this._dirty || this.hoverNode || this.dragNode) {
      this._render();
      this._dirty = false;
    }

    this._raf = requestAnimationFrame(this._loop);
  }

  _render() {
    const { ctx, view } = this;
    const dpr = this._dpr;
    const cw  = this.canvas.width;
    const ch  = this.canvas.height;

    // ── Viewport-Rechteck in Weltkoordinaten ────────────────────────────────
    const logicalW = cw / dpr;
    const logicalH = ch / dpr;
    const vLeft   = -view.x / view.scale;
    const vTop    = -view.y / view.scale;
    const vRight  = vLeft + logicalW / view.scale;
    const vBottom = vTop  + logicalH / view.scale;
    // Kleiner Puffer damit Knoten beim Einblenden nicht abrupt erscheinen
    const pad = 80 / view.scale;

    // LOD: Bei sehr kleinem Zoom nur Punkte und keine Labels
    const lodFull    = view.scale >= 0.3;
    const lodMedium  = view.scale >= 0.15;  // Rechtecke aber keine Labels
    const useCulling = this.nodes.length >= this.opts.cullingThreshold;

    ctx.clearRect(0, 0, cw, ch);
    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.translate(view.x, view.y);
    ctx.scale(view.scale, view.scale);

    // ── Kanten (gebatcht nach Farbe für weniger State-Wechsel) ─────────────
    if (lodMedium) {
      // Normale Kanten (keine gestrichelten)
      ctx.beginPath();
      ctx.strokeStyle = "#475569";
      ctx.lineWidth   = 1.5;
      ctx.setLineDash([]);
      ctx.globalAlpha = 0.85;

      const specialEdges = [];

      for (const e of this.edges) {
        const a = this._nodeMap.get(e.from);
        const b = this._nodeMap.get(e.to);
        if (!a || !b) continue;

        // Viewport Culling für Kanten
        if (useCulling) {
          const inView = !(
            (Math.max(a.x, b.x) < vLeft  - pad) ||
            (Math.min(a.x, b.x) > vRight + pad) ||
            (Math.max(a.y, b.y) < vTop   - pad) ||
            (Math.min(a.y, b.y) > vBottom + pad)
          );
          if (!inView) continue;
        }

        const dim = this._isDimmed(a.id) && this._isDimmed(b.id);
        if (dim) continue;  // Gedimmte Kanten in zweitem Pass

        if (e.color !== "#475569" || e.dashes) {
          specialEdges.push({ e, a, b, dim });
          continue;
        }

        const { sx, sy, ex, ey } = this._edgeEndpoints(a, b);
        ctx.moveTo(sx, sy);
        ctx.lineTo(ex, ey);
      }
      ctx.stroke();

      // Dimmed-Kanten (eigener Pass mit niedrigem Alpha)
      ctx.beginPath();
      ctx.globalAlpha = 0.08;
      for (const e of this.edges) {
        const a = this._nodeMap.get(e.from);
        const b = this._nodeMap.get(e.to);
        if (!a || !b) continue;
        if (!this._isDimmed(a.id) || !this._isDimmed(b.id)) continue;
        if (e.color !== "#475569" || e.dashes) continue;
        const { sx, sy, ex, ey } = this._edgeEndpoints(a, b);
        ctx.moveTo(sx, sy);
        ctx.lineTo(ex, ey);
      }
      ctx.stroke();

      // Spezielle Kanten (andere Farbe / gestrichelt) + Pfeile
      for (const { e, a, b, dim } of specialEdges) {
        ctx.globalAlpha = dim ? 0.1 : 0.85;
        ctx.strokeStyle = e.color;
        ctx.lineWidth   = e.width;
        ctx.setLineDash(e.dashes ? [6, 4] : []);
        const { sx, sy, ex, ey } = this._edgeEndpoints(a, b);
        ctx.beginPath();
        ctx.moveTo(sx, sy);
        ctx.lineTo(ex, ey);
        ctx.stroke();
        ctx.setLineDash([]);
        this._drawArrow(ex, ey, Math.atan2(ey - sy, ex - sx), e.color, dim ? 0.1 : 0.85);
      }

      // Pfeile für normale Kanten (nur wenn lodFull)
      if (lodFull) {
        ctx.strokeStyle = "#475569";
        ctx.lineWidth   = 1.5;
        ctx.setLineDash([]);
        for (const e of this.edges) {
          if (e.color !== "#475569" || e.dashes) continue;
          const a = this._nodeMap.get(e.from);
          const b = this._nodeMap.get(e.to);
          if (!a || !b) continue;
          if (useCulling) {
            const inView = !(
              (Math.max(a.x, b.x) < vLeft  - pad) ||
              (Math.min(a.x, b.x) > vRight + pad) ||
              (Math.max(a.y, b.y) < vTop   - pad) ||
              (Math.min(a.y, b.y) > vBottom + pad)
            );
            if (!inView) continue;
          }
          const dim = this._isDimmed(a.id) && this._isDimmed(b.id);
          if (dim) continue;
          const { sx, sy, ex, ey } = this._edgeEndpoints(a, b);
          this._drawArrow(ex, ey, Math.atan2(ey - sy, ex - sx), "#475569", 0.85);
        }
      }

      ctx.globalAlpha = 1;
    }

    // ── Knoten ──────────────────────────────────────────────────────────────
    const padX = 12, padY = 7;
    if (lodFull) ctx.font = "13px Inter, system-ui, sans-serif";

    for (const nd of this.nodes) {
      // Viewport Culling für Knoten
      if (useCulling) {
        const hw = (nd._w || 80) / 2 + pad;
        const hh = (nd._h || 27) / 2 + pad;
        if (nd.x + hw < vLeft || nd.x - hw > vRight || nd.y + hh < vTop || nd.y - hh > vBottom) {
          continue;
        }
      }

      const isDim = this._isDimmed(nd.id);
      const c     = this._colorFor(nd);

      if (!lodMedium) {
        // Ultra-LOD: einfacher Punkt
        ctx.globalAlpha = isDim ? 0.15 : nd.opacity * 0.8;
        ctx.fillStyle   = c.background;
        ctx.beginPath();
        ctx.arc(nd.x, nd.y, 3, 0, Math.PI * 2);
        ctx.fill();
        continue;
      }

      ctx.globalAlpha = isDim ? 0.2 : nd.opacity;

      if (lodFull) {
        // Vollständiger Render mit Label
        const tw = ctx.measureText(nd.label).width;
        const bw = tw + padX * 2;
        const bh = 13 + padY * 2;
        nd._w = bw; nd._h = bh;

        const x = nd.x - bw / 2, y = nd.y - bh / 2;

        ctx.shadowColor   = "rgba(0,0,0,0.35)";
        ctx.shadowBlur    = 6;
        ctx.shadowOffsetY = 2;

        this._roundRect(x, y, bw, bh, 7);
        ctx.fillStyle = c.background;
        ctx.fill();

        ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
        ctx.lineWidth   = nd.id === this.selected ? 2.5 : 1.5;
        ctx.strokeStyle = nd.id === this.selected ? "#fff" : c.border;
        ctx.stroke();

        ctx.fillStyle    = "#f8fafc";
        ctx.textAlign    = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(nd.label, nd.x, nd.y);
      } else {
        // Medium-LOD: Rechteck ohne Label
        const bw = 30, bh = 14;
        nd._w = bw; nd._h = bh;
        const x = nd.x - bw / 2, y = nd.y - bh / 2;
        this._roundRect(x, y, bw, bh, 4);
        ctx.fillStyle = c.background;
        ctx.fill();
        if (nd.id === this.selected) {
          ctx.lineWidth   = 2;
          ctx.strokeStyle = "#fff";
          ctx.stroke();
        }
      }
    }

    ctx.globalAlpha  = 1;
    ctx.shadowBlur   = 0;
    ctx.restore();
  }

  /** Berechne Kanten-Endpunkte an den Node-Rändern. */
  _edgeEndpoints(a, b) {
    const dx  = b.x - a.x, dy  = b.y - a.y;
    const ang = Math.atan2(dy, dx);
    const aw  = (a._w || 60) / 2, ah = (a._h || 27) / 2;
    const bw  = (b._w || 60) / 2, bh = (b._h || 27) / 2;

    // Schnittpunkt mit Rechteck-Rand (via parametrische Projektion)
    const ta  = this._rectEdgeT(aw, ah, ang);
    const tb  = this._rectEdgeT(bw, bh, ang + Math.PI);

    return {
      sx: a.x + Math.cos(ang) * ta,
      sy: a.y + Math.sin(ang) * ta,
      ex: b.x - Math.cos(ang) * tb,
      ey: b.y - Math.sin(ang) * tb,
    };
  }

  /** Abstand Rechteck-Mittelpunkt zu Rand in Richtung angle. */
  _rectEdgeT(hw, hh, angle) {
    const ca = Math.abs(Math.cos(angle));
    const sa = Math.abs(Math.sin(angle));
    return ca < 1e-9 ? hh : sa < 1e-9 ? hw : Math.min(hw / ca, hh / sa);
  }

  _drawArrow(x, y, angle, color, alpha) {
    const ah = 9;
    this.ctx.globalAlpha = alpha;
    this.ctx.fillStyle   = color;
    this.ctx.beginPath();
    this.ctx.moveTo(x, y);
    this.ctx.lineTo(x - ah * Math.cos(angle - 0.38), y - ah * Math.sin(angle - 0.38));
    this.ctx.lineTo(x - ah * Math.cos(angle + 0.38), y - ah * Math.sin(angle + 0.38));
    this.ctx.closePath();
    this.ctx.fill();
    this.ctx.globalAlpha = 1;
  }

  _colorFor(n) {
    if (n.group === "system") return { background: "#e05252", border: "#f08080" };
    if (n.group === "source") return { background: "#3a80c9", border: "#6ba8e8" };
    if (n.group?.startsWith("tag-")) {
      const tag  = n.group.slice(4);
      const hash = [...tag].reduce((a, c) => a + c.charCodeAt(0), 0);
      const hues = [35, 90, 160, 200, 260, 320];
      const hue  = hues[hash % hues.length];
      return { background: `hsl(${hue},58%,42%)`, border: `hsl(${hue},58%,58%)` };
    }
    return { background: "#5b6ee8", border: "#8091f5" };
  }

  _roundRect(x, y, w, h, r) {
    const ctx = this.ctx;
    // 2026: Path2D + roundRect nativ unterstützt in allen modernen Browsern
    if (ctx.roundRect) {
      ctx.beginPath();
      ctx.roundRect(x, y, w, h, r);
    } else {
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.arcTo(x + w, y,     x + w, y + h, r);
      ctx.arcTo(x + w, y + h, x,     y + h, r);
      ctx.arcTo(x,     y + h, x,     y,     r);
      ctx.arcTo(x,     y,     x + w, y,     r);
      ctx.closePath();
    }
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // Selektion / Dimming
  // ─────────────────────────────────────────────────────────────────────────────

  _isDimmed(id) {
    if (!this.selected) return false;
    return id !== this.selected && !this.adjacency.get(this.selected)?.has(id);
  }

  _select(id) {
    this.selected = id;
    this._dirty   = true;
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // Interaktion – Pointer Events (Maus + Touch)
  // ─────────────────────────────────────────────────────────────────────────────

  _bindEvents() {
    const cv = this.canvas;
    let panning = false, lastX = 0, lastY = 0;
    let clickTimer = null;

    // ── Pointer Down ────────────────────────────────────────────────────────
    cv.addEventListener("pointerdown", e => {
      cv.setPointerCapture(e.pointerId);
      const p   = this._toWorld(e);
      const hit = this._hitTest(p);
      if (hit) {
        this.dragNode = hit;
        this.sim.alpha = Math.max(this.sim.alpha, 0.12);
      } else {
        panning = true;
        lastX   = e.clientX;
        lastY   = e.clientY;
      }
    });

    // ── Pointer Move ────────────────────────────────────────────────────────
    cv.addEventListener("pointermove", e => {
      const p = this._toWorld(e);
      if (this.dragNode) {
        this.dragNode.x = p.x;
        this.dragNode.y = p.y;
        this.sim.alpha  = Math.max(this.sim.alpha, 0.08);
        this._dirty     = true;
      } else if (panning) {
        this.view.x += e.clientX - lastX;
        this.view.y += e.clientY - lastY;
        lastX = e.clientX;
        lastY = e.clientY;
        this._dirty = true;
      } else {
        const prev = this.hoverNode;
        this.hoverNode = this._hitTest(p);
        cv.style.cursor = this.hoverNode ? "pointer" : "grab";
        if (this.hoverNode !== prev) {
          this._dirty = true;
          if (this.hoverNode) {
            this._showTooltip(e, this.hoverNode);
          } else {
            this._hideTooltip();
          }
        } else if (this.hoverNode) {
          this._moveTooltip(e);
        }
      }
    });

    // ── Pointer Up ──────────────────────────────────────────────────────────
    cv.addEventListener("pointerup", e => {
      if (!this.dragNode && !panning) {
        // Click-Logik: einfacher Klick vs. Doppelklick
        if (clickTimer) {
          clearTimeout(clickTimer);
          clickTimer = null;
          // Doppelklick
          const p   = this._toWorld(e);
          const hit = this._hitTest(p);
          if (hit?.url) window.location.href = hit.url;
        } else {
          clickTimer = setTimeout(() => {
            clickTimer = null;
            const p   = this._toWorld(e);
            const hit = this._hitTest(p);
            this._select(hit ? hit.id : null);
          }, 220);
        }
      }
      this.dragNode = null;
      panning       = false;
    });

    cv.addEventListener("pointercancel", () => {
      this.dragNode = null;
      panning       = false;
    });

    // ── Wheel / Zoom ────────────────────────────────────────────────────────
    cv.addEventListener("wheel", e => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      const rect   = cv.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      this.view.x     = mx - (mx - this.view.x) * factor;
      this.view.y     = my - (my - this.view.y) * factor;
      this.view.scale = Math.max(0.05, Math.min(this.view.scale * factor, 6));
      this._dirty = true;
    }, { passive: false });

    // ── Mouse Leave: Tooltip verbergen ─────────────────────────────────────
    cv.addEventListener("pointerleave", () => {
      this._hideTooltip();
      this.hoverNode = null;
    });
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // Koordinaten-Transformation
  // ─────────────────────────────────────────────────────────────────────────────

  _toWorld(e) {
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left  - this.view.x) / this.view.scale,
      y: (e.clientY - rect.top   - this.view.y) / this.view.scale,
    };
  }

  _hitTest(p) {
    // Von vorne nach hinten (zuletzt gezeichnet = oben)
    for (let i = this.nodes.length - 1; i >= 0; i--) {
      const n  = this.nodes[i];
      const hw = (n._w || 80) / 2, hh = (n._h || 27) / 2;
      if (p.x >= n.x - hw && p.x <= n.x + hw && p.y >= n.y - hh && p.y <= n.y + hh)
        return n;
    }
    return null;
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // Tooltip
  // ─────────────────────────────────────────────────────────────────────────────

  _createTooltip() {
    const el = document.createElement("div");
    el.style.cssText = [
      "position:absolute",
      "display:none",
      "pointer-events:none",
      "background:rgba(15,20,30,0.92)",
      "color:#e2e8f0",
      "padding:5px 10px",
      "border-radius:6px",
      "font:12px Inter,system-ui,sans-serif",
      "border:1px solid rgba(255,255,255,0.1)",
      "backdrop-filter:blur(4px)",
      "z-index:100",
      "max-width:220px",
      "white-space:pre-wrap",
    ].join(";");
    // In den Canvas-Container einhängen
    const parent = this.canvas.parentElement || document.body;
    parent.style.position ||= "relative";
    parent.appendChild(el);
    return el;
  }

  _showTooltip(e, node) {
    if (!node.title) return;
    const rect   = this.canvas.getBoundingClientRect();
    const parent = this._tooltip.parentElement.getBoundingClientRect();
    this._tooltip.textContent = node.title;
    this._tooltip.style.left  = `${e.clientX - parent.left + 12}px`;
    this._tooltip.style.top   = `${e.clientY - parent.top  - 30}px`;
    this._tooltip.style.display = "block";
  }

  _moveTooltip(e) {
    const parent = this._tooltip.parentElement.getBoundingClientRect();
    this._tooltip.style.left = `${e.clientX - parent.left + 12}px`;
    this._tooltip.style.top  = `${e.clientY - parent.top  - 30}px`;
  }

  _hideTooltip() {
    this._tooltip.style.display = "none";
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // ResizeObserver – Canvas-Auflösung bei Größenänderung anpassen
  // ─────────────────────────────────────────────────────────────────────────────

  _observeResize() {
    this._ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        const dpr = window.devicePixelRatio || 1;
        this._dpr = dpr;
        this.canvas.width  = Math.round(width  * dpr);
        this.canvas.height = Math.round(height * dpr);
        this._dirty = true;
      }
    });
    this._ro.observe(this.canvas);
  }
}
