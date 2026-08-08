/* General settings and environment configuration forms, built from a declarative spec. */
window.SettingsPanel = (function () {

  const SECTIONS = [
    {
      title: "Traffic policing",
      note: "Controls the token bucket every switch port checks each frame against.",
      callout:
        "<strong>sigma margin:</strong> the textbook value is 1x Lmax, which does not work in " +
        "practice &mdash; policing happens at every hop, and other links sharing a port perturb " +
        "a link's timing enough that a one-frame allowance underruns. 4x was the smallest margin " +
        "that ran clean on the reference network. Raise it if validation reports dropped frames.",
      fields: [
        { key: "sigma_margin_factor", label: "sigma margin factor", type: "number", step: 0.5,
          sub: "sigma = this x Lmax" },
        { key: "frame_header_length_bytes", label: "Frame header", type: "number",
          sub: "bytes added to the payload to form the wire frame" },
        { key: "phy_overhead_bits", label: "Physical overhead", type: "number", readonly: true,
          sub: "bits; fixed in the AFDX library's C++ and shown here for reference only" },
      ],
    },
    {
      title: "Technological latencies",
      note: "Fixed per-hop delays applied inside end systems and switches.",
      callout:
        "<strong>Unverified:</strong> these are conventional values, not calibrated against a " +
        "published AFDX delay model. Simulated end-to-end latency is sensitive to them, so treat " +
        "absolute latency figures as provisional until you have checked them against your reference.",
      fields: [
        { key: "switch_fabric_delay_s", label: "Switch fabric delay", type: "number", scale: 1e6,
          unit: "us", step: 1 },
        { key: "latency_tech_tx_delay_s", label: "End system TX delay", type: "number", scale: 1e6,
          unit: "us", step: 1 },
        { key: "latency_tech_rx_delay_s", label: "End system RX delay", type: "number", scale: 1e6,
          unit: "us", step: 1 },
      ],
    },
    {
      title: "Redundancy",
      note: "AFDX transmits every frame on two independent networks; the receiver drops the second copy.",
      fields: [
        { key: "skew_max_s", label: "Max skew", type: "number", scale: 1e3, unit: "ms", step: 1,
          sub: "how far apart the two copies may arrive" },
        { key: "redundancy_copy_to_link_a", label: "Transmit on plane A", type: "checkbox" },
        { key: "redundancy_copy_to_link_b", label: "Transmit on plane B", type: "checkbox" },
        { key: "skew_max_test_enabled", label: "Skew test enabled", type: "checkbox" },
      ],
    },
    {
      title: "Physical layer",
      fields: [
        { key: "channel_datarate_bps", label: "Link rate", type: "number", scale: 1e6, unit: "Mbps" },
        { key: "channel_length_m", label: "Cable length", type: "number", unit: "m" },
      ],
    },
    {
      title: "Queueing",
      fields: [
        { key: "regulator_max_vlid_queue_size", label: "Max queue per link", type: "number",
          sub: "frames; the run aborts if a link exceeds this" },
        { key: "scheduler_service_time_s", label: "Scheduler service time", type: "number",
          scale: 1e6, unit: "us" },
      ],
    },
    {
      title: "Validation",
      fields: [
        { key: "validation_sim_time_limit_s", label: "Simulated duration", type: "number",
          unit: "s", step: 0.5,
          sub: "longer runs catch problems that only appear once traffic patterns align" },
      ],
    },
  ];

  const ENV_FIELDS = [
    { key: "binary_path", label: "Simulator binary",
      placeholder: "/path/to/project/src/yourSimulation_dbg",
      sub: "the compiled OMNeT++ executable" },
    { key: "omnetpp_lib_dir", label: "OMNeT++ lib directory",
      placeholder: "/path/to/omnetpp-6.x/lib" },
    { key: "afdx_src_dir", label: "AFDX library src",
      placeholder: "/path/to/AFDX-master/afdx/src" },
    { key: "queueinglib_dir", label: "Queueing library",
      placeholder: "/path/to/AFDX-master/queueinglib" },
    { key: "project_src_dir", label: "Target project src", placeholder: "/path/to/yourProject/src",
      sub: "optional; only needed if your project defines its own NED types" },
  ];

  function renderGeneral() {
    const container = document.getElementById("tab-settings");
    const settings = Store.get().general_settings;
    container.innerHTML = SECTIONS.map(section => `
      <div class="form-section">
        <h3>${section.title}</h3>
        ${section.note ? `<p class="section-note">${section.note}</p>` : ""}
        ${section.callout ? `<div class="callout">${section.callout}</div>` : ""}
        ${section.fields.map(field => renderField(field, settings)).join("")}
      </div>`).join("");

    container.querySelectorAll("[data-key]").forEach(input => {
      input.addEventListener("change", () => {
        const key = input.dataset.key;
        const spec = SECTIONS.flatMap(s => s.fields).find(f => f.key === key);
        const settings = Store.get().general_settings;
        if (spec.type === "checkbox") {
          settings[key] = input.checked;
        } else {
          const value = Number(input.value);
          if (!isFinite(value)) return;
          settings[key] = spec.scale ? value / spec.scale : value;
        }
        Store.touch();
        if (window.VLTable) VLTable.refresh();  // margin/header changes move the derived columns
      });
    });
  }

  function renderField(field, settings) {
    const raw = settings[field.key];
    if (field.type === "checkbox") {
      return `<div class="field">
        <label>${field.label}${field.sub ? `<span class="sub">${field.sub}</span>` : ""}</label>
        <input type="checkbox" data-key="${field.key}" ${raw ? "checked" : ""}>
      </div>`;
    }
    const shown = field.scale ? Number(raw) * field.scale : raw;
    const label = field.unit ? `${field.label} (${field.unit})` : field.label;
    return `<div class="field">
      <label>${label}${field.sub ? `<span class="sub">${field.sub}</span>` : ""}</label>
      <input type="number" data-key="${field.key}" value="${shown}"
             ${field.step ? `step="${field.step}"` : 'step="any"'}
             ${field.readonly ? "readonly" : ""}>
    </div>`;
  }

  async function renderEnvironment() {
    const container = document.getElementById("tab-env");
    let config = {};
    try { config = await API.getEnvironment(); } catch (_) { config = {}; }

    container.innerHTML = `
      <div class="form-section">
        <h3>Simulator paths</h3>
        <p class="section-note">
          Needed to run the generated network. These are specific to this machine, so they are
          stored outside the project file &mdash; a project stays portable.
        </p>
        ${ENV_FIELDS.map(field => `
          <div class="field" style="grid-template-columns: 1fr; gap: 4px;">
            <label>${field.label}${field.sub ? `<span class="sub">${field.sub}</span>` : ""}</label>
            <input type="text" data-env="${field.key}"
                   value="${Store.escapeHtml(config[field.key] || "")}"
                   placeholder="${field.placeholder || ""}">
          </div>`).join("")}
        <button id="btn-save-env" class="btn btn-small">Save paths</button>
        <span id="env-save-state" class="hint inline"></span>
      </div>`;

    document.getElementById("btn-save-env").onclick = async () => {
      const payload = {};
      container.querySelectorAll("[data-env]").forEach(input => {
        payload[input.dataset.env] = input.value.trim();
      });
      const state = document.getElementById("env-save-state");
      try {
        await API.saveEnvironment(payload);
        state.textContent = "Saved.";
      } catch (err) {
        state.textContent = err.message;
      }
    };
  }

  return { renderGeneral, renderEnvironment };
})();
