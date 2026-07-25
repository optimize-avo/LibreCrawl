// ========================================
// Dashboard - Domain Sidebar + Crawl Detail
// ========================================

// Dashboard state
let selectedDomain = null;
let compareMode = false;
let selectedCrawls = new Set();
let allDomains = [];

async function loadDashboard() {
    try {
        const response = await fetch('/api/crawls/history');
        const data = await response.json();

        if (!data.success) {
            console.error('Failed to load history:', data.error);
            return;
        }

        allDomains = data.domains || [];
        renderDomainSidebar();

        // Auto-select first domain if available
        if (allDomains.length > 0 && !selectedDomain) {
            selectDomain(allDomains[0].domain);
        } else if (allDomains.length === 0) {
            renderCrawlDetailEmpty();
        }
    } catch (error) {
        console.error('Error loading dashboard:', error);
    }
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

        html += `
            <div class="crawl-card ${isSelected ? 'selected' : ''}">
                ${compareMode ? `<input type="checkbox" class="compare-checkbox" ${isSelected ? 'checked' : ''} onchange="toggleCrawlSelect(${crawl.id})">` : ''}
                <div style="flex:1;min-width:0;">
                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                        <span style="font-size:13px;font-weight:500;color:var(--ink);">${date}</span>
                        <span class="status-badge status-${crawl.status}">${crawl.status}</span>
                        ${crawl.display_name ? `<span style="font-size:12px;color:var(--fg-muted);">— ${escapeHtml(crawl.display_name)}</span>` : ''}
                    </div>
                    <div style="display:flex;gap:16px;font-size:12px;color:var(--fg-muted);">
                        <span>${crawl.urls_crawled || 0} URLs</span>
                        <span style="color:${issues > 0 ? 'var(--error)' : 'var(--success)'};">${issues} issues</span>
                        ${crawl.completed_at ? `<span>${formatDuration(crawl.started_at, crawl.completed_at)}</span>` : ''}
                    </div>
                </div>
                <div style="display:flex;gap:6px;flex-shrink:0;">
                    ${crawl.urls_crawled > 0 ? `<button class="action-btn" onclick="loadCrawl(${crawl.id})">Load</button>` : ''}
                    <button class="action-btn" onclick="renameCrawl(${crawl.id}, '${(crawl.display_name || '').replace(/'/g, "\\'")}')">Rename</button>
                    <button class="action-btn danger" onclick="deleteCrawl(${crawl.id})">Delete</button>
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

async function loadCrawl(crawlId) {
    if (!confirm('Load this crawl? Current data will be lost.')) return;
    try {
        const response = await fetch(`/api/crawls/${crawlId}/load`, { method: 'POST' });
        const data = await response.json();
        if (data.success) {
            sessionStorage.setItem('force_ui_refresh', 'true');
            window.location.href = '/';
        } else {
            alert('Error: ' + (data.error || data.message));
        }
    } catch (error) {
        alert('Error loading crawl: ' + error.message);
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
