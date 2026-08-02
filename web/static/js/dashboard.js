// ========================================
// Dashboard - Domain Sidebar + Crawl Detail
// ========================================

// Dashboard Loading Overlay Utilities
function showDashboardLoading(text, step) {
    const overlay = document.getElementById('loadingOverlay');
    const textEl = document.getElementById('loadingOverlayText');
    const stepEl = document.getElementById('loadingOverlayStep');
    if (!overlay) return;
    overlay.style.display = 'flex';
    if (textEl) textEl.textContent = text || 'Loading...';
    if (stepEl) stepEl.textContent = step || '';
}

function updateDashboardLoading(text, step) {
    const textEl = document.getElementById('loadingOverlayText');
    const stepEl = document.getElementById('loadingOverlayStep');
    if (textEl && text) textEl.textContent = text;
    if (stepEl) stepEl.textContent = step || '';
}

function hideDashboardLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) overlay.style.display = 'none';
}

// Dashboard state
let selectedDomain = null;
let compareMode = false;
let selectedCrawls = new Set();
let allDomains = [];
let activeCrawlRefreshInterval = null;
let dashboardRefreshInterval = null;
let currentUserId = null;
let currentUsername = null;

async function loadDashboard() {
    try {
        // Fetch current user info, active crawls, and history in parallel
        const [userResponse, historyResponse, activeResponse] = await Promise.all([
            fetch('/api/user/info').catch(() => ({ json: () => ({ success: false }) })),
            fetch('/api/crawls/history'),
            fetch('/api/my_active_crawls').catch(() => ({ json: () => ({ success: false, crawls: [] }) }))
        ]);

        const userData = await userResponse.json();
        if (userData.success) {
            currentUserId = userData.user.id;
            currentUsername = userData.user.username;
        }

        const data = await historyResponse.json();
        const activeData = await activeResponse.json();

        if (!data.success) {
            console.error('Failed to load history:', data.error);
            return;
        }

        allDomains = data.domains || [];
        renderDomainSidebar();
        renderActiveCrawls(activeData.crawls || []);

        // Auto-select first domain if none selected, or refresh if one is already selected
        if (allDomains.length > 0) {
            if (!selectedDomain || !allDomains.find(d => d.domain === selectedDomain)) {
                selectDomain(allDomains[0].domain);
            } else {
                renderCrawlDetail();
            }
        } else {
            selectedDomain = null;
            renderCrawlDetailEmpty();
        }
    } catch (error) {
        console.error('Error loading dashboard:', error);
    }
}

// ========================================
// Active Crawls Section
// ========================================

function renderActiveCrawls(crawls) {
    const container = document.getElementById('activeCrawlsSection');
    if (!container) return;

    if (crawls.length === 0) {
        container.style.display = 'none';
        // Stop auto-refresh if no active crawls
        if (activeCrawlRefreshInterval) {
            clearInterval(activeCrawlRefreshInterval);
            activeCrawlRefreshInterval = null;
        }
        return;
    }

    container.style.display = 'block';
    container.innerHTML = `
        <div style="background: linear-gradient(135deg, #1e40af, #3b82f6); border-radius: 10px; padding: 16px 20px; margin-bottom: 20px;">
            <div style="display: flex; align-items: center; gap: 10px; font-size: 14px; font-weight: 600; color: #ffffff; margin-bottom: 12px;">
                <div style="width: 8px; height: 8px; border-radius: 50%; background: #4ade80; animation: pulse 2s infinite;"></div>
                <span>Active Crawl${crawls.length > 1 ? 's' : ''}</span>
                <span style="font-size: 12px; font-weight: 400; opacity: 0.8; margin-left: 4px;">${crawls.length} in progress</span>
            </div>
            <div style="display: flex; flex-direction: column; gap: 8px;">
                ${crawls.map(crawl => {
                    const isOwner = currentUserId !== null && crawl.user_id === currentUserId;
                    return `
                    <div style="display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; ${isOwner ? 'cursor: pointer;' : ''} transition: background 0.2s;"
                         ${isOwner ? `onclick="reconnectFromDashboard(${crawl.id})"` : ''}
                         onmouseover="this.style.background='rgba(255,255,255,0.2)'"
                         onmouseout="this.style.background='rgba(255,255,255,0.12)'">
                        <div style="flex: 1; min-width: 0;">
                            <div style="font-weight: 600; font-size: 14px; color: #ffffff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(crawl.base_url)}</div>
                            <div style="font-size: 12px; color: rgba(255,255,255,0.75); margin-top: 2px; display: flex; gap: 8px;">
                                <span>${crawl.status === 'running' ? 'Crawling...' : 'Paused'}</span>
                                ${crawl.owner_username ? `<span style="opacity:0.7;">by ${escapeHtml(crawl.owner_username)}</span>` : ''}
                            </div>
                        </div>
                        <div style="display: flex; align-items: center; gap: 12px; flex-shrink: 0;">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <div style="width: 100px; height: 6px; background: rgba(255,255,255,0.2); border-radius: 3px; overflow: hidden;">
                                    <div style="height: 100%; background: linear-gradient(90deg, #4ade80, #22d3ee); border-radius: 3px; width: ${crawl.progress_percent || 0}%; transition: width 0.3s ease;"></div>
                                </div>
                                <span style="font-size: 13px; font-weight: 600; color: #ffffff; min-width: 36px;">${crawl.progress_percent || 0}%</span>
                            </div>
                            ${isOwner ? `
                            <button style="padding: 6px 14px; background: rgba(255,255,255,0.2); color: #ffffff; border: 1px solid rgba(255,255,255,0.3); border-radius: 6px; font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit; transition: background 0.2s;"
                                    onclick="event.stopPropagation(); reconnectFromDashboard(${crawl.id})"
                                    onmouseover="this.style.background='rgba(255,255,255,0.3)'"
                                    onmouseout="this.style.background='rgba(255,255,255,0.2)'">
                                Reconnect
                            </button>
                            ` : `<span style="font-size:12px;color:rgba(255,255,255,0.5);padding:6px 14px;">Read-only</span>`}
                        </div>
                    </div>`;
                }).join('')}
            </div>
        </div>
    `;

    // Start auto-refresh if not already running
    // Refreshes the full dashboard so domain list + crawl detail also update
    if (!activeCrawlRefreshInterval) {
        activeCrawlRefreshInterval = setInterval(() => {
            loadDashboard();
        }, 30000);
    }
}

