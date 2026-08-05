const DASHBOARD = document.getElementById('dashboard');
const LOGIN_PAGE = document.getElementById('login-page');
const ERROR_EL = document.getElementById('login-error');
const requestsEl = document.getElementById('requests');
const emptyStateEl = document.getElementById('empty-state');
const countEl = document.getElementById('request-count');
const containerFilterEl = document.getElementById('filter-container');
const searchInputEl = document.getElementById('search-input');
const statusDotEl = document.getElementById('status-dot');
const liveTailBtnEl = document.getElementById('live-tail-btn');
const liveTailLabelEl = document.getElementById('live-tail-label');

const LEVEL_RANK = { CRITICAL: 0, ERROR: 1, WARNING: 2, INFO: 3, DEBUG: 4, UNKNOWN: 5 };
const ERROR_LEVELS = new Set(['CRITICAL', 'ERROR']);
const ALL_LEVELS = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'UNKNOWN'];
const PAGE_SIZES = [10, 20, 30, 50, 100];

let activeViewId = null;
let expandedSet = new Set();
let allRequests = [];
let ws;
let stats = {
    total: 0,
    errors: 0,
    history: []
};
let knownContainers = new Set();
let all_requests_count = 0;
let currentPage = 1;
let pageLimit = parseInt(localStorage.getItem('pageLimit'), 10) || 20;
let loadingPage = false;

function changePageSize() {
    const pageSizeEl = document.getElementById('page-size');
    pageLimit = parseInt(pageSizeEl.value, 10) || 20;
    localStorage.setItem('pageLimit', pageLimit);
    if (allRequests.length > pageLimit) {
        allRequests.length = pageLimit;
    }
    fetchPage(1);
}

let isLive = true;
let pendingNewCount = 0;
let activeLevels = new Set();

// ---------------- Theme management ----------------
function toggleTheme() {
    document.body.classList.toggle('light-mode');
    localStorage.setItem('theme', document.body.classList.contains('light-mode') ? 'light' : 'dark');
}

function loadTheme() {
    const theme = localStorage.getItem('theme');
    if (theme === 'light') {
        document.body.classList.add('light-mode');
    }
}

