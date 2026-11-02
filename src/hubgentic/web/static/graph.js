// Interactive graphs (Cytoscape.js) for [data-graph] containers.
// Elements come from a <script type="application/json"> tag rendered by the server.
(() => {
  if (!window.cytoscape) return;
  const graphs = new Map();

  const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const sourceColors = new Map();
  const sourceColor = (src) => {
    if (!sourceColors.has(src)) {
      const probe = document.createElement("span");
      probe.className = `src-${src}`;
      probe.hidden = true;
      document.body.append(probe);
      sourceColors.set(src, getComputedStyle(probe).color);
      probe.remove();
    }
    return sourceColors.get(src);
  };

  // Box nodes are sized to their measured label (Cytoscape's `width: label` is deprecated).
  const ctx = document.createElement("canvas").getContext("2d");
  const box = (size, family, weight, pad) => ({
    "font-size": size, "font-family": family, "font-weight": weight, padding: 0,
    width: (n) => { ctx.font = `${weight} ${size}px ${family}`; return ctx.measureText(n.data("label")).width + 2 * pad; },
    height: size + 2 * pad,
  });

  function style() {
    sourceColors.clear();
    const t = {
      text: token("--text"), text2: token("--text-2"), text3: token("--text-3"),
      bg: token("--bg-elev"), sunk: token("--bg-sunk"), border: token("--border-strong"),
      accent: token("--accent"), accent2: token("--accent-2"), ok: token("--ok"),
      sans: token("--sans") || "sans-serif", mono: token("--mono") || "monospace",
    };
    const nodeSrc = (n) => sourceColor(n.data("source"));
    return [
      { selector: "node", style: {
        label: "data(label)", "font-family": t.sans, "font-size": 11, color: t.text,
        "text-valign": "center", "text-halign": "center", shape: "round-rectangle",
        "background-color": t.bg,
        "border-width": 1.5, "border-color": t.border,
      } },
      { selector: "node[kind='entity']", style: {
        ...box(13, t.sans, 600, 12), "background-color": t.accent, "border-width": 0, color: "#fff",
      } },
      { selector: "node[kind='record'], node[kind='related'], node[kind='excluded']", style: {
        ...box(10.5, t.mono, 400, 8), "border-width": 2, "border-color": nodeSrc,
      } },
      { selector: "node[kind='related']", style: { "border-style": "dashed", "background-color": t.sunk } },
      { selector: "node[kind='excluded']", style: { "border-style": "dotted", color: t.text3, opacity: 0.7 } },
      { selector: "node[kind='source']", style: {
        ...box(11, t.mono, 600, 10), "background-color": nodeSrc, "border-width": 0, color: "#fff",
      } },
      { selector: "node[?disabled]", style: { opacity: 0.4 } },
      { selector: "node[kind='attribute']", style: {
        shape: "ellipse", width: 12, height: 12, "background-color": t.bg,
        "border-color": t.text3, "text-valign": "bottom", "text-margin-y": 4,
        "font-size": 10, color: t.text2,
      } },
      { selector: "node[?identifying]", style: { "background-color": t.accent2, "border-color": t.accent2 } },
      { selector: "edge", style: {
        width: 1.2, "line-color": t.border, "curve-style": "bezier", label: "data(label)",
        "font-family": t.mono, "font-size": 9.5, color: t.text3,
        "text-background-color": t.bg, "text-background-opacity": 1, "text-background-padding": 2,
        "text-rotation": "autorotate", "loop-direction": "-45deg", "loop-sweep": "70deg",
      } },
      // Record-to-record edges arc around the centre so they never cross the entity node.
      { selector: "edge[kind='match'], edge[kind='rejected']", style: {
        "curve-style": "unbundled-bezier", "control-point-distances": 90, "control-point-weights": 0.5,
      } },
      { selector: "edge[kind='match']", style: { width: 2.5, "line-color": t.ok, color: t.text2 } },
      { selector: "edge[kind='rejected']", style: { "line-style": "dashed", "line-color": t.text3 } },
      { selector: "edge[kind='rel']", style: {
        width: 2, "line-color": t.accent2, "target-arrow-color": t.accent2,
        "target-arrow-shape": "triangle", color: t.text2,
      } },
      { selector: "edge[kind='binding']", style: {
        "line-color": (e) => sourceColor(e.target().data("source")), "line-opacity": 0.55, "text-opacity": 0,
      } },
      { selector: ".dim", style: { opacity: 0.15 } },
      { selector: "edge.hl", style: { "text-opacity": 1, "line-opacity": 1, "z-index": 9 } },
      { selector: ":selected", style: { "overlay-color": t.accent, "overlay-opacity": 0.15, "overlay-padding": 4 } },
    ];
  }

  function layout(name) {
    if (name === "concentric") {
      // Entity in the centre, everything it touches on one ring around it.
      return { name, concentric: (n) => (n.data("kind") === "entity" ? 2 : 1), levelWidth: () => 1,
               minNodeSpacing: 70, spacingFactor: 1.2, startAngle: Math.PI, padding: 28, animate: false };
    }
    // Columns: entity types → attributes → source systems, each column centred vertically.
    return { name: "preset", padding: 28, positions: columnPositions };
  }

  const COLUMNS = { entity: 0, attribute: 1, source: 2 };
  function columnPositions(node) {
    const col = COLUMNS[node.data("kind")] ?? 1;
    const peers = node.cy().nodes().filter((n) => (COLUMNS[n.data("kind")] ?? 1) === col);
    const gap = col === 1 ? 38 : 120;
    const index = peers.toArray().indexOf(node);
    return { x: col * 230, y: (index - (peers.length - 1) / 2) * gap };
  }

  function init(container) {
    const id = container.dataset.graph;
    const data = document.getElementById(id);
    if (!data || graphs.has(id) || container.offsetParent === null) return;
    const info = document.querySelector(`[data-graph-info="${id}"]`);
    const cy = window.cytoscape({
      container, elements: JSON.parse(data.textContent), style: style(),
      layout: layout(container.dataset.layout), minZoom: 0.3, maxZoom: 2.5,
    });
    const clear = () => cy.elements().removeClass("dim hl");
    cy.on("tap", (e) => {
      clear();
      if (e.target === cy) return;
      const el = e.target;
      const focus = el.isNode() ? el.closedNeighborhood() : el.union(el.connectedNodes());
      cy.elements().not(focus).addClass("dim");
      focus.edges().addClass("hl");
      if (info) info.textContent = el.data("detail") || el.data("label");
    });
    graphs.set(id, cy);
  }

  const initAll = () => document.querySelectorAll("[data-graph]").forEach(init);
  initAll();
  // Graphs inside hidden tabs are built the first time their tab is shown.
  document.addEventListener("tab:shown", (e) => {
    e.target.querySelectorAll("[data-graph]").forEach((c) => {
      const cy = graphs.get(c.dataset.graph);
      if (cy) { cy.resize(); cy.fit(undefined, 28); } else init(c);
    });
  });
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-graph-fit]");
    if (btn) graphs.get(btn.dataset.graphFit)?.fit(undefined, 28);
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    graphs.forEach((cy) => cy.style(style()));
  });
})();