function reconnectFromDashboard(crawlId) {
    sessionStorage.setItem('force_ui_refresh', 'true');
    sessionStorage.setItem('reconnect_crawl_id', crawlId);
    sessionStorage.setItem('current_crawl_id', crawlId);
    // Use reconnect_crawl_id for active crawls so the page auto-reconnects
    window.location.href = `/?reconnect_crawl_id=${crawlId}`;
}

function renderDomainSidebar() {
    const container = document.getElementById('domainList');
    if (!container) return;

    if (allDomains.length === 0) {
        container.innerHTML = '<div style="padding:16px;color:var(--fg-muted);font-size:13px;text-align:center;">No crawls yet</div>';
        return;
    }

    container.innerHTML = allDomains.map(d => `
        <div class="domain-item ${selectedDomain === d.domain ? 'active' : ''}"
             onclick="selectDomain('${d.domain.replace(/'/g, "\\'")}')">
            <div class="domain-name">${escapeHtml(d.domain)}</div>
            <div class="domain-count">${d.crawl_count} crawl${d.crawl_count !== 1 ? 's' : ''}</div>
        </div>
    `).join('');
}

function selectDomain(domain) {
    selectedDomain = domain;
    selectedCrawls.clear();
    compareMode = false;
    renderDomainSidebar();
    renderCrawlDetail();
}

function renderCrawlDetailEmpty() {
    const container = document.getElementById('crawlDetail');
    if (!container) return;
    container.innerHTML = '<div class="empty-state"><p>Select a domain to view crawl history</p></div>';
}