// ---------------- Login handling ----------------
async function login(event) {
    event.preventDefault();

    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value.trim();
    const loginBtn = document.getElementById('login-btn');
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');

    if (!username || !password) {
        ERROR_EL.textContent = 'Please fill in all fields';
        ERROR_EL.classList.remove('hidden');
        usernameInput.classList.add('error');
        passwordInput.classList.add('error');
        return;
    }

    loginBtn.disabled = true;
    loginBtn.textContent = 'Logging in...';

    try {
        const res = await fetch('/auth', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const auth_response = await res.json();

        if (auth_response.message === "success") {
            localStorage.setItem('auth', 'true');
            ERROR_EL.classList.add('hidden');
            usernameInput.classList.remove('error');
            passwordInput.classList.remove('error');
            LOGIN_PAGE.classList.add('hidden');
            DASHBOARD.classList.remove('hidden');
            loadContainers();
            loadAlertAvailability();
            loadAlertSettings();
            fetchPage(1);
            initWebSocket();
        } else {
            ERROR_EL.textContent = 'Invalid credentials';
            ERROR_EL.classList.remove('hidden');
            usernameInput.classList.add('error');
            passwordInput.classList.add('error');
        }
    } catch (err) {
        console.log(err);
        ERROR_EL.textContent = 'Connection error. Please try again.';
        ERROR_EL.classList.remove('hidden');
    } finally {
        loginBtn.disabled = false;
        loginBtn.textContent = 'Login';
    }
}

function handleSessionExpired() {
    localStorage.removeItem('auth');
    if (ws) ws.close();
    DASHBOARD.classList.add('hidden');
    LOGIN_PAGE.classList.remove('hidden');
}

async function logout() {
    try {
        await fetch('/api/logout', { method: 'POST' });
    } catch (err) {
        console.log('logout request failed', err);
    }

    localStorage.removeItem('auth');
    DASHBOARD.classList.add('hidden');
    LOGIN_PAGE.classList.remove('hidden');

    if (ws) ws.close();
    allRequests = [];
    all_requests_count = 0;
    stats = { total: 0, errors: 0, history: [] };
    knownContainers = new Set();
    pendingNewCount = 0;
    isLive = true;
    updateLiveTailUI();

    countEl.textContent = `${all_requests_count} logs`;
    document.getElementById('total-requests').textContent = all_requests_count;

    requestsEl.innerHTML = '';
    emptyStateEl.style.display = 'block';
}

// ---------------- WebSocket ----------------
let wsReconnectAttempts = 0;
let wsReconnectTimer = null;

function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.hostname}:${window.location.port}/ws`);

    ws.onopen = () => {
        wsReconnectAttempts = 0;
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        addRequest(data);
    };

    ws.onclose = () => {
        console.log('WebSocket disconnected, reconnecting...');
        scheduleReconnect();
    };

    ws.onerror = () => {
        ws.close();
    };
}

function scheduleReconnect() {
    if (wsReconnectTimer) return;
    const delay = Math.min(1000 * (2 ** wsReconnectAttempts), 30000);
    wsReconnectAttempts++;
    wsReconnectTimer = setTimeout(() => {
        wsReconnectTimer = null;
        if (localStorage.getItem('auth') === 'true') {
            initWebSocket();
        }
    }, delay);
}

// ---------------- Live tail ----------------
function toggleLiveTail() {
    isLive = !isLive;
    if (isLive) {
        pendingNewCount = 0;
        applyFilters();
    }
    updateLiveTailUI();
}

function updateLiveTailUI() {
    if (!liveTailBtnEl) return;
    if (isLive) {
        liveTailBtnEl.classList.remove('paused');
        liveTailLabelEl.textContent = 'Live';
    } else {
        liveTailBtnEl.classList.add('paused');
        liveTailLabelEl.textContent = pendingNewCount > 0 ? `Paused (+${pendingNewCount})` : 'Paused';
    }
}

// ---------------- Container color coding ----------------
function containerColor(name) {
    if (!name) return 'transparent';
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
        hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
    }
    const hue = hash % 360;
    return `hsl(${hue}, 60%, 55%)`;
}

// ---------------- Containers filter ----------------
async function loadContainers() {
    try {
        const res = await fetch('/api/containers');
        const result = await res.json();
        (result.containers || []).forEach(name => knownContainers.add(name));
        renderContainerOptions();
    } catch (err) {
        console.log('failed to load containers', err);
    }
}

function renderContainerOptions() {
    const current = containerFilterEl.value;
    const names = Array.from(knownContainers).sort();

    containerFilterEl.innerHTML = '<option value="all">All</option>' +
        names.map(name => `<option value="${name}">${name}</option>`).join('');

    if (names.includes(current) || current === 'all') {
        containerFilterEl.value = current;
    }

    const activeContainersEl = document.getElementById('active-containers');
    if (activeContainersEl) activeContainersEl.textContent = knownContainers.size;
}

function noteContainer(name) {
    if (!name || knownContainers.has(name)) return;
    knownContainers.add(name);
    renderContainerOptions();
}

// ---------------- Alerts configuration ----------------
let alertAvailability = { slack: false, gmail: false };

async function loadAlertAvailability() {
    try {
        const res = await fetch('/api/alerts/availability');
        alertAvailability = await res.json();
        renderAlertAvailabilityWarning();
    } catch (err) {
        console.log('failed to load alert availability', err);
    }
}

async function loadAlertSettings() {
    try {
        const res = await fetch('/api/alerts/settings');
        const settings = await res.json();
        document.getElementById('alert-slack-enabled').checked = !!settings.slack_enabled;
        document.getElementById('alert-gmail-enabled').checked = !!settings.gmail_enabled;
        document.getElementById('alert-min-level').value = settings.min_level || 'ERROR';
        updateAlertStatusBadge(!!settings.slack_enabled, !!settings.gmail_enabled);
        renderAlertAvailabilityWarning();
    } catch (err) {
        console.log('failed to load alert settings', err);
    }
}

function renderAlertAvailabilityWarning() {
    const slackEnabled = document.getElementById('alert-slack-enabled')?.checked;
    const gmailEnabled = document.getElementById('alert-gmail-enabled')?.checked;
    const slackWarnEl = document.getElementById('alert-warning-slack');
    const gmailWarnEl = document.getElementById('alert-warning-gmail');

    if (slackWarnEl) {
        const show = slackEnabled && !alertAvailability.slack;
        if (show) {
            slackWarnEl.textContent = "Set APIWATCH_SLACK_WEBHOOK to enable Slack alerts.";
        }
        slackWarnEl.classList.toggle('hidden', !show);
    }

    if (gmailWarnEl) {
        const show = gmailEnabled && !alertAvailability.gmail;
        if (show) {
            gmailWarnEl.textContent = "Set APIWATCH_GMAIL_APP_PASS & APIWATCH_GMAIL to enable Gmail alerts.";
        }
        gmailWarnEl.classList.toggle('hidden', !show);
    }
}

function onAlertChannelToggle() {
    renderAlertAvailabilityWarning();
}

function updateAlertStatusBadge(slackEnabled, gmailEnabled) {
    const badge = document.getElementById('alerts-status-badge');
    if (!badge) return;

    let label = 'Disabled';
    if (slackEnabled && gmailEnabled) label = 'Slack + Gmail';
    else if (slackEnabled) label = 'Slack';
    else if (gmailEnabled) label = 'Gmail';

    const anyEnabled = slackEnabled || gmailEnabled;
    badge.textContent = label;
    badge.classList.toggle('enabled', anyEnabled);

    const card = document.getElementById('alert-card');
    if (card) card.classList.toggle('enabled', anyEnabled);
}

async function saveAlertSettings() {
    const slack_enabled = document.getElementById('alert-slack-enabled').checked;
    const gmail_enabled = document.getElementById('alert-gmail-enabled').checked;
    const min_level = document.getElementById('alert-min-level').value;

    if (slack_enabled && !alertAvailability.slack) {
        alert("Can't enable Slack alerts, that channel isn't configured on the server yet.");
        return;
    }
    if (gmail_enabled && !alertAvailability.gmail) {
        alert("Can't enable Gmail alerts, that channel isn't configured on the server yet.");
        return;
    }

    try {
        const res = await fetch('/api/alerts/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ slack_enabled, gmail_enabled, min_level })
        });
        if (!res.ok) {
            const err = await res.json();
            alert(err.error || 'Failed to save alert settings');
            return;
        }
        const data = await res.json().catch(() => ({}));
        updateAlertStatusBadge(slack_enabled, gmail_enabled);
        showAlertFlash(data.status === 'saved' ? 'Saved' : 'Done');
    } catch (err) {
        console.log('failed to save alert settings', err);
    }
}

let alertFlashTimer = null;
function showAlertFlash(text) {
    const el = document.getElementById('alert-save-flash');
    if (!el) return;
    el.textContent = text;
    el.classList.add('show');
    if (alertFlashTimer) clearTimeout(alertFlashTimer);
    alertFlashTimer = setTimeout(() => {
        el.classList.remove('show');
    }, 2000);
}

let searchDebounceTimer = null;
function onSearchInput() {
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
        fetchPage(1);
    }, 300);
}

// ---------------- Pagination ----------------
async function fetchPage(page) {
    if (loadingPage) return;
    loadingPage = true;

    const search = searchInputEl ? searchInputEl.value.trim() : '';
    const params = new URLSearchParams({ page, limit: pageLimit });
    if (search) params.set('search', search);

    const res = await fetch(`/api/history?${params.toString()}`);
    if (res.status === 401) {
        loadingPage = false;
        handleSessionExpired();
        return;
    }
    const result = await res.json();

    currentPage = result.page;
    all_requests_count = result.data.total;
    allRequests = result.data.results;

    allRequests.forEach(r => noteContainer(r.container_name));
    recalcStats();

    applyFilters();
    document.getElementById("page-num").textContent = currentPage;

    loadingPage = false;
}

function nextPage() {
    fetchPage(currentPage + 1);
}

function prevPage() {
    if (currentPage > 1) {
        fetchPage(currentPage - 1);
    }
}

// ---------------- JSON tree rendering ----------------
function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

function renderJsonNode(value, keyLabel, depth, term) {
    const keyHtml = keyLabel !== null
        ? `<span class="json-key">"${highlightMatch(String(keyLabel), term)}"</span>: `
        : '';

    if (value === null) {
        return `<div class="json-line">${keyHtml}<span class="json-null">null</span></div>`;
    }
    if (typeof value === 'boolean') {
        return `<div class="json-line">${keyHtml}<span class="json-bool">${highlightMatch(value, term)}</span></div>`;

    }
    if (typeof value === 'number') {
        return `<div class="json-line">${keyHtml}<span class="json-number">${highlightMatch(value, term)}</span></div>`;

    }
    if (typeof value === 'string') {
        return `<div class="json-line">${keyHtml}<span class="json-string">"${highlightMatch(value, term)}"</span></div>`;
    }

    const isArray = Array.isArray(value);
    const entries = isArray ? value.map((v, i) => [i, v]) : Object.entries(value);

    if (entries.length === 0) {
        return `<div class="json-line">${keyHtml}<span class="json-bracket">${isArray ? '[]' : '{}'}</span></div>`;
    }

    const childrenHtml = entries
        .map(([k, v]) => renderJsonNode(v, isArray ? null : k, depth + 1, term))
        .join('');

    const openLine = `<div class="json-line json-open" onclick="toggleJsonNode(this)"><span class="json-toggle">\u25BE</span>${keyHtml}<span class="json-bracket">${isArray ? '[' : '{'}</span><span class="json-count">${entries.length} item${entries.length !== 1 ? 's' : ''}</span></div>`;
    const closeLine = `<div class="json-line json-close"><span class="json-bracket">${isArray ? ']' : '}'}</span></div>`;

    return `<div class="json-node">${openLine}<div class="json-children">${childrenHtml}</div>${closeLine}</div>`;
}

function toggleJsonNode(clickedEl) {
    const node = clickedEl.closest('.json-node');
    if (!node) {
        console.error('toggleJsonNode: no .json-node ancestor found for', clickedEl);
        return;
    }

    let children = null;
    for (const child of node.children) {
        if (child.classList && child.classList.contains('json-children')) {
            children = child;
            break;
        }
    }

    if (!children) {
        console.error('toggleJsonNode: no direct .json-children found inside', node);
        return;
    }

    const isCollapsed = children.classList.toggle('collapsed');
    const icon = clickedEl.classList.contains('json-toggle')
        ? clickedEl
        : clickedEl.querySelector('.json-toggle');
    if (icon) icon.textContent = isCollapsed ? '\u25B8' : '\u25BE';
}


function renderDetailContent(text, parsedDataJson, term) {
    if (parsedDataJson) {
        try {
            const parsed = JSON.parse(parsedDataJson);
            if (parsed !== null && typeof parsed === 'object') {
                return `<div class="json-tree">${renderJsonNode(parsed, null, 0, term)}</div>`;
            }
        } catch (e) {
            // fall through
        }
    }

    if (!text) return '';
    try {
        const parsed = JSON.parse(text);
        if (parsed !== null && typeof parsed === 'object') {
            return `<div class="json-tree">${renderJsonNode(parsed, null, 0, term)}</div>`;
        }
    } catch (e) {
        // not JSON, fall through to plain text
    }
    return `<pre>${highlightMatch(text, term)}</pre>`;
}


function findRequestById(id) {
    return allRequests.find(r => String(r.id) === String(id));
}

async function copyDetailField(id, field, btnEl) {
    const req = findRequestById(id);
    if (!req || !req[field]) return;

    let toCopy = req[field];
    try {
        const parsed = JSON.parse(toCopy);
        if (parsed !== null && typeof parsed === 'object') {
            toCopy = JSON.stringify(parsed, null, 2);
        }
    } catch (e) {
        // not JSON, copy as-is
    }

    try {
        await navigator.clipboard.writeText(toCopy);
        const original = btnEl.textContent;
        btnEl.textContent = 'Copied';
        btnEl.classList.add('copied');
        setTimeout(() => {
            btnEl.textContent = original;
            btnEl.classList.remove('copied');
        }, 1500);
    } catch (err) {
        console.log('copy failed, likely no clipboard access (needs https or localhost)', err);
    }
}

// ---------------- Requests handling ----------------
function addRequest(req) {
    emptyStateEl.style.display = 'none';

    req.id = Date.now() + Math.random();
    allRequests.unshift(req);
    all_requests_count++;
    noteContainer(req.container_name);

    let overflowed = false;
    if (allRequests.length > pageLimit) {
        allRequests.length = pageLimit;
        overflowed = true;
    }

    const isError = ERROR_LEVELS.has(req.level);
    stats.total++;
    if (isError) stats.errors++;

    stats.history.push({ time: Date.now(), isError });
    if (stats.history.length > 20) stats.history.shift();

    updateStats();
    updateBeacon(isError);

    if (isLive) {
        if (overflowed) {
            applyFilters();
        } else {
            renderNewRequest(req);
        }
    } else {
        pendingNewCount++;
        updateLiveTailUI();
    }
}

let beaconResetTimer = null;
function updateBeacon(isError) {
    if (!statusDotEl) return;
    if (isError) {
        statusDotEl.classList.add('alert');
        if (beaconResetTimer) clearTimeout(beaconResetTimer);
        beaconResetTimer = setTimeout(() => statusDotEl.classList.remove('alert'), 4000);
    }
}

function recalcStats() {
    stats.total = allRequests.length;
    stats.errors = allRequests.filter(r => ERROR_LEVELS.has(r.level)).length;
    stats.history = allRequests.slice(-20).map(r => ({
        time: new Date(r.timestamp).getTime(),
        isError: ERROR_LEVELS.has(r.level)
    }));
    updateStats();
}

function renderNewRequest(req) {
    const sortBy = document.getElementById('sort-by').value;
    if (sortBy !== 'time-desc' || !passesFilters(req)) {
        applyFilters();
        return;
    }
    requestsEl.insertAdjacentHTML('afterbegin', renderRequest(req));
}

function highlightMatch(text, term) {
    const escaped = escapeHtml(text);
    if (!term) return escaped;
    const escapedTerm = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return escaped.replace(new RegExp(`(${escapedTerm})`, 'ig'), '<mark>$1</mark>');
}

function renderRequest(req) {
    const level = req.level || 'UNKNOWN';
    const term = searchInputEl ? searchInputEl.value.trim() : '';
    const messageRaw = req.message || req.raw || '';
    const dotColor = containerColor(req.container_name);
    const containerBadge = req.container_name
        ? `<span class="service-badge"><span class="container-dot" style="background:${dotColor}"></span>${escapeHtml(req.container_name)}</span>`
        : '';
    const timestamp = req.timestamp ? new Date(req.timestamp) : null;
    const timeLabel = timestamp && !isNaN(timestamp) ? timestamp.toLocaleTimeString() : '---';

    return `
        <div class="request-item ${String(activeViewId) === String(req.id) ? 'active-view' : ''}" data-id="${req.id}" data-level="${level}">
            <div class="request-header" onclick="toggleDetails(this)">
                ${containerBadge}
                <span class="level level-${level}">${level}</span>
                <span class="message">${highlightMatch(messageRaw, term)}</span>
                <span class="timestamp">${timeLabel}</span>
            </div>
            <div class="request-details ${expandedSet.has(req.id) ? 'open' : ''}">
                ${req.logger ? `<div class="detail-section"><div class="detail-label-row"><span class="detail-label">Logger</span><button class="copy-btn" onclick="copyDetailField('${req.id}', 'logger', this)">Copy</button></div><div class="detail-content"><pre>${highlightMatch(req.logger, term)}</pre></div></div>` : ''}
                ${req.raw ? `<div class="detail-section"><div class="detail-label-row"><span class="detail-label">Raw Line</span><button class="copy-btn" onclick="copyDetailField('${req.id}', 'raw', this)">Copy</button></div><div class="detail-content">${renderDetailContent(req.raw, req.parsed_data, term)}</div></div>` : ''}
            </div>
        </div>`;
}

function toggleDetails(header) {
    const item = header.parentElement;
    const id = item.dataset.id;
    const details = header.nextElementSibling;
    details.classList.toggle('open');
    if (details.classList.contains('open')) expandedSet.add(id);
    else expandedSet.delete(id);

    setActiveView(id);
}

function setActiveView(id) {
    activeViewId = id;
    document.querySelectorAll('.request-item.active-view').forEach(el => {
        el.classList.remove('active-view');
    });
    const item = requestsEl.querySelector(`.request-item[data-id="${id}"]`);
    if (item) item.classList.add('active-view');
}

// ---------------- Filters & Sorting ----------------
function toggleLevelChip(level, el) {
    if (activeLevels.has(level)) {
        activeLevels.delete(level);
        el.classList.remove('active');
    } else {
        activeLevels.add(level);
        el.classList.add('active');
    }
    applyFilters();
}

function passesFilters(req) {
    const containerFilter = containerFilterEl.value;
    const term = searchInputEl ? searchInputEl.value.trim().toLowerCase() : '';
    const level = req.level || 'UNKNOWN';

    const levelMatch = activeLevels.size === 0 || activeLevels.has(level);
    const containerMatch = containerFilter === 'all' || req.container_name === containerFilter;
    const text = (req.message || req.raw || '').toLowerCase();
    const searchMatch = !term || text.includes(term);

    return levelMatch && containerMatch && searchMatch;
}

function getFilteredRequests() {
    return allRequests.filter(passesFilters);
}

function applyFilters() {
    renderRequests(getFilteredRequests());
}

function applySort() {
    applyFilters();
}

function renderRequests(requests) {
    const sortBy = document.getElementById('sort-by').value;

    let sorted = [...requests];
    switch (sortBy) {
        case 'time-asc': sorted.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp)); break;
        case 'time-desc': sorted.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)); break;
        case 'level-desc':
            sorted.sort((a, b) => (LEVEL_RANK[a.level] ?? 5) - (LEVEL_RANK[b.level] ?? 5));
            break;
        case 'level-asc':
            sorted.sort((a, b) => (LEVEL_RANK[b.level] ?? 5) - (LEVEL_RANK[a.level] ?? 5));
            break;
    }

    requestsEl.innerHTML = sorted.map(req => renderRequest(req)).join('');
    emptyStateEl.style.display = sorted.length === 0 && allRequests.length > 0 ? 'block' : 'none';
}

// ---------------- Export ----------------
function exportLogs() {
    const filtered = getFilteredRequests();
    const payload = filtered.map(({ id, ...rest }) => rest);
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    a.href = url;
    a.download = `apiwatch-logs-${stamp}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}

