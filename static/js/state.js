/* The in-browser copy of the project, plus autosave.
   The browser holds the authoritative document while editing and posts the whole thing back. */
window.Store = (function () {
  const SAVE_DELAY_MS = 2000;   // how long after your last edit the save fires
  const MAX_UNDO = 3;           // how many steps back you can go

  let project = null;
  let constants = { phy_overhead_bits: 160, default_sigma_margin_factor: 4.0,
                    default_frame_header_length_bytes: 47 };
  let saveTimer = null;
  let dirty = false;
  const listeners = [];

  // Undo history. Callers mutate the project and THEN call touch(), so by then the change has
  // already happened -- we cannot snapshot at that point. Instead we keep a copy of the state as
  // it was after the previous touch(), and push that copy when the next change arrives.
  let undoStack = [];
  let snapshot = null;

  function clone(value) {
    // The project is plain JSON data, so either method is faithful.
    return typeof structuredClone === "function"
      ? structuredClone(value)
      : JSON.parse(JSON.stringify(value));
  }

  function get() { return project; }
  function setConstants(c) { constants = Object.assign(constants, c || {}); }
  function getConstants() { return constants; }

  function set(newProject) {
    project = newProject;
    // A different project means the old history is meaningless.
    undoStack = [];
    snapshot = clone(newProject);
    dirty = false;
    emit();
    updateUndoButton();
  }

  /* --- undo ------------------------------------------------------------------------------ */
  function canUndo() { return undoStack.length > 0; }

  function undo() {
    if (!undoStack.length) return false;
    project = undoStack.pop();
    snapshot = clone(project);
    dirty = true;
    emit();
    updateUndoButton();
    save();               // persist immediately: an undo you have to remember to save is a trap
    return true;
  }

  function updateUndoButton() {
    const button = document.getElementById("btn-undo");
    if (!button) return;
    button.disabled = !canUndo();
    button.title = canUndo()
      ? `Undo the last change (${undoStack.length} available)`
      : "Nothing to undo";
  }

  function onChange(fn) { listeners.push(fn); }
  function emit() { listeners.forEach(fn => { try { fn(project); } catch (e) { console.error(e); } }); }

  /* Record the change for undo, mark dirty, and schedule a save.
     Debounced so dragging a node doesn't spam the backend. */
  function touch({ immediate = false } = {}) {
    if (snapshot) {
      undoStack.push(snapshot);
      if (undoStack.length > MAX_UNDO) undoStack.shift();   // keep only the most recent steps
    }
    snapshot = clone(project);
    dirty = true;
    updateUndoButton();

    emit();
    setSaveState("unsaved");
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(save, immediate ? 0 : SAVE_DELAY_MS);
  }

  function payload() {
    return {
      name: project.name,
      nodes: project.nodes,
      edges: project.edges,
      virtual_links: project.virtual_links,
      general_settings: project.general_settings,
    };
  }

  async function save() {
    if (!project) return;
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
    setSaveState("saving");
    try {
      await API.saveProject(project.id, payload());
      dirty = false;
      // Re-baseline the undo snapshot. Normally touch() has already done this, but code that
      // populates a project directly and then saves (the starter project does exactly that)
      // would otherwise leave the snapshot describing an older, emptier state -- and the first
      // undo would jump all the way back to it.
      snapshot = clone(project);
      setSaveState("saved");
      refreshProblems();
    } catch (err) {
      setSaveState("error");
      // A rejected save usually means a field failed validation -- show it rather than
      // silently losing the edit.
      showProblems([err.message]);
    }
  }

  /* Waiting 5s before saving means a tab closed mid-edit could lose work. `keepalive` lets the
     request outlive the page, which a normal fetch would not. */
  function flushOnUnload() {
    if (!dirty || !project) return;
    try {
      fetch(`/api/projects/${project.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload()),
        keepalive: true,
      });
    } catch (_) { /* nothing useful to do while the page is going away */ }
  }
  window.addEventListener("beforeunload", flushOnUnload);
  // Covers the phone/tab-switch case, where beforeunload is unreliable.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flushOnUnload();
  });

  /* Re-derive the indicator from the actual state. Anything that temporarily borrows that
     element for a message must call this to hand it back, rather than restoring the text it
     happened to see -- which by then may describe an edit made since. */
  function refreshSaveIndicator() {
    setSaveState(dirty ? "unsaved" : "saved");
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

  return { get, set, touch, save, undo, canUndo, updateUndoButton, refreshSaveIndicator,
           onChange, nextId, showProblems, refreshProblems,
           setConstants, getConstants, escapeHtml };
})();
