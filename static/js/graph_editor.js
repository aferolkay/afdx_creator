/* Cytoscape topology editor: add nodes, drag to connect, move, delete. */
window.GraphEditor = (function () {
  let cy = null;
  let eh = null;      // edgehandles instance
  let suppress = false; // guard against reacting to our own programmatic changes

  const STYLE = [
    {
      selector: "node",
      style: {
        "label": "data(label)",
        "color": "#e4e9f2",
        "font-size": 12,
        "text-valign": "bottom",
        "text-margin-y": 6,
        "width": 44, "height": 44,
        "border-width": 2,
      },
    },
    {
      selector: 'node[kind="end_system"]',
      style: { "background-color": "#2b6cb0", "border-color": "#4da3ff", "shape": "round-rectangle" },
    },
    {
      selector: 'node[kind="switch"]',
      style: { "background-color": "#276749", "border-color": "#37d39f", "shape": "diamond",
               "width": 52, "height": 52 },
    },
    {
      selector: "edge",
      style: {
        "width": 2.5,
        "line-color": "#4a5768",
        "curve-style": "bezier",
        "label": "data(label)",
        "font-size": 10,
        "color": "#8b97ab",
        "text-background-color": "#10141b",
        "text-background-opacity": 0.85,
        "text-background-padding": 2,
      },
    },
    { selector: ":selected", style: { "border-color": "#ffb454", "border-width": 4, "line-color": "#ffb454" } },
    // edgehandles preview styling
    { selector: ".eh-handle", style: { "background-color": "#ffb454", "width": 11, "height": 11,
        "shape": "ellipse", "overlay-opacity": 0, "border-width": 8, "border-opacity": 0 } },
    { selector: ".eh-ghost-edge, .eh-preview", style: { "line-color": "#ffb454", "target-arrow-color": "#ffb454",
        "source-arrow-color": "#ffb454" } },
  ];

  function init() {
    cy = cytoscape({
      container: document.getElementById("cy"),
      style: STYLE,
      wheelSensitivity: 0.2,
      minZoom: 0.2,
      maxZoom: 3,
    });

    eh = cy.edgehandles({
      snap: true,
      canConnect(source, target) {
        if (source.id() === target.id()) return false;                       // no self loops
        if (source.data("kind") === "end_system" && target.data("kind") === "end_system") {
          return false;                                                      // ES-to-ES is not a thing
        }
        // An end system has exactly one physical port.
        for (const node of [source, target]) {
          if (node.data("kind") === "end_system" && node.degree(false) >= 1) return false;
        }
        return cy.edges().filter(e =>                                        // no duplicate links
          (e.source().id() === source.id() && e.target().id() === target.id()) ||
          (e.source().id() === target.id() && e.target().id() === source.id())
        ).length === 0;
      },
    });

    cy.on("ehcomplete", (event, source, target, added) => {
      // Remove the element edgehandles drew; the store is authoritative and re-renders it.
      added.remove();
      addEdge(source.id(), target.id());
    });

    // Persist positions after a drag so the layout survives a reload.
    cy.on("dragfree", "node", (event) => {
      if (suppress) return;
      const project = Store.get();
      const node = project.nodes.find(n => n.id === event.target.id());
      if (node) {
        const pos = event.target.position();
        node.x = pos.x; node.y = pos.y;
        Store.touch();
      }
    });

    document.getElementById("btn-add-es").onclick = () => addNode("end_system");
    document.getElementById("btn-add-sw").onclick = () => addNode("switch");
    document.getElementById("btn-delete-node").onclick = deleteSelected;
    document.getElementById("btn-layout").onclick = () => runLayout(true);

    document.addEventListener("keydown", (event) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
      if (!typing && (event.key === "Delete" || event.key === "Backspace")) {
        if (cy.$(":selected").length) { event.preventDefault(); deleteSelected(); }
      }
    });
  }

  function defaultLabel(kind, project) {
    const prefix = kind === "switch" ? "S" : "E";
    const used = new Set(project.nodes.map(n => n.label));
    // End systems conventionally start at 0, switches at 1.
    let i = kind === "switch" ? 1 : 0;
    while (used.has(prefix + i)) i++;
    return prefix + i;
  }

  function addNode(kind) {
    const project = Store.get();
    if (!project) return;
    const extent = cy.extent();
    const node = {
      id: Store.nextId(kind === "switch" ? "sw" : "es", project.nodes),
      kind,
      label: defaultLabel(kind, project),
      // Drop it near the middle of the current view, jittered so repeats don't stack.
      x: (extent.x1 + extent.x2) / 2 + (Math.random() - 0.5) * 120,
      y: (extent.y1 + extent.y2) / 2 + (Math.random() - 0.5) * 120,
    };
    project.nodes.push(node);
    Store.touch();
    render();
  }

  function addEdge(sourceId, targetId) {
    const project = Store.get();
    project.edges.push({
      id: Store.nextId("e", project.edges),
      node_a_id: sourceId,
      node_b_id: targetId,
      length_m: project.general_settings.channel_length_m || 10,
      datarate_bps: null,
    });
    Store.touch();
    render();
  }

  function deleteSelected() {
    const project = Store.get();
    const selected = cy.$(":selected");
    if (!selected.length) return;

    const nodeIds = selected.filter("node").map(n => n.id());
    const edgeIds = selected.filter("edge").map(e => e.id());

    // Deleting a node takes its links with it.
    const removedEdges = new Set(edgeIds);
    project.edges.forEach(edge => {
      if (nodeIds.includes(edge.node_a_id) || nodeIds.includes(edge.node_b_id)) {
        removedEdges.add(edge.id);
      }
    });

    // Warn before silently invalidating virtual links that referenced what's being removed.
    const affected = project.virtual_links.filter(vl =>
      nodeIds.includes(vl.source_node_id) ||
      vl.destination_node_ids.some(d => nodeIds.includes(d)) ||
      (vl.explicit_path_edge_ids || []).some(e => removedEdges.has(e))
    );
    if (affected.length) {
      const names = affected.map(vl => vl.label || vl.hex_vl_id).join(", ");
      if (!confirm(`This also affects ${affected.length} virtual link(s): ${names}.\n\n` +
                   `Links losing an endpoint will be removed; explicit routes using a deleted ` +
                   `link will fall back to the shortest path.\n\nContinue?`)) return;
    }

    project.nodes = project.nodes.filter(n => !nodeIds.includes(n.id));
    project.edges = project.edges.filter(e => !removedEdges.has(e.id));
    project.virtual_links = project.virtual_links.filter(vl =>
      !nodeIds.includes(vl.source_node_id) &&
      !vl.destination_node_ids.some(d => nodeIds.includes(d))
    );
    project.virtual_links.forEach(vl => {
      if ((vl.explicit_path_edge_ids || []).some(e => removedEdges.has(e))) {
        vl.explicit_path_edge_ids = null;
      }
    });

    Store.touch({ immediate: true });
    render();
    if (window.VLTable) VLTable.refresh();
  }

  function render() {
    const project = Store.get();
    if (!cy || !project) return;

    suppress = true;
    cy.elements().remove();

    cy.add(project.nodes.map(node => ({
      group: "nodes",
      data: { id: node.id, label: node.label || node.id, kind: node.kind },
      position: { x: node.x || 0, y: node.y || 0 },
    })));

    cy.add(project.edges.map(edge => ({
      group: "edges",
      data: { id: edge.id, source: edge.node_a_id, target: edge.node_b_id, label: "" },
    })));

    suppress = false;

    // First open of a project with no saved positions: arrange it automatically.
    const unpositioned = project.nodes.every(n => !n.x && !n.y);
    if (unpositioned && project.nodes.length) runLayout(false);
  }

  function runLayout(fit) {
    if (!cy || !cy.nodes().length) return;
    const layout = cy.layout({
      name: "cose",
      animate: false,
      padding: 40,
      nodeRepulsion: 9000,
      idealEdgeLength: 110,
avoidOverlap: true,
    });
    layout.run();
    // Persist whatever the layout decided, so it's stable next time.
    const project = Store.get();
    cy.nodes().forEach(n => {
      const node = project.nodes.find(item => item.id === n.id());
      if (node) { const p = n.position(); node.x = p.x; node.y = p.y; }
    });
    if (fit) cy.fit(undefined, 40);
    Store.touch();
  }

  function fit() { if (cy) cy.fit(undefined, 40); }

  return { init, render, fit, runLayout };
})();