// ---------------- Stats & Charts ----------------
function updateStats() {
    countEl.textContent = `${all_requests_count} log${all_requests_count !== 1 ? 's' : ''}`;
    document.getElementById('total-requests').textContent = all_requests_count;

    const errorRate = stats.total > 0 ? Math.round((stats.errors / stats.total) * 100) : 0;
    document.getElementById('error-rate').textContent = errorRate + '%';

    document.getElementById('active-containers').textContent = knownContainers.size;

    updateCharts();
}

function updateCharts() {
    const chartTotal = document.getElementById('chart-total');
    chartTotal.innerHTML = stats.history.slice(-10).map((h, i) => `<div class="chart-bar ${i === stats.history.length - 1 ? 'active' : ''}" style="height: ${20 + (i * 2)}px"></div>`).join('');

    const chartError = document.getElementById('chart-error');
    chartError.innerHTML = stats.history.slice(-10).map(h => `<div class="chart-bar ${h.isError ? 'active' : ''}" style="height: ${h.isError ? 40 : 15}px; opacity: ${h.isError ? 1 : 0.3}"></div>`).join('');
}

// ---------------- Clear ----------------
async function clearRequests() {
    if (confirm('Clear all logs?')) {
        const res = await fetch('/api/clear', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
        await res.json();

        allRequests = [];
        all_requests_count = 0;
        stats = { total: 0, errors: 0, history: [] };
        pendingNewCount = 0;
        updateLiveTailUI();

        requestsEl.innerHTML = '';
        emptyStateEl.style.display = 'block';
        updateStats();
    }
}

// ---------------- Header menu (mobile) ----------------
function toggleHeaderMenu(event) {
    event.stopPropagation();
    const dropdown = document.getElementById('header-menu-dropdown');
    const btn = document.getElementById('header-menu-btn');
    if (!dropdown) return;
    const isOpen = !dropdown.classList.contains('hidden');
    dropdown.classList.toggle('hidden', isOpen);
    if (btn) btn.setAttribute('aria-expanded', String(!isOpen));
}

document.addEventListener('click', (event) => {
    const dropdown = document.getElementById('header-menu-dropdown');
    const btn = document.getElementById('header-menu-btn');
    if (!dropdown || dropdown.classList.contains('hidden')) return;
    if (dropdown.contains(event.target) || (btn && btn.contains(event.target))) return;
    dropdown.classList.add('hidden');
    if (btn) btn.setAttribute('aria-expanded', 'false');
});

// ---------------- Initialize ----------------
loadTheme();

const pageSizeInitEl = document.getElementById('page-size');
if (pageSizeInitEl) {
    pageSizeInitEl.innerHTML = PAGE_SIZES
        .map(n => `<option value="${n}">${n}</option>`)
        .join('');
    pageSizeInitEl.value = String(pageLimit);
}

async function checkAuthAndInit() {
    const loadingEl = document.getElementById('app-loading');

    if (localStorage.getItem('auth') !== 'true') {
        if (loadingEl) loadingEl.classList.add('hidden');
        LOGIN_PAGE.classList.remove('hidden');
        return;
    }

    try {
        const res = await fetch('/api/me');
        if (!res.ok) {
            localStorage.removeItem('auth');
            if (loadingEl) loadingEl.classList.add('hidden');
            LOGIN_PAGE.classList.remove('hidden');
            return;
        }
        if (loadingEl) loadingEl.classList.add('hidden');
        DASHBOARD.classList.remove('hidden');
        loadContainers();
        loadAlertAvailability();
        loadAlertSettings();
        fetchPage(1);
        initWebSocket();
    } catch (err) {
        console.log('auth check failed', err);
        if (loadingEl) loadingEl.classList.add('hidden');
        LOGIN_PAGE.classList.remove('hidden');
    }
}

checkAuthAndInit();