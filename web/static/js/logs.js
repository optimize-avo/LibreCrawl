(function () {
    'use strict';

    const logList = document.getElementById('logList');
    const paginationEl = document.getElementById('pagination');
    const levelFilter = document.getElementById('levelFilter');
    const statusFilter = document.getElementById('statusFilter');
    const searchInput = document.getElementById('searchInput');
    const autoScrollCheck = document.getElementById('autoScroll');
    const clearBtn = document.getElementById('clearLogsBtn');

    const summaryEls = {
        active: document.getElementById('activeCount'),
        completed: document.getElementById('completedCount'),
        failed: document.getElementById('failedCount'),
        stopped: document.getElementById('stoppedCount'),
        total: document.getElementById('totalEvents'),
    };
    const activeCrawlList = document.getElementById('activeCrawlList');
    const activeCrawlCount = document.getElementById('activeCrawlCount');

    let currentPage = 1;
    let totalPages = 1;
    let totalEntries = 0;
    let summary = { active: 0, completed: 0, failed: 0, stopped: 0 };
    const perPage = 20;
    let allEntries = [];
    let newEventsBuffer = [];
    let filterTimer = null;

    function formatTime(iso) {
        const d = new Date(iso);
        return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    function formatTimestamp(iso) {
        const d = new Date(iso);
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' + formatTime(iso);
    }

    function truncateUrl(url, maxLen) {
        if (!url) return '';
        if (url.length <= maxLen) return url;
        return url.substring(0, maxLen - 3) + '...';
    }

    function escapeHtml(text) {
        if (!text) return '';
        const d = document.createElement('div');
        d.textContent = text;
        return d.innerHTML;
    }

    function getStatusClass(status) {
        const s = (status || '').toLowerCase();
        if (s === 'running' || s === 'idle') return 'status-running';
        if (s === 'completed') return 'status-completed';
        if (s === 'failed') return 'status-failed';
        if (s === 'stopped') return 'status-stopped';
        if (s === 'paused') return 'status-paused';
        if (s === 'demo_stopped') return 'status-demo_stopped';
        return '';
    }

    function getLevelClass(level) {
        return 'level-' + (level || 'INFO');
    }

    function matchesFilters(entry) {
        const lv = levelFilter.value;
        if (lv && entry.level !== lv) return false;
        const st = statusFilter.value;
        if (st && (entry.status || '').toLowerCase() !== st) return false;
        const q = searchInput.value.toLowerCase().trim();
        if (q) {
            const haystack = (entry.message + ' ' + (entry.url || '') + ' ' + (entry.source || '')).toLowerCase();
            if (!haystack.includes(q)) return false;
        }
        return true;
    }

    function renderEntry(entry) {
        const div = document.createElement('div');
        div.className = 'log-entry';
        div.dataset.level = entry.level || 'INFO';
        div.dataset.status = (entry.status || '').toLowerCase();
        div.innerHTML = `
            <div class="timestamp" title="${escapeHtml(entry.timestamp)}">${formatTimestamp(entry.timestamp)}</div>
            <div><span class="level-badge ${getLevelClass(entry.level)}">${escapeHtml(entry.level || 'INFO')}</span></div>
            <div class="source">${escapeHtml(entry.source || '')}</div>
            <div class="message" title="${escapeHtml(entry.message)}">${escapeHtml(entry.message)}</div>
            <div class="url-cell" title="${escapeHtml(entry.url || '')}">${escapeHtml(truncateUrl(entry.url, 40))}</div>
            <div><span class="status-badge ${getStatusClass(entry.status)}">${escapeHtml(entry.status || '')}</span></div>
        `;
        return div;
    }

    function renderAll() {
        const filtered = allEntries.filter(matchesFilters);
        logList.innerHTML = '';
        if (filtered.length === 0) {
            logList.innerHTML = '<div class="empty-state">Tidak ada event yang cocok</div>';
            return;
        }
        const frag = document.createDocumentFragment();
        for (const entry of filtered) {
            frag.appendChild(renderEntry(entry));
        }
        logList.appendChild(frag);
        if (autoScrollCheck.checked) {
            logList.scrollTop = 0;
        }
    }

    function debouncedRender() {
        clearTimeout(filterTimer);
        filterTimer = setTimeout(renderAll, 100);
    }

    // --- Pagination ---
    function renderPagination() {
        let html = '';

        if (newEventsBuffer.length > 0 && currentPage > 1) {
            html += `<span class="new-events-bar" data-action="goto-first">${newEventsBuffer.length} event baru — klik untuk lihat</span>`;
        }

        html += `<button class="prev" data-page="${currentPage - 1}" ${currentPage <= 1 ? 'disabled' : ''}>« Prev</button>`;

        const maxVisible = 7;
        let start = Math.max(1, currentPage - Math.floor(maxVisible / 2));
        let end = Math.min(totalPages, start + maxVisible - 1);
        if (end - start + 1 < maxVisible) {
            start = Math.max(1, end - maxVisible + 1);
        }

        if (start > 1) {
            html += `<span class="page-num" data-page="1">1</span>`;
            if (start > 2) html += `<span class="page-info">...</span>`;
        }
        for (let i = start; i <= end; i++) {
            html += `<span class="page-num ${i === currentPage ? 'active' : ''}" data-page="${i}">${i}</span>`;
        }
        if (end < totalPages) {
            if (end < totalPages - 1) html += `<span class="page-info">...</span>`;
            html += `<span class="page-num" data-page="${totalPages}">${totalPages}</span>`;
        }

        html += `<button class="next" data-page="${currentPage + 1}" ${currentPage >= totalPages ? 'disabled' : ''}>Next »</button>`;

        html += `<span class="page-info">${totalEntries} total</span>`;

        paginationEl.innerHTML = html;

        paginationEl.querySelectorAll('.page-num, .prev, .next').forEach(el => {
            const page = parseInt(el.dataset.page);
            if (page && !el.disabled) {
                el.addEventListener('click', () => loadPage(page));
            }
        });
        const newEventsBar = paginationEl.querySelector('[data-action="goto-first"]');
        if (newEventsBar) {
            newEventsBar.addEventListener('click', () => loadPage(1));
        }
    }

    async function loadPage(page) {
        if (page < 1 || page > totalPages) return;
        currentPage = page;
        try {
            const resp = await fetch(`/api/logs?page=${page}&per_page=${perPage}`);
            const data = await resp.json();
            if (data.success) {
                allEntries = data.logs || [];
                totalPages = data.pages || 1;
                totalEntries = data.total || 0;
                if (data.summary) summary = data.summary;
                renderAll();
                renderPagination();
                updateSummary();
                newEventsBuffer = [];
            }
        } catch (e) {
            console.error('Failed to load page:', e);
        }
    }

    // --- Polling (replaces SSE) ---
    let lastPollSince = Date.now() / 1000;
    let isFirstPoll = true;

    async function pollLogs() {
        try {
            const resp = await fetch(`/api/logs/poll?since=${lastPollSince}`);
            const data = await resp.json();
            if (!data.success) return;
            const entries = data.logs || [];
            if (data.summary) {
                summary = data.summary;
                updateSummary();
            }
            for (const entry of entries) {
                const ts = entry.timestamp_epoch || 0;
                if (ts > lastPollSince) lastPollSince = ts;
                totalEntries++;
                if (currentPage === 1 && !isFirstPoll) {
                    allEntries.unshift(entry);
                    if (allEntries.length > perPage) allEntries.pop();
                    renderAll();
                    renderPagination();
                    updateSummary();
                } else {
                    newEventsBuffer.push(entry);
                    renderPagination();
                    updateSummary();
                }
            }
            isFirstPoll = false;
        } catch (e) {
            console.error('Poll error:', e);
        }
    }

    let pollTimer = null;
    function startPolling() {
        pollTimer = setInterval(pollLogs, 2000);
    }
    function stopPolling() {
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    }

    // --- Summary ---
    function updateSummary() {
        summaryEls.active.textContent = summary.active;
        summaryEls.completed.textContent = summary.completed;
        summaryEls.failed.textContent = summary.failed;
        summaryEls.stopped.textContent = summary.stopped;
        summaryEls.total.textContent = totalEntries;
    }

    // --- Active Crawls ---
    function updateActiveCrawls(crawls) {
        if (!crawls || crawls.length === 0) {
            activeCrawlList.innerHTML = '<div class="empty-state">Tidak ada audit berjalan</div>';
            activeCrawlCount.textContent = '0';
            return;
        }
        activeCrawlCount.textContent = crawls.length;
        let html = '';
        for (const c of crawls) {
            const domain = c.base_domain || c.base_url || 'Unknown';
            const progress = c.progress != null ? c.progress : 0;
            const status = (c.status || 'running').toLowerCase();
            const crawled = c.urls_crawled || (c.last_message || '').match(/^(\d+)/)?.[1] || 0;
            const discovered = c.urls_discovered || 0;
            html += `
                <div class="active-crawl-item">
                    <span class="status-dot ${status}"></span>
                    <span class="domain">${escapeHtml(domain)}</span>
                    <span style="color:var(--fg-muted);font-size:11px;">${crawled}/${discovered}</span>
                    <div class="progress-bar">
                        <div class="fill" style="width:${progress}%;background:${status === 'running' ? 'var(--primary)' : status === 'completed' ? 'var(--success)' : 'var(--warning)'};"></div>
                    </div>
                    <span class="progress-label">${Math.round(progress)}%</span>
                    <span class="status-badge ${getStatusClass(status)}">${status}</span>
                    <span style="color:var(--fg-muted);font-size:11px;">${escapeHtml(c.last_message || '')}</span>
                </div>
            `;
        }
        activeCrawlList.innerHTML = html;
    }

    async function loadInitialLogs() {
        await loadPage(1);
    }

    async function loadActiveCrawls() {
        try {
            const resp = await fetch('/api/logs/active');
            const data = await resp.json();
            if (data.success && data.crawls) updateActiveCrawls(data.crawls);
        } catch (e) {
            console.error('Failed to load active crawls:', e);
        }
    }

    // --- Event Listeners ---
    levelFilter.addEventListener('change', debouncedRender);
    statusFilter.addEventListener('change', debouncedRender);
    searchInput.addEventListener('input', debouncedRender);

    clearBtn.addEventListener('click', async function () {
        allEntries = [];
        logList.innerHTML = '<div class="empty-state">Logs cleared</div>';
        paginationEl.innerHTML = '';
        updateSummary();
        await loadPage(1);
    });

    // --- Init ---
    loadInitialLogs();
    loadActiveCrawls();
    setInterval(loadActiveCrawls, 5000);
    startPolling();
})();
