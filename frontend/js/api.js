// js/api.js
const API = {
    // Universal error handler
    _handleResponse: async (res) => {
        if (!res.ok) throw new Error(`Motherbase Comm Error: ${res.status}`);
        return await res.json();
    },

    getLibrary: async () => {
        try {
            const res = await fetch('/api/library');
            return await API._handleResponse(res);
        } catch (e) {
            console.warn("Falling back to Mock Data for UI testing...", e);
            // Fallback so UI doesn't break
            return [{ id: 1, title: "MGS V", quality: "PC - 4K", status: "Monitored", missing: true, posterUrl: "https://placehold.co/400x600/1a1a1a/2ecc71?text=MGS+V" }];
        }
    },
    
    getQueue: async () => {
        try {
            const res = await fetch('/api/queue');
            return await API._handleResponse(res);
        } catch (e) {
            return [{ id: 1, title: "Metal Gear Solid V", version: "v1.15", quality: "WEBDL-1080p", format: "Repack", timeLeft: "00:15:30", progress: 75 }];
        }
    },

    // Example Toolbar Action
    triggerUpdateAll: async () => {
        console.log("Triggering Update All for local Libary...");
        const res = await fetch('/api/command/update-all', { method: 'POST' });
        return await API._handleResponse(res);
    }
};
