// js/api.js
const API = {
    _handleResponse: async (res) => {
        if (!res.ok) throw new Error(`Motherbase Comm Error: ${res.status}`);
        return await res.json();
    },

    getLibrary: async () => {
        const res = await fetch('/api/library');
        const data = await API._handleResponse(res);
        return data.results; // Extracting .results here simplifies the UI code
    },

    searchGames: async (query) => {
        const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        const data = await API._handleResponse(res);
        return data.results;
    },

    getDetails: async (titleId, name) => {
        const res = await fetch(`/api/details/${titleId}?name=${encodeURIComponent(name)}`);
        return await API._handleResponse(res);
    },

    getQueue: async () => {
        const res = await fetch('/api/queue');
        return await API._handleResponse(res);
    },

    addToQueue: async (game) => {
        const res = await fetch('/api/queue', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(game)
        });
        return await API._handleResponse(res);
    },

    triggerUpdateAll: async () => {
        const res = await fetch('/api/command/update-all', { method: 'POST' });
        return await API._handleResponse(res);
    }
};
