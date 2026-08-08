/* The in-browser copy of the project, plus autosave.
   The browser holds the authoritative document while editing and posts the whole thing back. */
window.Store = (function () {
  let project = null;
  let constants = { phy_overhead_bits: 160, default_sigma_margin_factor: 4.0,
                    default_frame_header_length_bytes: 47 };
  let saveTimer = null;
  const listeners = [];

  function get() { return project; }
  function setConstants(c) { constants = Object.assign(constants, c || {}); }
  function getConstants() { return constants; }

  function set(newProject) {
    project = newProject;
    emit();
  }

  function onChange(fn) { listeners.push(fn); }
  function emit() { listeners.forEach(fn => { try { fn(project); } catch (e) { console.error(e); } }); }

  /* Mark dirty and schedule a save. Debounced so dragging a node doesn't spam the backend. */
  function touch({ immediate = false } = {}) {
    emit();
    setSaveState("unsaved");
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(save, immediate ? 0 : 800);
  }

  async function save() {
    if (!project) return;
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
    setSaveState("saving");
    try {
      await API.saveProject(project.id, {
        name: project.name,
        nodes: project.nodes,
        edges: project.edges,
        virtual_links: project.virtual_links,
        general_settings: project.general_settings,
      });
      setSaveState("saved");
      refreshProblems();
    } catch (err) {
      setSaveState("error");
      // A rejected save usually means a field failed validation -- show it rather than
      // silently losing the edit.
      showProblems([err.message]);
    }
  }

  function setSaveState(state) {
    const el = document.getElementById("save-state");
    if (!el) return;
    const labels = { saved: "Saved", saving: "Saving...", unsaved: "Unsaved changes", error: "Save failed" };
    el.textContent = labels[state] || "";
    el.style.color = state === "error" ? "var(--danger)"
                   : state === "saved" ? "var(--muted)" : "var(--warn)";
  }

  async function refreshProblems() {
    if (!project) return;
    try {
      const result = await API.getProblems(project.id);
      showProblems(result.problems || []);
    } catch (_) { /* non-critical */ }
  }

  function showProblems(problems) {
    const box = document.getElementById("problems");
    if (!box) return;
    if (!problems || !problems.length) {
      box.classList.add("hidden");
      box.innerHTML = "";
      return;
    }
    box.classList.remove("hidden");
    box.innerHTML = "<strong>Needs attention before generating:</strong><ul>" +
      problems.map(p => `<li>${escapeHtml(p)}</li>`).join("") + "</ul>";
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = String(text);
    return div.innerHTML;
  }

  function nextId(prefix, existing) {
    let n = 1;
    const taken = new Set(existing.map(item => item.id));
    while (taken.has(prefix + n)) n++;
    return prefix + n;
  }

  return { get, set, touch, save, onChange, nextId, showProblems, refreshProblems,
           setConstants, getConstants, escapeHtml };
})();
