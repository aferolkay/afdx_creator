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

  /* The gap column carries the offered send rate for both patterns, and colours it by how it
     relates to the BAG:
       grey  - defaulted to the BAG (periodic, nothing entered)
       red   - the average is at or below the BAG: the regulator queue grows and the run aborts
       amber - the range dips below the BAG: legal, but it adds latency
  */
  function gapFormatter(cell) {
    const row = cell.getRow().getData();
    const bag = Number(row.bag_ms);
    const parsed = parseRange(cell.getValue());

    if (!parsed) {
      // Nothing entered: a periodic link simply runs at its BAG.
      if (row.arrival_pattern !== "uniform") {
        return `<span class="cell-auto">${trim(bag)}</span>`;
      }
      return '<span class="cell-bad">?</span>';
    }

    const [low, high] = parsed;
    const mean = high == null ? low : (low + high) / 2;
    const shown = formatRange(low, high);

    if (isFinite(mean) && mean <= bag && !(high == null && low === bag)) {
      return `<span class="cell-bad">${shown}</span>`;
    }
    if (low < bag) return `<span class="cell-warn">${shown}</span>`;
    return shown;
  }

  /* Accepts a single number or a range, in any of the forms a message-set table might use:
       "256"   "683-1183"   "683 - 1183"   "(683, 1183)"   "683,1183"
     Returns [low, high] with high === null when a single value was given. */
  function parseRange(text) {
    if (text == null) return null;
    const cleaned = String(text).replace(/[()\s]/g, "");
    if (!cleaned) return null;
    const parts = cleaned.split(/[-,]/).filter(s => s !== "");
    const numbers = parts.map(Number);
    if (!numbers.length || numbers.some(n => !isFinite(n) || n <= 0)) return null;
    if (numbers.length === 1) return [numbers[0], null];
    if (numbers[1] < numbers[0]) return null;
    return [numbers[0], numbers[1]];
  }

  function formatRange(low, high) {
    if (low == null) return "";
    return (high == null || high === low) ? trim(low) : `${trim(low)}–${trim(high)}`;
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

    // Size from the LARGEST frame, matching trafficmath.rho_sigma on the backend: the policer
    // checks every frame individually, so a bucket sized for a typical one drops the big ones.
    const bytes = parseRange(row.bytes_text);
    if (!bytes || !(bagSeconds > 0)) return null;
    const maxBytes = bytes[1] != null ? bytes[1] : bytes[0];

    const lmax = lmaxBits(maxBytes, header, settings.phy_overhead_bits
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
        { title: "Bytes", field: "bytes_text", editor: "input", width: 80,
          formatter: (cell) => {
            const parsed = parseRange(cell.getValue());
            if (!parsed) return '<span class="cell-bad">?</span>';
            return parsed[1] == null ? trim(parsed[0])
                 : `<span class="cell-manual">${formatRange(parsed[0], parsed[1])}</span>`;
          },
          tooltip: "Payload size in bytes. A range like 683-1183 (or the table's own " +
                   "(683, 1183)) varies the size per frame; rho/sigma are then sized for the " +
                   "largest." },
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
        { title: "Gap (ms)", field: "gap_text", editor: "input", width: 92,
          formatter: (cell) => gapFormatter(cell),
          tooltip: "How often a frame is offered. Periodic: a single value (defaults to the " +
                   "BAG; a larger value sends slower). Sporadic: a range like 2-6, redrawn per " +
                   "frame. The average must stay above the BAG." },
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

      // Choosing a pattern rewrites the gap column to a sensible shape for it, seeded from the
      // CURRENT BAG: a range of BAG..2xBAG for sporadic (safe by construction), or the plain BAG
      // for periodic.
      if (cell.getField() === "arrival_pattern") {
        const bag = Number(row.bag_ms);
        const parsed = parseRange(row.gap_text);
        const isRange = !!parsed && parsed[1] != null;
        if (row.arrival_pattern === "uniform" && !isRange) {
          cell.getRow().update({ gap_text: formatRange(bag, bag * 2) });
        } else if (row.arrival_pattern !== "uniform" && isRange) {
          cell.getRow().update({ gap_text: trim(bag) });
        }
      }
      // Typing a range in the gap column implies sporadic; keep the dropdown honest.
      if (cell.getField() === "gap_text") {
        const parsed = parseRange(cell.getValue());
        const wanted = (parsed && parsed[1] != null) ? "uniform" : "periodic";
        if (row.arrival_pattern !== wanted) cell.getRow().update({ arrival_pattern: wanted });
      }

      writeBack(cell.getRow().getData());
      Store.touch();
      // Turning a link sporadic is what makes the bounds columns relevant.
      updateScrollCue();
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

    // A range in the gap column means sporadic; a single value means periodic. The dropdown and
    // the range notation therefore say the same thing, and the dropdown follows what was typed.
    const gap = parseRange(row.gap_text);
    const isRange = !!gap && gap[1] != null;
    vl.arrival_pattern = (row.arrival_pattern === "uniform" || isRange) ? "uniform" : "periodic";

    if (vl.arrival_pattern === "uniform") {
      vl.arrival_min_s = gap ? gap[0] / 1000 : null;
      vl.arrival_max_s = (gap && gap[1] != null) ? gap[1] / 1000 : null;
      vl.period_s = null;
    } else {
      vl.arrival_min_s = null;
      vl.arrival_max_s = null;
      // Only store a period when it actually differs from the BAG, so the common case stays
      // "follows the BAG" rather than freezing a copy of it.
      const period = gap ? gap[0] / 1000 : null;
      vl.period_s = (period != null && Math.abs(period - vl.bag_s) > 1e-12) ? period : null;
    }

    const bytes = parseRange(row.bytes_text);
    if (bytes) {
      vl.frame_bytes = Math.round(bytes[0]);
      vl.frame_bytes_max = bytes[1] != null ? Math.round(bytes[1]) : null;
    }

    vl.hex_vl_id = String(row.hex_vl_id || "").trim();
    vl.label = row.label || "";
    vl.source_node_id = row.source_node_id;
    vl.destination_node_ids = row.destination_node_ids || [];
    vl.bag_s = (Number(row.bag_ms) || 1) / 1000;
    vl.offset_s = (row.offset_us === "" || row.offset_us == null)
      ? null : Number(row.offset_us) / 1e6;
    vl.rho_bps = (row.rho_bps === "" || row.rho_bps == null) ? null : Number(row.rho_bps);
    vl.sigma_bits = (row.sigma_bits === "" || row.sigma_bits == null) ? null : Number(row.sigma_bits);
  }

  /* What the gap column shows for a saved link. Mirrors the backend's defaults so the table
     reflects what would actually be generated rather than blanks. */
  function gapText(vl) {
    if (vl.arrival_pattern === "uniform") {
      const low = (vl.arrival_min_s != null ? vl.arrival_min_s : vl.bag_s) * 1000;
      const high = (vl.arrival_max_s != null ? vl.arrival_max_s : vl.bag_s * 2) * 1000;
      return formatRange(low, high);
    }
    return trim((vl.period_s != null ? vl.period_s : vl.bag_s) * 1000);
  }

  function toRow(vl) {
    return {
      id: vl.id,
      hex_vl_id: vl.hex_vl_id,
      label: vl.label,
      bytes_text: formatRange(vl.frame_bytes, vl.frame_bytes_max),
      source_node_id: vl.source_node_id,
      destination_node_ids: vl.destination_node_ids,
      bag_ms: vl.bag_s * 1000,
      offset_us: vl.offset_s == null ? "" : vl.offset_s * 1e6,
      arrival_pattern: vl.arrival_pattern || "periodic",
      gap_text: gapText(vl),
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
      frame_bytes_max: null,
      source_node_id: endSystems[0].id,
      destination_node_ids: [endSystems[1].id],
      bag_s: 0.002,
      offset_s: 0,
      arrival_pattern: "periodic",
      period_s: null,
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
    table.setData(project.virtual_links.map(toRow)).then(updateScrollCue);
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
