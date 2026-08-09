/* Virtual-link table.

   rho/sigma are computed here for instant feedback while typing. That duplicates the formula in
   trafficmath/rho_sigma.py -- deliberately, and documented there. The CONSTANTS it uses
   (phy overhead, default margin) are fetched from /api/constants rather than hardcoded, so the
   numbers cannot drift even though the arithmetic appears twice. */
window.VLTable = (function () {
  let table = null;

  /* Mirrors trafficmath.rho_sigma.wire_frame_bits */
  function lmaxBits(payloadBytes, headerBytes, phyOverheadBits) {
    return (Number(payloadBytes) + Number(headerBytes)) * 8 + Number(phyOverheadBits);
  }

  /* Min/Max only mean something for a sporadic link; show a dash otherwise so a stale number
     never looks like it is in effect. Also warns inline when the value would misbehave. */
  function sporadicOnly(cell) {
    const row = cell.getRow().getData();
    if (row.arrival_pattern !== "uniform") return '<span class="cell-auto">&mdash;</span>';
    const value = Number(cell.getValue());
    if (!isFinite(value)) return '<span class="cell-auto">&mdash;</span>';

    const bag = Number(row.bag_ms);
    const lo = Number(row.arrival_min_ms), hi = Number(row.arrival_max_ms);
    const mean = (lo + hi) / 2;
    // Mean at or below BAG eventually aborts the run; flag it in the table, not just at generate.
    if (isFinite(mean) && mean <= bag) return `<span class="cell-bad">${trim(value)}</span>`;
    if (cell.getField() === "arrival_min_ms" && value < bag) {
      return `<span class="cell-warn">${trim(value)}</span>`;
    }
    return trim(value);
  }

  /* Round-tripping seconds <-> microseconds leaves float noise (503.68 -> 503.68000000000006).
     Show a clean number without discarding a genuinely precise value. */
  function trim(value) {
    if (value === "" || value == null) return "";
    const n = Number(value);
    if (!isFinite(n)) return "";
    return String(Math.round(n * 1e6) / 1e6);
  }

  function autoValues(row) {
    const project = Store.get();
    const constants = Store.getConstants();
    const settings = project.general_settings;

    const header = row.frame_header_length_override != null
      ? row.frame_header_length_override
      : settings.frame_header_length_bytes;
    const margin = row.sigma_margin_factor_override || settings.sigma_margin_factor;
    const bagSeconds = Number(row.bag_ms) / 1000;

    if (!(bagSeconds > 0) || !(Number(row.frame_bytes) > 0)) return null;

    const lmax = lmaxBits(row.frame_bytes, header, settings.phy_overhead_bits
                                                  ?? constants.phy_overhead_bits);
    return { lmax, rho: lmax / bagSeconds, sigma: lmax * margin };
  }

  function nodeOptions() {
    const project = Store.get();
    const options = {};
    project.nodes.filter(n => n.kind === "end_system")
      .forEach(n => { options[n.id] = n.label || n.id; });
    return options;
  }

  /* Show the effective value, greyed when it came from the formula rather than the user. */
  function derivedFormatter(field, digits, scale) {
    return function (cell) {
      const row = cell.getRow().getData();
      const manual = row[field];
      if (manual != null && manual !== "") {
        return `<span class="cell-manual">${(Number(manual) / scale).toFixed(digits)}</span>`;
      }
      const auto = autoValues(row);
      if (!auto) return `<span class="cell-auto">-</span>`;
      const value = field === "rho_bps" ? auto.rho : auto.sigma;
      return `<span class="cell-auto">${(value / scale).toFixed(digits)}</span>`;
    };
  }

  function init() {
    table = new Tabulator("#vl-table", {
      // "fitData" honours each column's declared width and lets the table scroll sideways when
      // they do not all fit. "fitColumns" squeezes everything into view instead, which silently
      // pushed the rightmost columns (sigma, rho) out of reach once the arrival columns arrived.
      layout: "fitData",
      height: "100%",
      selectableRows: true,
      placeholder: "No virtual links yet. Add one to describe a traffic stream.",
      columns: [
        { title: "VL id", field: "hex_vl_id", editor: "input", width: 62,
          tooltip: "Hex identifier, e.g. 0x1. Must be unique." },
        { title: "Name", field: "label", editor: "input", width: 60 },
        { title: "Bytes", field: "frame_bytes", editor: "number", width: 62,
          editorParams: { min: 1 }, tooltip: "Application payload size." },
        { title: "From", field: "source_node_id", width: 66,
          editor: "list", editorParams: { valuesLookup: nodeOptions },
          formatter: (cell) => nodeOptions()[cell.getValue()] || "-" },
        { title: "To", field: "destination_node_ids", width: 96,
          tooltip: "Destination end systems. Several = multicast.",
          formatter: (cell) => {
            const options = nodeOptions();
            const values = cell.getValue() || [];
            return values.map(v => options[v] || v).join(", ") || "-";
          },
          cellClick: (event, cell) => editDestinations(cell),
        },
        { title: "BAG (ms)", field: "bag_ms", editor: "number", width: 74,
          editorParams: { min: 0.001, step: 0.5 },
          formatter: (cell) => trim(cell.getValue()),
          tooltip: "Minimum interval between frames." },
        { title: "Offset (us)", field: "offset_us", editor: "number", width: 78,
          formatter: (cell) => trim(cell.getValue()),
          tooltip: "Release offset of the first frame." },
        { title: "Arrival", field: "arrival_pattern", width: 76,
          editor: "list",
          editorParams: { values: { periodic: "periodic", uniform: "sporadic" } },
          formatter: (cell) => cell.getValue() === "uniform"
            ? '<span class="cell-manual">sporadic</span>'
            : '<span class="cell-auto">periodic</span>',
          tooltip: "periodic = one frame every BAG. sporadic = the gap is redrawn at random " +
                   "from the Min..Max range for every frame." },
        { title: "Min (ms)", field: "arrival_min_ms", editor: "number", width: 74,
          formatter: (cell) => sporadicOnly(cell),
          tooltip: "Sporadic only: shortest possible gap. Below BAG is allowed but the " +
                   "regulator will hold frames back, adding latency." },
        { title: "Max (ms)", field: "arrival_max_ms", editor: "number", width: 74,
          formatter: (cell) => sporadicOnly(cell),
          tooltip: "Sporadic only: longest possible gap. Keep the average above BAG." },
        { title: "rho (Mbps)", field: "rho_bps", editor: "number", width: 84,
          formatter: derivedFormatter("rho_bps", 3, 1e6),
          tooltip: "Sustained rate. Blank = computed as Lmax/BAG.",
          editorParams: { min: 0 },
          mutatorEdit: (value) => (value === "" || value == null) ? null : Number(value) * 1e6,
          accessorEdit: (value) => (value == null) ? "" : Number(value) / 1e6 },
        { title: "sigma (bits)", field: "sigma_bits", editor: "number", width: 88,
          formatter: derivedFormatter("sigma_bits", 0, 1),
          tooltip: "Burst allowance. Blank = margin x Lmax.",
          editorParams: { min: 0 },
          mutatorEdit: (value) => (value === "" || value == null) ? null : Number(value) },
      ],
    });

    table.on("cellEdited", (cell) => {
      const row = cell.getRow().getData();

      // Switching to sporadic: seed the bounds from the CURRENT BAG rather than whatever was
      // last shown, so the defaults are always min = BAG, max = 2 x BAG and safe by construction.
      if (cell.getField() === "arrival_pattern" && row.arrival_pattern === "uniform") {
        cell.getRow().update({
          arrival_min_ms: Number(row.bag_ms),
          arrival_max_ms: Number(row.bag_ms) * 2,
        });
      }

      writeBack(cell.getRow().getData());
      Store.touch();
      // Turning a link sporadic is what makes the bounds columns relevant.
      if (cell.getField() === "arrival_pattern") applyColumnVisibility();
      // Several columns are rendered from OTHER columns -- rho/sigma from bytes and BAG, the
      // arrival bounds from the pattern and BAG. Tabulator does not know about those
      // dependencies and reuses cached cells on a plain redraw(), which leaves stale values on
      // screen. `true` forces a full re-render, which is what keeps the derived columns honest.
      table.redraw(true);
    });

    document.getElementById("btn-add-vl").onclick = addVL;
    document.getElementById("btn-delete-vl").onclick = deleteSelected;
  }

  /* Dialog-free multi-select: a prompt keeps this dependency-light and works offline. */
  function editDestinations(cell) {
    const options = nodeOptions();
    const row = cell.getRow().getData();
    const labels = Object.entries(options).map(([id, label]) => label);
    const current = (row.destination_node_ids || []).map(id => options[id]).join(", ");
    const answer = prompt(
      `Destination end system(s) for ${row.label || row.hex_vl_id}.\n` +
      `Comma-separated for multicast.\n\nAvailable: ${labels.join(", ")}`,
      current
    );
    if (answer === null) return;

    const byLabel = {};
    Object.entries(options).forEach(([id, label]) => { byLabel[label.toLowerCase()] = id; });

    const chosen = [];
    const unknown = [];
    answer.split(",").map(s => s.trim()).filter(Boolean).forEach(name => {
      const id = byLabel[name.toLowerCase()];
      if (id) { if (!chosen.includes(id)) chosen.push(id); } else unknown.push(name);
    });

    if (unknown.length) { alert(`Not an end system: ${unknown.join(", ")}`); return; }
    if (!chosen.length) { alert("A virtual link needs at least one destination."); return; }

    cell.getRow().update({ destination_node_ids: chosen });
    writeBack(cell.getRow().getData());
    Store.touch();
  }

  /* Table rows use display-friendly units; the project model stores SI. */
  function writeBack(row) {
    const project = Store.get();
    const vl = project.virtual_links.find(item => item.id === row.id);
    if (!vl) return;

    vl.arrival_pattern = row.arrival_pattern === "uniform" ? "uniform" : "periodic";
    if (vl.arrival_pattern === "uniform") {
      vl.arrival_min_s = (Number(row.arrival_min_ms) || 0) / 1000 || null;
      vl.arrival_max_s = (Number(row.arrival_max_ms) || 0) / 1000 || null;
    } else {
      // Keep the model clean: bounds that are not in effect are not stored.
      vl.arrival_min_s = null;
      vl.arrival_max_s = null;
    }

    vl.hex_vl_id = String(row.hex_vl_id || "").trim();
    vl.label = row.label || "";
    vl.frame_bytes = Number(row.frame_bytes) || 1;
    vl.source_node_id = row.source_node_id;
    vl.destination_node_ids = row.destination_node_ids || [];
    vl.bag_s = (Number(row.bag_ms) || 1) / 1000;
    vl.offset_s = (row.offset_us === "" || row.offset_us == null)
      ? null : Number(row.offset_us) / 1e6;
    vl.rho_bps = (row.rho_bps === "" || row.rho_bps == null) ? null : Number(row.rho_bps);
    vl.sigma_bits = (row.sigma_bits === "" || row.sigma_bits == null) ? null : Number(row.sigma_bits);
  }

  function toRow(vl) {
    return {
      id: vl.id,
      hex_vl_id: vl.hex_vl_id,
      label: vl.label,
      frame_bytes: vl.frame_bytes,
      source_node_id: vl.source_node_id,
      destination_node_ids: vl.destination_node_ids,
      bag_ms: vl.bag_s * 1000,
      offset_us: vl.offset_s == null ? "" : vl.offset_s * 1e6,
      arrival_pattern: vl.arrival_pattern || "periodic",
      // Mirror the backend's defaults (min = BAG, max = 2 x BAG) so the table shows what would
      // actually be generated rather than blanks.
      arrival_min_ms: (vl.arrival_min_s != null ? vl.arrival_min_s : vl.bag_s) * 1000,
      arrival_max_ms: (vl.arrival_max_s != null ? vl.arrival_max_s : vl.bag_s * 2) * 1000,
      rho_bps: vl.rho_bps,
      sigma_bits: vl.sigma_bits,
      frame_header_length_override: vl.frame_header_length_override,
      sigma_margin_factor_override: vl.sigma_margin_factor_override,
    };
  }

  function addVL() {
    const project = Store.get();
    const endSystems = project.nodes.filter(n => n.kind === "end_system");
    if (endSystems.length < 2) {
      alert("Add at least two end systems to the topology first.");
      return;
    }
    const usedIds = new Set(project.virtual_links.map(vl => parseInt(vl.hex_vl_id, 16)));
    let next = 1;
    while (usedIds.has(next)) next++;

    project.virtual_links.push({
      id: Store.nextId("vl", project.virtual_links),
      hex_vl_id: "0x" + next.toString(16).toUpperCase(),
      label: "V" + next,
      frame_bytes: 256,
      source_node_id: endSystems[0].id,
      destination_node_ids: [endSystems[1].id],
      bag_s: 0.002,
      offset_s: 0,
      arrival_pattern: "periodic",
      arrival_min_s: null,
      arrival_max_s: null,
      rho_bps: null,
      sigma_bits: null,
      explicit_path_edge_ids: null,
      partition_id: null,
      frame_header_length_override: null,
      sigma_margin_factor_override: null,
    });
    Store.touch();
    refresh();
  }

  function deleteSelected() {
    const rows = table.getSelectedData();
    if (!rows.length) { alert("Select one or more rows first."); return; }
    const project = Store.get();
    const ids = new Set(rows.map(r => r.id));
    project.virtual_links = project.virtual_links.filter(vl => !ids.has(vl.id));
    Store.touch({ immediate: true });
    refresh();
  }

  function refresh() {
    const project = Store.get();
    if (!table || !project) return;
    table.setData(project.virtual_links.map(toRow)).then(applyColumnVisibility);
  }

  /* The arrival bounds are dashes for every row unless something is sporadic, so they are hidden
     until they mean something. With 12 columns and a side panel that is only ~700px on a laptop,
     two columns of dashes are the difference between Arrival being on screen or not. */
  function applyColumnVisibility() {
    if (!table) return;
    const project = Store.get();
    const anySporadic = (project?.virtual_links || []).some(vl => vl.arrival_pattern === "uniform");
    ["arrival_min_ms", "arrival_max_ms"].forEach(field => {
      const column = table.getColumn(field);
      if (!column) return;
      if (anySporadic) column.show(); else column.hide();
    });
    updateScrollCue();
  }

  /* Tell the user the table scrolls sideways. Without this the rightmost columns simply look
     absent -- which is exactly how the Arrival column went missing on a narrower screen. */
  function updateScrollCue() {
    const host = document.getElementById("vl-table");
    const holder = host?.querySelector(".tabulator-tableholder");
    if (!holder) return;
    const update = () => {
      const overflowing = holder.scrollWidth - holder.clientWidth > 2;
      const atEnd = holder.scrollLeft + holder.clientWidth >= holder.scrollWidth - 2;
      host.classList.toggle("has-more-columns", overflowing && !atEnd);
    };
    if (!holder.dataset.cueBound) {
      holder.addEventListener("scroll", update);
      window.addEventListener("resize", update);
      holder.dataset.cueBound = "1";
    }
    update();
  }

  return { init, refresh };
})();
