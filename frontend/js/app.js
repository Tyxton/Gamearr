// js/app.js
document.addEventListener("DOMContentLoaded", () => {
  // Global cache for all loaded games (Library + Search)
  const gameCache = new Map();
  const mainContent = document.getElementById("main-content");

  // --- Global Updaters ---
  async function updateQueueBadge() {
    try {
      const data = await API.getQueueCount();
      const badge = document.getElementById("queue-badge");

      if (badge) {
        if (data.count > 0) {
          badge.textContent = data.count;
          badge.style.display = "inline-block";
        } else {
          badge.style.display = "none";
        }
      }
    } catch (e) {
      console.error("Failed to update queue badge.", e);
    }
  }

  // define status map
  const STATUS_MAP = {
    PENDING: "pending",
    DOWNLOADING: "downloading",
    EXTRACTING: "extracting",
    IMPORTING: "importing",
    COMPLETED: "completed",
    FAILED: "failed",
    AVAILABLE: "available",
  };

  updateQueueBadge();
  setInterval(updateQueueBadge, 10000);

  // --- Global Polling State ---
  let heartbeatInterval = null;

  function startHeartbeat() {
    // run every 5 seconds
    heartbeatInterval = setInterval(async () => {
      updateQueueBadge();
      updateSystemStats();

      // if the user is currently looking at the activity/queue page, refresh the table
      const mainContent = document.getElementById("main-content");
      const activeLink = document.querySelector(".nav-link.active");

      if (activeLink && activeLink.getAttribute("data-view") == "queue") {
        refreshQueueTable();
      }
    }, 5000);
  }

  async function updateSystemStats() {
    try {
      const health = await API.getSystemHealth();
      const diskText = document.getElementById("disk-usage-text");
      const diskBar = document.getElementById("disk-progress");

      // Check if health and health.disk exist before trying to read properties
      if (health && health.disk && diskText) {
        const used = health.disk.used_gb;
        const total = health.disk.total_gb;
        const percent = health.disk.percent;

        diskText.textContent = `${used}GB / ${total}GB (${percent}%)`;

        if (diskBar) {
          diskBar.style.width = `${percent}%`;
        }
      }
    } catch (e) {
      console.error("Stats heartbeat failed:", e);
    }
  }

  // --- Header Search Bar Logic ---
  const topSearchInput = document.querySelector(".top-header .search-input");
  topSearchInput.addEventListener("keypress", async (e) => {
    if (e.key === "Enter") {
      const query = topSearchInput.value.trim();
      if (query.length < 2) return;

      // clear active states on sidebar
      document
        .querySelectorAll(".nav-link")
        .forEach((l) => l.classList.remove("active"));

      // show loading state

      mainContent.innerHTML = `
                <div class="status-msg">
                    <i class="fa-solid fa-wand-magic-sparkles fa-bounce" style="font-size: 2rem; color: var(--primary-accent); margin-bottom: 15px;"></i>
                    <p>Searching NoPayStation & Fetching Art from IGDB...</p>
                </div>
            `;

      try {
        // fetch and render
        const results = await API.searchGames(query);
        renderSearchResults(results, query);

        // clear input
        topSearchInput.value = "";
        topSearchInput.blur();
      } catch (err) {
        mainContent.innerHTML = `<p class="status-msg text-danger">Search failed.</p>`;
      }
    }
  });

  // --- Toast Notification Logic ---
  function showToast(message, type = "success") {
    const container =
      document.getElementById("toast-container") || document.body;
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.style.cssText = `
        position: fixed; bottom: 20px; right: 20px; 
        background: var(--bg-card); border-left: 4px solid ${type === "success" ? "var(--primary-accent)" : "#e74c3c"};
        padding: 15px 25px; border-radius: 4px; z-index: 10000;
        box-shadow: 0 4px 15px rgba(0,0,0,0.5); animation: slideIn 0.3s ease;
    `;
    toast.innerHTML = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 500);
    }, 3000);
  }

  // --- Navigation & Routing ---
  const navLinks = document.querySelectorAll(".nav-link");
  const chevrons = document.querySelectorAll(".nav-chevron");

  navLinks.forEach((link) => {
    link.addEventListener("click", (e) => {
      const view = e.currentTarget.getAttribute("data-view");
      if (!view) return;
      e.preventDefault();

      // dropdown toggling
      const group = e.currentTarget.closest(".nav-group");
      if (group) {
        const chevron = group.querySelector(".nav-chevron");
        const dropdown = group.querySelector(".nav-dropdown");

        // if clicking the parent activity or library
        if (view.includes("-parent")) {
          const isOpen = dropdown.classList.contains("open");
          // close all other groups first
          document
            .querySelectorAll(".nav-dropdown")
            .forEach((d) => d.classList.remove("open"));
          document
            .querySelectorAll(".nav-chevron")
            .forEach((c) => c.classList.remove("open"));

          if (!isOpen) {
            dropdown.classList.add("open");
            chevron.classList.add("open");
          }

          if (view === "library-parent") renderLibrary();
          if (view === "activity-parent") renderActivity("active");
          return; // Don't change the main view yet if just toggling
        }
      }

      // update active states
      document
        .querySelectorAll(".nav-link")
        .forEach((l) => l.classList.remove("active"));
      e.currentTarget.classList.add("active");

      // route to the correct renderer
      switch (view) {
        case "library":
          renderLibrary();
          break;
        case "add-new":
          renderAddNew();
          break;
        case "queue":
          renderActivity("active");
          break;
        case "history":
          renderActivity("history");
          break;
        case "blocklist":
          renderActivity("blocklist");
          break;
        case "wanted":
          renderWanted();
          break;
        case "calendar":
          renderCalendar();
          break;
        case "settings":
          renderSettings();
          break;
        case "system":
          renderSystem();
          break;
      }
    });
  });

  // --- UI Helpers ---
  // Generates a standardized status badge HTML element
  function getStatusBadge(status) {
    const safeStatus = status ? status.toLowerCase() : STATUS_MAP.AVAILABLE;
    return `<span class="status-badge status-${safeStatus}">${safeStatus.toUpperCase()}</span>`;
  }

  // Generates the ribbon element for the top corner of cards.
  // Only shows for (Pending, Downloading, Failed)
  function getCardRibbon(status) {
    const activeStates = [
      "pending",
      "downloading",
      "extracting",
      "importing",
      "failed",
    ];
    if (activeStates.includes(status.toLowerCase())) {
      return `<div class="card-ribbon status-$(status.toLowerCase()}"></div>`;
    }
    return "";
  }

  // --- View Renderers ---
  async function renderLibrary() {
    // 1. Use a container with the 'poster-grid' class
    mainContent.innerHTML = `
        <div class="view-header"><h2>Library</h2></div>
        <div class="poster-grid" id="library-grid">
            <p class="status-msg"><i class="fa-solid fa-circle-notch fa-spin"></i> Loading...</p>
        </div>
    `;

    try {
      const games = await API.getLibrary();
      const grid = document.getElementById("library-grid");

      if (!games || games.length === 0) {
        grid.innerHTML = `<p class="status-msg">Library is empty. Add a game to get started.</p>`;
        return;
      }

      // 2. Map the cards into the grid
      grid.innerHTML = games
        .map((game) => {
          gameCache.set(game.title_id, game);

          const imgUrl = game.cover_url.includes("http")
            ? `${game.cover_url}?t=${new Date().getTime()}`
            : game.cover_url;

          return `
                <div class="card" onclick="showDetails('${game.title_id}', '${game.name.replace(/'/g, "\\'")}')">
                    <img src="${imgUrl}" class="card-poster" onerror="this.src='/assets/placeholder.png'">
                    <div class="card-footer">
                        <span class="card-status">${game.name}</span>
                        <div class="card-meta">
                            ${getStatusBadge(game.status)}
                            <span class="card-quality">${game.platform.toUpperCase()}</span>
                        </div>
                    </div>
                </div>
            `;
        })
        .join("");
    } catch (e) {
      mainContent.innerHTML = `<p class="status-msg text-danger">Failed to load library.</p>`;
    }
  }

  async function renderActivity(view = "active") {
    mainContent.innerHTML = `<p class="status-msg"><i class="fa-solid fa-circle-notch fa-spin"></i> Loading ${view}...</p>`;

    try {
      const queueItems = await API.getQueueItems(view);

      // Map internal view names to Display names
      const displayNames = {
        active: "Queue",
        history: "History",
        blocklist: "Blocklist",
      };

      mainContent.innerHTML = `
            <div class="view-header">
                <h2>Activity <span class="text-muted">| ${displayNames[view]}</span></h2>
            </div>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>PLATFORM</th>
                        <th>TITLE</th>
                        <th>STATUS</th>
                        <th style="width: 250px;">${view === "active" ? "PROGRESS" : "DATE"}</th>
                        <th style="width: 50px;"></th>
                    </tr>
                </thead>
                <tbody>
                    ${queueItems.length === 0 ? `<tr><td colspan="5" class="text-center text-muted">No items found in ${view}</td></tr>` : ""}
                    ${queueItems
                      .map(
                        (item) => `
                        <tr>
                            <td><span class="badge-quality">${item.platform.toUpperCase()}</span></td>
                            <td>${item.name}<br><small class="text-muted">${item.title_id}</small></td>
                            <td>${getStatusBadge(item.status)}</td>
                            <td>
                                ${
                                  view === "active"
                                    ? `
                                    <div class="progress-bar-container" style="width: 100%; height: 18px; background: var(--border); border-radius: 4px; overflow: hidden; position: relative;">
                                        <div class="progress-bar-fill" style="width: ${item.progress}%; height: 100%; background: var(--primary-accent); transition: width 0.5s ease;"></div>
                                        <span style="position: absolute; width: 100%; text-align: center; font-size: 0.65rem; line-height: 18px; color: white; font-weight: bold; mix-blend-mode: difference;">${Math.round(item.progress)}%</span>
                                    </div>
                                `
                                    : `<small class="text-muted">${new Date(item.added_at).toLocaleString()}</small>`
                                }
                            </td>
                            <td>
                                <i class="fa-solid fa-trash text-danger" style="cursor:pointer; opacity: 0.5;" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.5" onclick="handleQueueDelete('${item.title_id}', '${view}')"></i>
                            </td>
                        </tr>
                    `,
                      )
                      .join("")}
                </tbody>
            </table>
        `;
    } catch (e) {
      mainContent.innerHTML = `<div class="status-msg text-danger">Failed to load activity.</div>`;
    }
  }

  // Helper to render the card HTML
  function renderGameCard(game) {
    gameCache.set(game.title_id, game);
    return `
        <div class="card ${isSelectMode ? "selecting" : ""}" 
             data-id="${game.title_id}" 
             onclick="${isSelectMode ? `toggleCardSelection('${game.title_id}', event)` : `showDetails('${game.title_id}', '${game.name.replace(/'/g, "\\'")}')`}">
            
            <div class="card-checkbox-container">
                <input type="checkbox" class="card-checkbox" 
                       ${selectedIds.has(game.title_id) ? "checked" : ""} 
                       onclick="event.stopPropagation()">
            </div>

            <img src="${game.cover_url || "/assets/placeholder.png"}" class="card-poster" onerror="this.src='/assets/placeholder.png'">
            <div class="card-footer">
                <span class="card-status">${game.name}</span>
                <div class="card-meta">
                    <span class="badge-quality" style="background: #444; border:none;">${game.region || "??"}</span>
                    <span class="card-quality">${game.platform.toUpperCase()}</span>
                </div>
                <div style="margin-top: 8px;">
                    ${getStatusBadge(game.status || "available")}
                </div>
            </div>
        </div>
    `;
  }

  // Unified Search Results Renderer
  function renderSearchResults(results, query) {
    mainContent.innerHTML = `
        <div class="view-header">
            <h2>Add New <span class="text-muted">| "${query}"</span></h2>
        </div>
        <div class="search-container" style="width: 100%; max-width: 600px; margin-bottom: 30px;">
            <i class="fa-solid fa-magnifying-glass search-icon"></i>
            <input type="text" id="inner-search-input" class="search-input" placeholder="Search again..." value="${query}">
        </div>
        <div class="poster-grid">
            ${results.length > 0 ? results.map((game) => renderGameCard(game)).join("") : `<p class="status-msg">No results found for "${query}"</p>`}
        </div>
    `;

    // Re-bind the search listener to the inner input
    document
      .getElementById("inner-search-input")
      .addEventListener("keypress", async (e) => {
        if (e.key === "Enter") {
          const q = e.target.value.trim();
          if (q.length < 2) return;
          const res = await API.searchGames(q);
          renderSearchResults(res, q);
        }
      });
  }

  // Add New Page (Initial State)
  function renderAddNew() {
    mainContent.innerHTML = `
        <div class="view-header"><h2>Add New Game</h2></div>
        <div class="search-container" style="width: 100%; max-width: 600px; margin-bottom: 30px;">
            <i class="fa-solid fa-magnifying-glass search-icon"></i>
            <input type="text" id="inner-search-input" class="search-input" placeholder="Search by name or Title ID (e.g. SCUS-94444)">
        </div>
        <div class="poster-grid">
            <p class="status-msg">Enter a game title above to search NoPayStation and IGDB.</p>
        </div>
    `;

    document
      .getElementById("inner-search-input")
      .addEventListener("keypress", async (e) => {
        if (e.key === "Enter") {
          const q = e.target.value.trim();
          if (q.length < 2) return;
          const res = await API.searchGames(q);
          renderSearchResults(res, q);
        }
      });
  }

  function renderSettings() {
    mainContent.innerHTML = `
        <div class="view-header"><h2>Settings</h2></div>
        <div class="card" style="padding: 30px; max-width: 600px; opacity: 0.7;">
            <i class="fa-solid fa-gears" style="font-size: 3rem; margin-bottom: 20px; color: var(--primary-accent);"></i>
            <h3>Settings Engine</h3>
            <p class="text-muted">Global settings, NAS pathing (FTP/SMB), and API Key management are scheduled for the <strong>v0.5 NAS Integration</strong> update.</p>
        </div>
    `;
  }

  async function renderSystem() {
    mainContent.innerHTML = `<p class="status-msg"><i class="fa-solid fa-circle-notch fa-spin"></i> Loading System Status...</p>`;

    try {
      const health = await API.getSystemHealth();
      // Fetch logs as well
      const logData = await API._handleResponse(
        await API._fetch("/api/system/logs?lines=50"),
      );

      mainContent.innerHTML = `
            <div class="view-header"><h2>System <span class="text-muted">| Status</span></h2></div>
            <div class="system-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                
                <div class="card" style="padding: 20px;">
                    <h3><i class="fa-solid fa-hard-drive"></i> Disk Space</h3>
                    <div style="margin-top: 15px;">
                        <p>${health.disk.used_gb} GB / ${health.disk.total_gb} GB Used</p>
                        <div class="progress-bar-container" style="width: 100%; height: 12px; margin-top: 10px;">
                            <div class="progress-bar-fill" style="width: ${health.disk.percent}%;"></div>
                        </div>
                    </div>
                </div>

                <div class="card" style="padding: 20px;">
                    <h3><i class="fa-solid fa-list-check"></i> Tasks</h3>
                    <p class="text-muted" style="font-size: 0.8rem; margin-top:10px;">Background tasks are running via FastAPI Lifespan.</p>
                </div>

                <!-- Log Viewer: Full Width -->
                <div class="card" style="grid-column: span 2; padding: 20px; background: #151515;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                        <h3><i class="fa-solid fa-terminal"></i> Recent Logs</h3>
                        <button class="toolbar-btn" onclick="renderSystem()"><i class="fa-solid fa-rotate"></i> Refresh</button>
                    </div>
                    <pre id="log-output" style="background: #000; color: #0f0; padding: 15px; border-radius: 4px; height: 300px; overflow-y: auto; font-family: 'Courier New', monospace; font-size: 0.85rem; line-height: 1.4;">${logData.logs}</pre>
                </div>
            </div>
        `;

      // Auto-scroll logs to bottom
      const logOutput = document.getElementById("log-output");
      if (logOutput) logOutput.scrollTop = logOutput.scrollHeight;
    } catch (e) {
      mainContent.innerHTML = `<p class="status-msg text-danger">Failed to load system health.</p>`;
    }
  }

  // Add a placeholder for Calendar so it doesn't crash either
  function renderCalendar() {
    mainContent.innerHTML = `
        <div class="view-header"><h2>Calendar</h2></div>
        <p class="status-msg">Calendar view will display upcoming releases in v0.6.</p>
    `;
  }

  async function renderWanted() {
    mainContent.innerHTML = `<p class="status-msg"><i class="fa-solid fa-circle-notch fa-spin"></i> Loading Wanted list...</p>`;

    try {
      const res = await API._fetch("/api/wanted");
      const data = await API._handleResponse(res);
      const games = data.results;

      mainContent.innerHTML = `
            <div class="view-header">
                <h2>Wanted <span class="text-muted">| Missing</span></h2>
            </div>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>PLATFORM</th>
                        <th>TITLE</th>
                        <th>REGION</th>
                        <th>ID</th>
                        <th>ACTIONS</th>
                    </tr>
                </thead>
                <tbody>
                    ${games.length === 0 ? `<tr><td colspan="5" class="text-center text-muted">No missing monitored games found.</td></tr>` : ""}
                    ${games
                      .map(
                        (game) => `
                        <tr>
                            <td><span class="badge-quality">${game.platform.toUpperCase()}</span></td>
                            <td><a href="#" onclick="showDetails('${game.title_id}', '${game.name.replace(/'/g, "\\'")}')" style="color: var(--primary-accent); text-decoration: none;">${game.name}</a></td>
                            <td>${game.region}</td>
                            <td><small class="text-muted">${game.title_id}</small></td>
                            <td>
                                <i class="fa-solid fa-download" style="cursor:pointer; margin-right: 15px;" title="Download Now" onclick="requestDownload('${game.title_id}')"></i>
                                <i class="fa-solid fa-bookmark" style="cursor:pointer; color: var(--primary-accent);" title="Unmonitor" onclick="toggleMonitor('${game.title_id}', 0)"></i>
                            </td>
                        </tr>
                    `,
                      )
                      .join("")}
                </tbody>
            </table>
        `;
    } catch (e) {
      mainContent.innerHTML = `<div class="status-msg text-danger">Failed to load Wanted list.</div>`;
    }
  }

  // --- System Triggers ---

  let isSelectMode = false;
  let selectedIds = new Set();

  window.toggleSelectMode = (forceState) => {
    isSelectMode = forceState !== undefined ? forceState : !isSelectMode;
    const grid = document.querySelector(".poster-grid");
    const bulkBar = document.getElementById("bulk-bar");

    if (isSelectMode) {
      grid.classList.add("select-mode-active");
      bulkBar.classList.add("active");
      // Add .selecting class to all cards
      document
        .querySelectorAll(".card")
        .forEach((c) => c.classList.add("selecting"));
    } else {
      grid.classList.remove("select-mode-active");
      bulkBar.classList.remove("active");
      selectedIds.clear();
      document.querySelectorAll(".card").forEach((c) => {
        c.classList.remove("selecting", "is-selected");
        const cb = c.querySelector(".card-checkbox");
        if (cb) cb.checked = false;
      });
      updateBulkCount();
    }
  };

  window.toggleCardSelection = (titleId, event) => {
    // Prevent the normal "showDetails" click if we are in select mode
    if (event) event.stopPropagation();

    const card = document.querySelector(`.card[data-id="${titleId}"]`);
    const checkbox = card.querySelector(".card-checkbox");

    if (selectedIds.has(titleId)) {
      selectedIds.delete(titleId);
      card.classList.remove("is-selected");
      checkbox.checked = false;
    } else {
      selectedIds.add(titleId);
      card.classList.add("is-selected");
      checkbox.checked = true;
    }
    updateBulkCount();
  };

  function updateBulkCount() {
    document.getElementById("selected-count").textContent = selectedIds.size;
  }

  window.requestDownload = async (title_id) => {
    const game = gameCache.get(title_id);
    try {
      const result = await API.addToQueue(game);
      if (result.message === "Success") {
        alert(`Queued: ${game.name}`);
        window.closeModal();
        updateQueueBadge();
      }
    } catch (e) {
      alert(`Error: ${e.message}`);
    }
  };

  window.toggleMonitor = async (titleId, status) => {
    await API._fetch("/api/games/monitor", {
      method: "POST",
      body: JSON.stringify({ title_id: titleId, monitored: status }),
    });

    const activeView = document
      .querySelector(".nav-link.active")
      .getAttribute("data-view");
    if (activeView === "wanted") renderWanted();
    else if (activeView === "library") renderLibrary();
  };

  // Toolbar Logic
  window.triggerUpdateAll = async () => {
    try {
      await fetch("/api/system/update-all", { method: "POST" });
      showToast("Library and NPS sync started...");
    } catch (e) {
      showToast("Failed to trigger update.", "error");
    }
  };

  let currentSort = "asc";
  window.toggleSort = () => {
    currentSort = currentSort === "asc" ? "desc" : "asc";
    renderLibrary(); // rerenders with current sort logic
  };

  window.bulkAction = async (action) => {
    if (selectedIds.size === 0) return;

    try {
      const ids = Array.from(selectedIds);
      const result = await API.bulkAction(ids, action);
      showToast(result.message);

      // Refresh UI and exit selection mode
      toggleSelectMode(false);

      const activeView = document
        .querySelector(".nav-link.active")
        .getAttribute("data-view");
      if (activeView === "library" || activeView === "library-parent")
        renderLibrary();
      if (activeView === "wanted") renderWanted();
    } catch (e) {
      showToast("Bulk action failed: " + e.message, "error");
    }
  };

  // --- Detail Modal Logic ---
  window.showDetails = async (titleId, name) => {
    const modal = document.getElementById("detail-modal");
    const content = modal.querySelector(".modal-content");

    modal.classList.add("active");
    content.innerHTML = `
        <span class="close-btn" onclick="window.closeModal()">&times;</span>
        <div class="status-msg"><i class="fa-solid fa-circle-notch fa-spin"></i> Loading details...</div>
    `;

    try {
      const data = await API.getDetails(titleId, name);
      const meta = data.metadata;

      content.innerHTML = `
            <span class="close-btn" onclick="window.closeModal()">&times;</span>
            <div class="briefing-layout" style="display: flex; gap: 30px;">
                <img src="${meta.cover_url || "/assets/placeholder.png"}" class="briefing-poster" onerror="this.src='/assets/placeholder.png'">
                <div class="briefing-text" style="flex: 1; display: flex; flex-direction: column;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <h2 style="margin: 0; color: #fff;">${name}</h2>
                        <i class="fa-${data.monitored ? "solid" : "regular"} fa-bookmark" 
                           style="font-size: 1.5rem; cursor: pointer; color: var(--primary-accent);" 
                           title="${data.monitored ? "Unmonitor" : "Monitor"}"
                           onclick="toggleMonitor('${titleId}', ${data.monitored ? 0 : 1}); window.closeModal();"></i>
                    </div>
                    
                    <div style="margin: 10px 0 20px 0; display: flex; gap: 10px;">
                        <span class="badge-quality">${titleId}</span>
                        ${getStatusBadge(data.status)}
                    </div>

                    <div class="summary-container" style="flex-grow: 1; max-height: 300px; overflow-y: auto; padding-right: 10px; margin-bottom: 20px;">
                        <p style="line-height: 1.6; color: var(--text-main); font-size: 0.95rem;">
                            ${meta.summary || "No description available for this title."}
                        </p>
                    </div>

                    <div class="actions" style="margin-top: auto;">
                        ${
                          data.status === "available" ||
                          data.status === "failed"
                            ? `<button class="btn-primary" onclick="requestDownload('${titleId}')" style="padding: 12px 25px; background: var(--primary-accent); border: none; border-radius: 4px; color: white; font-weight: bold; cursor: pointer; width: 100%;">Add to Queue</button>`
                            : `<button class="btn-disabled" disabled style="padding: 12px 25px; width: 100%; opacity: 0.5; cursor: not-allowed;">Already in Library</button>`
                        }
                    </div>
                </div>
            </div>
        `;
    } catch (err) {
      content.innerHTML = `<span class="close-btn" onclick="window.closeModal()">&times;</span><p class="status-msg text-danger">Failed to load game details.</p>`;
    }
  };

  window.closeModal = () => {
    document.getElementById("detail-modal").classList.remove("active");
  };

  renderLibrary(); // Initial Load
});
