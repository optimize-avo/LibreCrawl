// Parse URL params
const params = new URLSearchParams(window.location.search);
const ids = params.get('ids') || (params.get('id_a') && params.get('id_b') ? params.get('id_a') + ',' + params.get('id_b') : null);

if (!ids || !ids.includes(',')) {
    document.getElementById('compareHeader').innerHTML = '<p style="color:var(--error);">No crawl IDs provided. Go to Dashboard and select 2 crawls to compare.</p>';
} else {
    loadComparison(ids);
}

async function loadComparison(ids) {
    try {
        const response = await fetch(`/api/crawls/compare?ids=${ids}`);
        const data = await response.json();
        
        if (!data.success) {
            document.getElementById('compareHeader').innerHTML = `<p style="color:var(--error);">Error: ${data.error}</p>`;
            return;
        }
        
        renderHeader(data);
        renderSummary(data.summary);
        renderCategories(data.categories);
        
    } catch (error) {
        document.getElementById('compareHeader').innerHTML = `<p style="color:var(--error);">Failed to load comparison: ${error.message}</p>`;
    }
}

function renderHeader(data) {
    const a = data.crawl_a;
    const b = data.crawl_b;
    const dateA = new Date(a.started_at).toLocaleString();
    const dateB = new Date(b.started_at).toLocaleString();
    
    document.getElementById('compareHeader').innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
            <a href="/dashboard" style="font-size:12px;color:var(--primary);text-decoration:none;">← Back to Dashboard</a>
        </div>
        <h1 style="font-size:18px;font-weight:600;color:var(--ink);margin-bottom:12px;">Compare: ${a.base_url || a.crawl_name}</h1>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
            <div class="crawl-card">
                <div class="tag">Older Run (B)</div>
                <div class="date">${dateB}</div>
                <div class="meta">${b.urls_crawled || 0} URLs · ${data.summary.total_issues_b} issues</div>
            </div>
            <div class="crawl-card">
                <div class="tag">Newer Run (A)</div>
                <div class="date">${dateA}</div>
                <div class="meta">${a.urls_crawled || 0} URLs · ${data.summary.total_issues_a} issues</div>
            </div>
        </div>
    `;
}

function renderSummary(summary) {
    const container = document.getElementById('compareSummary');
    container.style.display = 'grid';
    container.style.gridTemplateColumns = 'repeat(3, 1fr)';
    container.style.gap = '12px';
    
    container.innerHTML = `
        <div class="summary-card">
            <div class="count" style="color:var(--success);">${summary.fixed}</div>
            <div class="label">Fixed (improved)</div>
        </div>
        <div class="summary-card">
            <div class="count" style="color:var(--fg-muted);">${summary.still}</div>
            <div class="label">Still present</div>
        </div>
        <div class="summary-card">
            <div class="count" style="color:var(--error);">${summary.new}</div>
            <div class="label">New (regression)</div>
        </div>
    `;
}

function renderCategories(categories) {
    const container = document.getElementById('compareCategories');
    
    if (!categories || categories.length === 0) {
        container.innerHTML = '<p style="color:var(--fg-muted);text-align:center;padding:40px;">No issues to compare</p>';
        return;
    }
    
    container.innerHTML = categories.map(cat => {
        const items = cat.items || [];
        const fixedItems = items.filter(i => i.status === 'fixed');
        const stillItems = items.filter(i => i.status === 'still');
        const newItems = items.filter(i => i.status === 'new');
        
        return `
            <div class="category-section">
                <div class="category-header" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'block' : 'none'">
                    <div>
                        <span style="font-size:14px;font-weight:500;color:var(--ink);">${formatCategory(cat.category)}</span>
                        <span style="font-size:12px;color:var(--fg-muted);margin-left:8px;">${cat.count_b} → ${cat.count_a}</span>
                    </div>
                    <div style="display:flex;gap:8px;font-size:12px;">
                        ${cat.fixed > 0 ? `<span style="color:var(--success);">✓ ${cat.fixed} fixed</span>` : ''}
                        ${cat.new > 0 ? `<span style="color:var(--error);">+ ${cat.new} new</span>` : ''}
                    </div>
                </div>
                <div class="category-items">
                    ${renderItems(fixedItems, 'fixed')}
                    ${renderItems(stillItems, 'still')}
                    ${renderItems(newItems, 'new')}
                </div>
            </div>
        `;
    }).join('');
}

function renderItems(items, status) {
    if (items.length === 0) return '';
    const icon = status === 'fixed' ? '✅' : status === 'still' ? '➖' : '🆕';
    const label = status === 'fixed' ? 'FIXED' : status === 'still' ? 'STILL' : 'NEW';
    const cls = `diff-${status}`;
    
    return items.map(item => `
        <div class="diff-item ${cls}">
            <span style="font-size:12px;margin-right:6px;">${icon}</span>
            <span style="font-size:11px;font-weight:500;color:var(--fg-muted);margin-right:8px;">${label}</span>
            <a href="${item.url}" target="_blank" style="color:var(--primary);text-decoration:none;font-weight:500;">${item.url}</a>
            <span style="color:var(--fg-muted);margin-left:8px;">— ${item.issue}</span>
        </div>
    `).join('');
}

function formatCategory(cat) {
    return cat.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}
