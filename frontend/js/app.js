// js/app.js
document.addEventListener('DOMContentLoaded', () => {
    const mainContent = document.getElementById('main-content');
    const navLinks = document.querySelectorAll('.nav-link');
    const chevron = document.getElementById('library-chevron');
    const dropdown = document.getElementById('library-dropdown');

    // Dropdown Logic
    chevron.addEventListener('click', (e) => {
        chevron.classList.toggle('open');
        dropdown.classList.toggle('open');
    });

    // View Router Engine
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            const view = e.currentTarget.getAttribute('data-view');
            if (view) {
                e.preventDefault();
                
                // Manage Active State
                document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
                e.currentTarget.classList.add('active');
                
                // Route to the correct render function
                switch(view) {
                    case 'library': renderLibrary(); break;
                    case 'add-new': renderAddNew(); break;
                    case 'calendar': renderPlaceholder("Calendar", "fa-calendar-days"); break;
                    case 'queue': renderQueue(); break;
                    case 'wanted': renderPlaceholder("Wanted", "fa-triangle-exclamation"); break;
                    case 'settings': renderPlaceholder("Settings", "fa-gear"); break;
                    case 'system': renderPlaceholder("System", "fa-laptop"); break;
                }
            }
        });
    });

    // Toolbar Wiring
    const toolbarBtns = document.querySelectorAll('.toolbar-btn');
    toolbarBtns[0].addEventListener('click', () => {
        API.triggerUpdateAll();
        alert("Update All command sent to Raiden.");
    });

    // Generic Placeholder Renderer for unbuilt tabs
    function renderPlaceholder(title, iconClass) {
        mainContent.innerHTML = `
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); opacity: 0.5;">
                <i class="fa-solid ${iconClass}" style="font-size: 4rem; margin-bottom: 20px;"></i>
                <h2>${title} View</h2>
                <p>Awaiting deployment in future versions.</p>
            </div>
        `;
    }

    // Add New View
    function renderAddNew() {
        mainContent.innerHTML = `
            <div class="add-new-header">
                <h2>Add New Game</h2>
                <p class="text-muted">Search Motherbase Archives or IGDB</p>
            </div>
            <div class="search-container" style="width: 100%; max-width: 800px; margin: 20px 0;">
                <i class="fa-solid fa-magnifying-glass search-icon"></i>
                <input type="text" id="game-search-input" class="search-input" placeholder="Enter game title...">
            </div>
            <div id="search-results" class="search-results-container">
                </div>
        `;

        const searchInput = document.getElementById('game-search-input');
        searchInput.addEventListener('keypress', async (e) => {
            if (e.key === 'Enter') {
                const query = searchInput.value;
                document.getElementById('search-results').innerHTML = '<p>Scanning frequencies...</p>';
            
                // Real Test: Call backend search
                const results = await API.searchGames(query); 
                renderSearchResults(results);
            }
        });
    }

    const API_BASE = "/api";

    const API = {
        async getLibrary() {
            const res = await fetch(`${API_BASE}/library`);
            const data = await res.json();
            return data.results; 
        },
        async searchGames(query) {
            const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`);
            const data = await res.json();
            return data.results;
        },
        async getDetails(titleId, name) {
            const res = await fetch(`${API_BASE}/details/${titleId}?name=${encodeURIComponent(name)}`);
            return await res.json();
        },
        async addToQueue(game) {
            const res = await fetch(`${API_BASE}/queue`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(game)
            });
            return await res.json();
        }
    };

// --- View Rendering ---

    async function renderLibrary() {
        const games = await API.getLibrary();
        const grid = document.getElementById('game-grid');
    
        if (!games || games.length === 0) {
            grid.innerHTML = `<div class="status-msg">[!] NO GAMES FOUND, SYNCING DATABASE.</div>`;
            return;
        }

        grid.innerHTML = games.map(game => {
            const poster = game.cover_url || 'https://placehold.co/400x600/1a1a1a/2ecc71?text=NO+INTEL';
        
            return `
                <div class="game-card" onclick="showDetails('${game.title_id}', '${game.name.replace(/'/g, "\\'")}')">
                    <div class="poster-container">
                        <img src="${poster}" alt="${game.name}" onerror="this.src='https://placehold.co/400x600/1a1a1a/2ecc71?text=UNSUPPORTED+ENCODING'">
                        <div class="platform-badge">${game.platform.toUpperCase()}</div>
                    </div>
                    <div class="game-info">
                        <div class="game-title">${game.name}</div>
                        <div class="game-meta">${game.region} | ${game.title_id}</div>
                    </div>
                </div>
            `;
        }).join('');
    }

    async function showDetails(titleId, name) {
        // Trigger the "Scanning" UI state
        const safeName = name.replace(/'/g, "\\'")

        const modal = document.getElementById('detail-modal');
        modal.classList.add('active');
        modal.innerHTML = `<div class="loading-spinner">Establishing database link...</div>`;

        // Fetch the real intel
        const data = await API.getDetails(titleId, name);
        const meta = data.metadata;

        // Render the Briefing
        modal.innerHTML = `
            <div class="modal-content">
                <span class="close-btn" onclick="closeModal()">&times;</span>
                <div class="briefing-layout">
                    <img src="${meta.cover}" class="briefing-poster">
                    <div class="briefing-text">
                        <h2>${name} <span class="text-muted">[${titleId}]</span></h2>
                        <p class="status-tag ${data.status}">${data.status.toUpperCase()}</p>
                        <hr>
                        <p class="summary">${meta.summary}</p>
                        <div class="actions">
                            ${data.status === 'available' ? 
                                `<button class="btn-primary" onclick="requestExtraction('${titleId}', '${safeName}')">Request Game?</button>` : 
                                `<button class="btn-disabled" disabled>Game Installed</button>`
                            }
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    // Initialize default view
    renderLibrary();
});
