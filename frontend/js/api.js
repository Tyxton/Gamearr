// js/api.js
const API = {
  apiKey: null,

  // Fetch the key from the bootstrap
  init: async () => {
    const res = await fetch("/api/config/keys");
    const data = await res.json();
    API.apiKey = data.api_key;
    console.log("Gamearr API Initialized");
  },

  _handleResponse: async (res) => {
    if (res.status === 401) {
      console.error("Auth Failure. API Key rejected.");
      // future redirect to login
    }
    if (!res.ok) {
      // FastAPI returns detail on 422 validation errors
      const errorData = await res.json();
      console.error("Server Error Detail:", errorData);
      throw new Error(errorData.detail || `Server Error: ${res.status}`);
    }
    return await res.json();
  },

  // fetch wrapper to include headers
  _fetch: async (url, options = {}) => {
    if (!API.apiKey) await API.init();

    options.headers = {
      ...options.headers,
      "X-Api-Key": API.apiKey,
      "Content-Type": "application/json",
    };
    return await fetch(url, options);
  },

  getLibrary: async () => {
    const res = await API._fetch("/api/library");
    const data = await API._handleResponse(res);
    return data.results; // Returns array of GameModel
  },

  searchGames: async (query) => {
    const res = await API._fetch(`/api/search?q=${encodeURIComponent(query)}`);
    const data = await API._handleResponse(res);
    return data.results;
  },

  getDetails: async (titleId, name) => {
    const res = await API._fetch(
      `/api/details/${titleId}?name=${encodeURIComponent(name)}`,
    );
    return await API._handleResponse(res);
  },

  getQueueCount: async () => {
    const res = await API._fetch("/api/queue/count");
    return await API._handleResponse(res);
  },

  getQueueItems: async (view = "active") => {
    const res = await API._fetch(`/api/queue?view=${view}`);
    const data = await API._handleResponse(res);
    return data.queue; // Returns array of QueueItem
  },

  removeFromQueue: async (titleId) => {
    const res = await API._fetch(`/api/queue/${titleId}`, { method: "DELETE" });
    return await API._handleResponse(res);
  },

  getSystemHealth: async () => {
    const res = await API._fetch(`/api/system/health`);
    return await API._handleResponse(res);
  },

  triggerUpdateAll: async () => {
    const res = await API._fetch(`/api/system/update-all`, { method: "POST" });
    return await API._handleResponse(res);
  },

  addToQueue: async (game) => {
    const res = await API._fetch("/api/queue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        platform: game.platform,
        title_id: game.title_id,
        region: game.region,
        name: game.name,
        pkg_url: game.pkg_url,
        license_key: game.license_key || "MISSING",
      }),
    });
    return await API._handleResponse(res);
  },

  // Helper for bulk actions
  bulkAction: async (ids, action) => {
    const res = await API._fetch("/api/games/bulk", {
      method: "POST",
      body: JSON.stringify({ title_ids: ids, action: action }),
    });
    return await API._handleResponse(res);
  },
};