function renderCrawlDetail() {
    const container = document.getElementById('crawlDetail');
    if (!container) return;

    const domainData = allDomains.find(d => d.domain === selectedDomain);
    if (!domainData) {
        renderCrawlDetailEmpty();
        return;
    }

    const crawls = domainData.crawls || [];
    const totalIssues = crawls.reduce((sum, c) => sum + (c.issues_count || 0), 0);

    let html = `
        <div class="domain-header">
            <div>
                <h1>${escapeHtml(domainData.domain)}</h1>
                <p class="domain-stats">${domainData.crawl_count} crawl${domainData.crawl_count !== 1 ? 's' : ''} · ${totalIssues} total issues</p>
            </div>
            <div style="display:flex;gap:8px;">
                <button class="btn ${compareMode ? 'btn-primary' : ''}" onclick="toggleCompareMode()">
                    ${compareMode ? 'Cancel Compare' : 'Compare Runs'}
                </button>
            </div>
        </div>
    `;

    // Compare bar
    if (compareMode && selectedCrawls.size === 2) {
        const ids = Array.from(selectedCrawls);
        html += `
            <div class="compare-bar">
                <span style="font-size:13px;font-weight:500;">2 crawls selected for comparison</span>
                <a href="/compare?id_a=${ids[0]}&id_b=${ids[1]}" class="compare-link">Compare Now</a>
            </div>
        `;
    }

    if (crawls.length === 0) {
        html += '<div class="empty-state"><p>No crawls for this domain</p></div>';
        container.innerHTML = html;
        return;
    }

    // Crawl list
    crawls.forEach(crawl => {
        const date = new Date(crawl.started_at).toLocaleString();
        const issues = crawl.issues_count || 0;
        const isSelected = selectedCrawls.has(crawl.id);
        const urlsCrawled = crawl.urls_crawled || 0;
        const clickable = !compareMode && urlsCrawled > 0;
        const isOwner = currentUserId !== null && crawl.user_id === currentUserId;
        const ownerLabel = crawl.owner_username || (isOwner ? currentUsername : 'unknown');

        html += `
            <div class="crawl-card ${isSelected ? 'selected' : ''}"
                 ${clickable ? `onclick="openCrawl(${crawl.id}, '${crawl.status}', ${urlsCrawled}, ${crawl.user_id})" style="cursor:pointer;"` : ''}>
                ${compareMode ? `<input type="checkbox" class="compare-checkbox" ${isSelected ? 'checked' : ''} onchange="toggleCrawlSelect(${crawl.id})">` : ''}
                <div style="flex:1;min-width:0;">
                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                        <span style="font-size:13px;font-weight:500;color:var(--ink);">${date}</span>
                        <span class="status-badge status-${crawl.status}">${crawl.status}</span>
                        ${crawl.display_name ? `<span style="font-size:12px;color:var(--fg-muted);">— ${escapeHtml(crawl.display_name)}</span>` : ''}
                    </div>
                    <div style="display:flex;gap:16px;font-size:12px;color:var(--fg-muted);">
                        <span style="display:flex;align-items:center;gap:4px;"><span style="opacity:0.6;">by</span> ${escapeHtml(ownerLabel)}</span>
                        <span>${urlsCrawled} URLs</span>
                        <span style="color:${issues > 0 ? 'var(--error)' : 'var(--success)'};">${issues} issues</span>
                        ${crawl.completed_at ? `<span>${formatDuration(crawl.started_at, crawl.completed_at)}</span>` : ''}
                    </div>
                </div>
                <div style="display:flex;gap:6px;flex-shrink:0;">
                    ${isOwner ? `<button class="action-btn" onclick="event.stopPropagation(); renameCrawl(${crawl.id}, '${(crawl.display_name || '').replace(/'/g, "\\'")}')">Rename</button>` : ''}
                    ${isOwner ? `<button class="action-btn danger" onclick="event.stopPropagation(); deleteCrawl(${crawl.id})">Delete</button>` : ''}
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}

// ========================================
// Compare Mode
// ========================================

function toggleCompareMode() {
    compareMode = !compareMode;
    selectedCrawls.clear();
    renderCrawlDetail();
}

function toggleCrawlSelect(id) {
    if (selectedCrawls.has(id)) {
        selectedCrawls.delete(id);
    } else if (selectedCrawls.size < 2) {
        selectedCrawls.add(id);
    }
    renderCrawlDetail();
}

// ========================================
// Helpers
// ========================================

function formatDuration(start, end) {
    const diff = new Date(end) - new Date(start);
    const h = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const s = Math.floor((diff % 60000) / 1000);
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ========================================
// Crawl Actions
// ========================================

async function openCrawl(crawlId, status, urlsCrawled, ownerUserId) {
    if (urlsCrawled === 0) {
        alert('No URLs crawled yet — nothing to load.');
        return;
    }

    const isOwner = currentUserId !== null && ownerUserId === currentUserId;
    const isActive = status === 'running' || status === 'paused';

    // Cannot reconnect to another user's active crawl
    if (isActive && !isOwner) {
        alert('This crawl is owned by someone else and is still in progress. Wait until it completes to view the results.');
        return;
    }

    if (!confirm('Load this crawl? Current data will be lost.')) return;

    // Show loading overlay on dashboard
    showDashboardLoading('Loading crawl data...', `Preparing crawl #${crawlId}`);

    // Use /load for completed crawls, /reconnect for active/running/paused crawls
    const endpoint = isActive
        ? `/api/crawls/${crawlId}/reconnect`
        : `/api/crawls/${crawlId}/load`;

    try {
        updateDashboardLoading('Loading crawl data...', 'Fetching from database...');
        const response = await fetch(endpoint, { method: 'POST' });
        const data = await response.json();
        if (data.success) {
            updateDashboardLoading('Redirecting...', 'Crawl loaded successfully');
            sessionStorage.setItem('force_ui_refresh', 'true');
            sessionStorage.setItem('current_crawl_id', crawlId);
            if (isActive) {
                window.location.href = `/?reconnect_crawl_id=${crawlId}`;
            } else {
                window.location.href = `/?crawl_id=${crawlId}`;
            }
        } else {
            hideDashboardLoading();
            alert('Error: ' + (data.error || data.message || 'Unknown error'));
        }
    } catch (error) {
        hideDashboardLoading();
        alert('Error opening crawl: ' + error.message);
    }
}

async function renameCrawl(crawlId, currentName) {
    const newName = prompt('Crawl name:', currentName);
    if (newName === null || newName.trim() === '') return;
    try {
        await fetch(`/api/crawls/${crawlId}/save-name`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ crawl_name: newName.trim() })
        });
        loadDashboard();
    } catch (error) {
        alert('Error renaming crawl');
    }
}

async function deleteCrawl(crawlId) {
    if (!confirm('Delete this crawl permanently?')) return;
    try {
        const response = await fetch(`/api/crawls/${crawlId}/delete`, { method: 'DELETE' });
        const data = await response.json();
        if (data.success) loadDashboard();
        else alert('Error: ' + data.error);
    } catch (error) {
        alert('Error deleting crawl');
    }
}

// ========================================
// Initialize
// ========================================

loadDashboard();
