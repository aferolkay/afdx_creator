/* Thin fetch wrapper. Every backend call goes through here. */
window.API = (function () {
  async function request(method, url, body) {
    const options = { method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined) options.body = JSON.stringify(body);

    const response = await fetch(url, options);
    if (response.status === 204) return null;

    const text = await response.text();
    let payload = null;
    try { payload = text ? JSON.parse(text) : null; } catch (_) { payload = text; }

    if (!response.ok) {
      const error = new Error(describeError(payload, response.status));
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  function describeError(payload, status) {
    const detail = payload && payload.detail;
    if (detail && detail.problems) return detail.problems.join("\n");
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      // FastAPI validation errors: surface the field that was rejected.
      return detail.map(d => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("\n");
    }
    return `Request failed (HTTP ${status})`;
  }

  return {
    listProjects: () => request("GET", "/api/projects"),
    createProject: (name) => request("POST", "/api/projects", { name }),
    getProject: (id) => request("GET", `/api/projects/${id}`),
    saveProject: (id, data) => request("PUT", `/api/projects/${id}`, data),
    deleteProject: async (id) => {
      const result = await request("DELETE", `/api/projects/${id}`);
      // Stop the store holding a deleted project. Otherwise the unload flush faithfully saves
      // it back and the project reappears the moment you close the tab.
      if (window.Store && Store.get() && Store.get().id === id) Store.forget();
      return result;
    },
    getProblems: (id) => request("GET", `/api/projects/${id}/problems`),
    generate: (id) => request("POST", `/api/projects/${id}/generate`),
    validate: (id) => request("POST", `/api/projects/${id}/validate`),
    getConstants: () => request("GET", "/api/constants"),
    getEnvironment: () => request("GET", "/api/environment"),
    saveEnvironment: (config) => request("PUT", "/api/environment", config),
  };
})();
