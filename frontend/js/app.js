// js/app.js
document.addEventListener('DOMContentLoaded', () => {
    // Global cache for all loaded games (Library + Search)
    const gameCache = new Map(); 
    const mainContent = document.getElementById('main-content');
    
    // --- Navigation & Routing ---
    const navLinks = document.querySelectorAll('.nav-link');
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            const view = e.currentTarget.getAttribute('data-view');
            if (view) {
                e.preventDefault();
                document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
                e.currentTarget.classList.add('active');
                
                switch(view) {
                    case 'library': renderLibrary(); break;
                    case 'add-new': renderAddNew(); break;
                    case 'queue': renderQueue(); break;
                    default: renderPlaceholder(view, "fa-circle-info");
                }
            }
        });
    });

    // --- View Renderers ---
    async function renderLibrary() {
        mainContent.innerHTML = `<p class="status-msg"><i class="fa-solid fa-circle-notch fa-spin"></i> Loading Library...</p>`;
        
        try {
            const games = await API.getLibrary();
            
            if (!games || games.length === 0) {
                mainContent.innerHTML = `<div class="status-msg"><i class="fa-solid fa-circle-exclamation"></i> Library is empty. Add a game to get started.</div>`;
                return;
            }

            // Cache games for modal lookups
            games.forEach(g => gameCache.set(g.title_id, g));

            mainContent.innerHTML = `
                <div class="view-header" style="margin-bottom: 20px;">
                    <h2>Library</h2>
                </div>
                <div class="poster-grid">
                    ${games.map(game => {
                        const poster = game.cover_url || 'https://placehold.co/400x600/1a1a1a/2ecc71?text=NO+POSTER';
                        const safeName = game.name.replace(/'/g, "\\'");
                        
                        return `
                            <div class="card" onclick="showDetails('${game.title_id}', '${safeName}')">
                                <div class="card-ribbon" style="${game.is_missing ? '' : 'display: none;'}"></div>
                                <img src="${poster}" class="card-poster" alt="${game.name}">
                                <div class="card-footer">
                                    <span class="card-status">${game.name}</span>
                                    <span class="card-quality">${game.platform.toUpperCase()} | ${game.region}</span>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            `;
        } catch (e) {
            mainContent.innerHTML = `<div class="status-msg text-danger"><i class="fa-solid fa-triangle-exclamation"></i> Failed to load library. Check server logs.</div>`;
        }
    }

    async function renderQueue() {
        mainContent.innerHTML = `<p class="status-msg"><i class="fa-solid fa-circle-notch fa-spin"></i> Loading Activity...</p>`;
        
        try {
            const data = await API.getQueue();
            const queueItems = data.queue || [];
            
            mainContent.innerHTML = `
                <div class="view-header" style="margin-bottom: 20px;">
                    <h2>Activity <span class="text-muted">| Queue</span></h2>
                </div>
                ${queueItems.length === 0 ? 
                    `<div class="status-msg"><i class="fa-solid fa-check-circle" style="color: var(--status-monitored);"></i> Queue is empty.</div>` : 
                    `<table class="data-table">
                        <thead>
                            <tr>
                                <th>PLATFORM</th>
                                <th>TITLE</th>
                                <th>STATUS</th>
                                <th>PROGRESS</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${queueItems.map(item => `
                                <tr>
                                    <td><span class="badge-quality">${item.platform}</span></td>
                                    <td>${item.name} <br><small class="text-muted">${item.title_id}</small></td>
                                    <td><span class="badge-format">${item.status.toUpperCase()}</span></td>
                                    <td>
                                        <div class="progress-bar-container">
                                            <div class="progress-bar-fill" style="width: ${item.status === 'completed' ? '100%' : '0%'}"></div>
                                        </div>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>`
                }
            `;
        } catch (e) {
            mainContent.innerHTML = `<div class="status-msg text-danger"><i class="fa-solid fa-triangle-exclamation"></i> Failed to load queue. Check server logs.</div>`;
        }
    }

    function renderAddNew() {
        mainContent.innerHTML = `
            <div class="add-new-header" style="margin-bottom: 20px;">
                <h2>Add New Game</h2>
            </div>
            <div class="search-container" style="margin-bottom: 20px;">
                <i class="fa-solid fa-magnifying-glass search-icon"></i>
                <input type="text" id="game-search-input" class="search-input" placeholder="Search for a game...">
            </div>
            <div id="search-results" class="search-results-container"></div>
        `;

        const searchInput = document.getElementById('game-search-input');
        const container = document.getElementById('search-results');

        searchInput.addEventListener('keypress', async (e) => {
            if (e.key === 'Enter') {
                container.innerHTML = `<p class="status-msg"><i class="fa-solid fa-circle-notch fa-spin"></i> Searching...</p>`;
                try {
                    const results = await API.searchGames(searchInput.value);
                    renderSearchResults(results);
                } catch (err) {
                    container.innerHTML = `<p class="status-msg text-danger"><i class="fa-solid fa-triangle-exclamation"></i> Search failed. Check server logs.</p>`;
                }
            }
        });
    }

    function renderSearchResults(results) {
        const container = document.getElementById('search-results');
        
        if (!results || results.length === 0) {
            container.innerHTML = `<p class="status-msg"><i class="fa-solid fa-circle-info"></i> Search returned no results.</p>`;
            return;
        }

        // Cache search results so the modal/queue logic can find them
        results.forEach(g => gameCache.set(g.title_id, g));

        container.innerHTML = `
            <table class="data-table">
                <thead>
                    <tr><th>PLATFORM</th><th>TITLE</th><th>ACTION</th></tr>
                </thead>
                <tbody>
                    ${results.map(game => `
                        <tr>
                            <td><span class="badge-quality">${game.platform}</span></td>
                            <td>${game.name} <br><small class="text-muted">${game.region} | ${game.title_id}</small></td>
                            <td class="table-actions">
                                <button class="toolbar-btn" style="color: var(--primary-accent)" onclick="requestExtraction('${game.title_id}')">
                                    <i class="fa-solid fa-download"></i>
                                    <span>ADD</span>
                                </button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    }

    function renderPlaceholder(view, iconClass) {
        mainContent.innerHTML = `
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); opacity: 0.5;">
                <i class="fa-solid ${iconClass}" style="font-size: 4rem; margin-bottom: 20px;"></i>
                <h2>${view.charAt(0).toUpperCase() + view.slice(1)} View</h2>
                <p>Functionality coming in a future update.</p>
            </div>
        `;
    }

    // --- System Triggers ---
    window.requestExtraction = async (title_id) => {
        const game = gameCache.get(title_id);
        if (!game) {
            alert("Error: Game data is missing from the local cache.");
            return;
        }

        try { 
            const result = await API.addToQueue(game);
            if (result.message) {
                // Change alert to a less intrusive *Arr style notification if possible, but alert works for now
                alert(`Added ${game.name} to the download queue.`);
                window.closeModal();
            }
        } catch (e) {
            alert("Error: Failed to communicate with the server.");
        }
    };

    // --- Detail Modal Logic ---
    window.showDetails = async (titleId, name) => {
        const modal = document.getElementById('detail-modal');
        const content = modal.querySelector('.modal-content');
    
        modal.classList.add('active');
        content.innerHTML = `
            <div class="status-msg" style="text-align: center; padding: 40px;">
                <i class="fa-solid fa-circle-notch fa-spin" style="font-size: 2rem; margin-bottom: 15px; color: var(--primary-accent);"></i> 
                <p>Loading game details...</p>
            </div>
        `;

        try {
            const data = await API.getDetails(titleId, name);
            const meta = data.metadata;
            const safeName = name.replace(/'/g, "\\'");

            content.innerHTML = `
                <span class="close-btn" onclick="window.closeModal()">&times;</span>
                <div class="briefing-layout" style="display: flex; gap: 20px;">
                    <img src="${meta.cover}" class="briefing-poster" onerror="this.src='https://placehold.co/400x600/1a1a1a/2ecc71?text=NO+POSTER'" style="width: 220px; border-radius: 4px; box-shadow: 0 4px 10px rgba(0,0,0,0.5);">
                    <div class="briefing-text" style="flex-grow: 1;">
                        <h2 style="margin-bottom: 5px;">${name}</h2>
                        <div class="meta-row" style="margin-bottom: 15px;">
                            <span class="badge-quality">${data.platform.toUpperCase()}</span>
                            <span class="text-muted" style="margin-left: 10px;">${titleId} | ${data.region}</span>
                        </div>
                        <hr class="toolbar-separator" style="width: 100%; margin: 15px 0; height: 1px;">
                        <p class="summary" style="line-height: 1.5; color: var(--text-main); margin-bottom: 20px;">${meta.summary || 'No description available.'}</p>
                    
                        <div class="actions">
                            ${data.status === 'available' ? 
                                `<button class="btn-primary" onclick="window.requestExtraction('${titleId}')" style="background: var(--primary-accent); color: #fff; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; font-weight: bold;">
                                    <i class="fa-solid fa-download"></i> Add to Queue
                                </button>` : 
                                `<button class="btn-disabled" disabled style="background: var(--border); color: var(--text-muted); border: none; padding: 10px 15px; border-radius: 4px; cursor: not-allowed; font-weight: bold;">
                                    <i class="fa-solid fa-check"></i> Already in Library
                                </button>`
                            }
                        </div>
                    </div>
                </div>
            `;
        } catch (err) {
            content.innerHTML = `
                <div class="status-msg text-danger" style="text-align: center; padding: 30px;">
                    <i class="fa-solid fa-triangle-exclamation" style="font-size: 2rem; margin-bottom: 15px;"></i>
                    <p>Failed to retrieve game details.</p>
                    <button onclick="window.closeModal()" style="margin-top: 15px; background: transparent; border: 1px solid var(--border); color: var(--text-main); padding: 8px 15px; cursor: pointer; border-radius: 4px;">Close</button>
                </div>
            `;
        }
    };

    window.closeModal = () => {
        document.getElementById('detail-modal').classList.remove('active');
    };

    renderLibrary(); // Initial Load
});
