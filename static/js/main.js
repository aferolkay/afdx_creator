/* Page bootstrap: project loading, tabs, generate/validate actions. */
(function () {
  const LAST_PROJECT_KEY = "afdx_generator.lastProject";

  async function boot() {
    GraphEditor.init();
    VLTable.init();
    wireTabs();
    wireActions();

    try { Store.setConstants(await API.getConstants()); } catch (_) { /* defaults are fine */ }

    const projects = await API.listProjects();
    populateProjectList(projects);

    const remembered = localStorage.getItem(LAST_PROJECT_KEY);
    const target = projects.find(p => p.id === remembered) || projects[0];

    if (target) {
      await openProject(target.id);
    } else {
      await createProject("My AFDX network", { seed: true });
    }
  }

  function populateProjectList(projects, selectedId) {
    const select = document.getElementById("project-select");
    select.innerHTML = projects.map(p =>
      `<option value="${p.id}">${Store.escapeHtml(p.name)}</option>`).join("");
    if (selectedId) select.value = selectedId;
  }

  async function openProject(id) {
    const project = await API.getProject(id);
    Store.set(project);
    localStorage.setItem(LAST_PROJECT_KEY, id);
    document.getElementById("project-select").value = id;

    GraphEditor.render();
    GraphEditor.fit();
    VLTable.refresh();
    SettingsPanel.renderGeneral();
    Store.refreshProblems();
    setOutput('<p class="hint">Generate the network to see results here.</p>');
  }

  async function createProject(name, { seed = false } = {}) {
    const created = await API.createProject(name);
    Store.set(created);

    if (seed) {
      // A brand-new install with an empty canvas gives no hint of what to do. Start with the
      // smallest meaningful AFDX network: two end systems either side of one switch.
      created.nodes = [
        { id: "es1", kind: "end_system", label: "E0", x: -170, y: 0 },
        { id: "es2", kind: "end_system", label: "E1", x: 170, y: 0 },
        { id: "sw1", kind: "switch", label: "S1", x: 0, y: 0 },
      ];
      created.edges = [
        { id: "e1", node_a_id: "es1", node_b_id: "sw1", length_m: 10, datarate_bps: null },
        { id: "e2", node_a_id: "sw1", node_b_id: "es2", length_m: 10, datarate_bps: null },
      ];
      created.virtual_links = [{
        id: "vl1", hex_vl_id: "0x1", label: "V1", frame_bytes: 256,
        source_node_id: "es1", destination_node_ids: ["es2"],
        bag_s: 0.002, offset_s: 0,
        rho_bps: null, sigma_bits: null, explicit_path_edge_ids: null,
        partition_id: null, frame_header_length_override: null,
        sigma_margin_factor_override: null,
      }];
      await Store.save();
    }

    populateProjectList(await API.listProjects(), created.id);
    localStorage.setItem(LAST_PROJECT_KEY, created.id);

    GraphEditor.render();
    GraphEditor.fit();
    VLTable.refresh();
    SettingsPanel.renderGeneral();
    Store.refreshProblems();
  }

  function wireTabs() {
    document.querySelectorAll(".tab").forEach(tab => {
      tab.onclick = async () => {
        document.querySelectorAll(".tab").forEach(t => t.classList.remove("tab-active"));
        tab.classList.add("tab-active");
        document.querySelectorAll(".tab-body").forEach(body => body.classList.add("hidden"));
        document.getElementById("tab-" + tab.dataset.tab).classList.remove("hidden");

        if (tab.dataset.tab === "settings") SettingsPanel.renderGeneral();
        if (tab.dataset.tab === "env") await SettingsPanel.renderEnvironment();
      };
    });
  }

  function showTab(name) {
    const tab = document.querySelector(`.tab[data-tab="${name}"]`);
    if (tab) tab.click();
  }

  function wireActions() {
    document.getElementById("project-select").onchange = (event) => openProject(event.target.value);

    document.getElementById("btn-new-project").onclick = async () => {
      const name = prompt("Name for the new network:", "My AFDX network");
      if (name) await createProject(name.trim());
    };

    document.getElementById("btn-save").onclick = () => Store.save();

    document.getElementById("btn-generate").onclick = () => runAction(false);
    document.getElementById("btn-validate").onclick = () => runAction(true);
  }

  async function runAction(withValidation) {
    const buttons = [document.getElementById("btn-generate"),
                     document.getElementById("btn-validate")];
    buttons.forEach(b => b.disabled = true);
    showTab("output");
    setOutput(`<p class="hint">${withValidation
      ? "Generating, then running the simulator. This can take a while."
      : "Generating..."}</p>`);

    try {
      await Store.save();
      const result = withValidation
        ? await API.validate(Store.get().id)
        : await API.generate(Store.get().id);
      setOutput(withValidation ? renderValidation(result) : renderGeneration(result));
    } catch (err) {
      setOutput(`<div class="result-banner result-fail">Could not complete</div>
                 <pre class="log">${Store.escapeHtml(err.message)}</pre>`);
    } finally {
      buttons.forEach(b => b.disabled = false);
    }
  }

  function renderGeneration(result) {
    const warnings = (result.warnings || []).length
      ? `<div class="result-banner result-warn">Generated with ${result.warnings.length} warning(s)</div>
         ${result.warnings.map(w => `<div class="issue"><div class="issue-title">${Store.escapeHtml(w)}</div></div>`).join("")}`
      : `<div class="result-banner result-pass">Generated successfully</div>`;

    return warnings +
      `<p class="hint" style="padding-left:0">Written to <code>${Store.escapeHtml(result.directory)}</code></p>
       <ul class="file-list">${result.files.map(f => `<li>${Store.escapeHtml(f)}</li>`).join("")}</ul>
       ${renderRoutes(result.virtual_links)}`;
  }

  function renderRoutes(vls) {
    if (!vls || !vls.length) return "";
    return `<table class="route-preview">
      <thead><tr><th>Link</th><th>Route</th><th>rho (Mbps)</th><th>sigma (bits)</th></tr></thead>
      <tbody>${vls.map(vl => `
        <tr>
          <td><code>${Store.escapeHtml(vl.label)}</code></td>
          <td>${Store.escapeHtml(vl.route)}</td>
          <td>${(vl.rho_bps / 1e6).toFixed(3)}${vl.auto_rho ? "" : " *"}</td>
          <td>${Math.round(vl.sigma_bits)}${vl.auto_sigma ? "" : " *"}</td>
        </tr>`).join("")}</tbody>
    </table><p class="hint" style="padding-left:0">* set manually rather than computed</p>`;
  }

  function renderValidation(result) {
    const banner = result.passed
      ? `<div class="result-banner result-pass">Validation passed &mdash; no dropped frames or errors</div>`
      : `<div class="result-banner result-fail">Validation failed</div>`;

    const generationWarnings = (result.generation_warnings || []).map(w =>
      `<div class="issue"><div class="issue-title">${Store.escapeHtml(w)}</div></div>`).join("");

    const issues = (result.issues || []).map(issue => `
      <div class="issue">
        <div class="issue-title">${Store.escapeHtml(issue.message)}
          ${issue.count > 1 ? `<span class="issue-count">&times;${issue.count}</span>` : ""}
        </div>
        ${issue.hint ? `<div class="issue-hint">${Store.escapeHtml(issue.hint)}</div>` : ""}
      </div>`).join("");

    const timing = result.duration_s
      ? `<p class="hint" style="padding-left:0">Simulator ran for ${result.duration_s.toFixed(1)}s.</p>` : "";

    return banner + generationWarnings + issues + timing +
      (result.stdout_tail
        ? `<details><summary class="hint" style="padding-left:0;cursor:pointer">Simulator output</summary>
           <pre class="log">${Store.escapeHtml(result.stdout_tail)}</pre></details>`
        : "");
  }

  function setOutput(html) {
    document.getElementById("output-content").innerHTML = html;
  }

  document.addEventListener("DOMContentLoaded", () => {
    boot().catch(err => {
      document.body.insertAdjacentHTML("afterbegin",
        `<div class="problems">Could not start: ${Store.escapeHtml(err.message)}</div>`);
      console.error(err);
    });
  });
})();
