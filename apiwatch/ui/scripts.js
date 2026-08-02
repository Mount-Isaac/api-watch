console.log('[apiwatch] scripts.js loaded, build: v3-redesign+alerts');

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
// not an arithmetic range (10/20/30/50/100 has no constant step), so this
// stays an explicit list - but it's the one place it's defined, and the
// <select> is built from it instead of duplicating these values in HTML
const PAGE_SIZES = [10, 20, 30, 50, 100];

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
// rows-per-page: also doubles as the cap on the live-stream buffer (see
// addRequest), so changing it affects both the paginated fetch size and
// how many live rows are kept in memory before the oldest rolls off
let pageLimit = parseInt(localStorage.getItem('pageLimit'), 10) || 20;
let loadingPage = false;

function changePageSize() {
    const pageSizeEl = document.getElementById('page-size');
    pageLimit = parseInt(pageSizeEl.value, 10) || 20;
    localStorage.setItem('pageLimit', pageLimit);
    // trim what's already in memory too, so a live buffer that was built
    // up at the old size doesn't stay oversized until the next log arrives
    if (allRequests.length > pageLimit) {
        allRequests.length = pageLimit;
    }
    fetchPage(1);
}

// live-tail state: when paused, incoming ws messages are still recorded
// (stats stay accurate) but not rendered until the user resumes, so a
// busy stream doesn't yank a row they're mid-read on out from under them
let isLive = true;
let pendingNewCount = 0;

// active level filter set - multi-select chips. Empty = no filter, show
// every level. Clicking a chip narrows the view down to just the level(s)
// selected (click Error + Critical to see both together), rather than
// starting "everything on" and having clicks subtract from that.
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
            // the real session lives in an httponly cookie the server just
            // set, this flag is only so we don't flash the login page on
            // next reload, /api/me is what actually verifies the cookie
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
    // session died mid-use (TTL expiry, server restart cleared it), drop
    // back to the login page without hitting /api/logout, there's no
    // valid session left to invalidate
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
    // capped exponential backoff: 1s, 2s, 4s, ... up to 30s, so a
    // restarting apiwatch container or nginx reload doesn't get
    // hammered with reconnect attempts
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
// deterministic hash -> hue, so the same container name always gets the
// same swatch color across reloads and across every logged-in user
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

    // keep whatever the user had selected, if it still exists
    if (names.includes(current) || current === 'all') {
        containerFilterEl.value = current;
    }

    // active-containers stat reads knownContainers directly - keep it in
    // sync any time this set changes, not just whenever updateStats()
    // next happens to run
    const activeContainersEl = document.getElementById('active-containers');
    if (activeContainersEl) activeContainersEl.textContent = knownContainers.size;
}

function noteContainer(name) {
    if (!name || knownContainers.has(name)) return;
    // a new container shows up mid-session, we add it, we never remove
    // one just because it stopped, its past logs are still browsable
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
        if (settings.channel) {
            document.getElementById('alert-channel').value = settings.channel;
        }
        document.getElementById('alert-min-level').value = settings.min_level || 'ERROR';
        document.getElementById('alert-enabled').checked = !!settings.enabled;
        updateAlertStatusBadge(!!settings.enabled);
        renderAlertAvailabilityWarning();
    } catch (err) {
        console.log('failed to load alert settings', err);
    }
}

function renderAlertAvailabilityWarning() {
    const channelEl = document.getElementById('alert-channel');
    const warningEl = document.getElementById('alert-warning');
    if (!channelEl || !warningEl) return;

    const channel = channelEl.value;
    if (!alertAvailability[channel]) {
        const envHint = channel === 'slack'
            ? 'APIWATCH_SLACK_WEBHOOK_URL is not set on the container.'
            : 'APIWATCH_GMAIL_USER / APIWATCH_GMAIL_APP_PASSWORD are not set on the container.';
        const label = channel === 'slack' ? 'Slack' : 'Gmail';
        warningEl.textContent = `${label} isn't configured yet. ${envHint}`;
        warningEl.classList.remove('hidden');
    } else {
        warningEl.classList.add('hidden');
    }
}

function onAlertChannelChange() {
    renderAlertAvailabilityWarning();
}

function updateAlertStatusBadge(enabled) {
    const badge = document.getElementById('alerts-status-badge');
    if (!badge) return;
    badge.textContent = enabled ? 'Enabled' : 'Disabled';
    badge.classList.toggle('enabled', !!enabled);

    // the alerts card's left accent bar goes green ("armed") when alerts
    // are actually on, same visual language as the other stat cards
    const card = document.getElementById('alert-card');
    if (card) card.classList.toggle('enabled', !!enabled);
}

async function saveAlertSettings() {
    const channel = document.getElementById('alert-channel').value;
    const min_level = document.getElementById('alert-min-level').value;
    const enabled = document.getElementById('alert-enabled').checked;

    if (enabled && !alertAvailability[channel]) {
        alert(`Can't enable ${channel === 'slack' ? 'Slack' : 'Gmail'} alerts, that channel isn't configured on the server yet.`);
        return;
    }

    try {
        const res = await fetch('/api/alerts/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channel, min_level, enabled })
        });
        if (!res.ok) {
            const err = await res.json();
            alert(err.error || 'Failed to save alert settings');
            return;
        }
        const data = await res.json().catch(() => ({}));
        updateAlertStatusBadge(enabled);
        showAlertFlash(data.status === 'saved' ? 'Saved' : 'Done');
    } catch (err) {
        console.log('failed to save alert settings', err);
    }
}

// small self-dismissing confirmation next to the Save button - no modal,
// no alert(), just a quiet fade in/out so it doesn't demand attention
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
    // debounce so we're not hitting the db on every keystroke, only once
    // typing pauses, this now searches every log in the db, not just
    // whatever page happens to be loaded client-side
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

// IMPORTANT: .json-line has `white-space: pre-wrap` in the CSS so long
// values wrap instead of overflowing. That means any newline/indentation
// embedded in the HTML string we build here gets rendered literally by the
// browser. Every string returned for a single .json-line MUST therefore be
// built as one unbroken line with no template-literal line breaks inside it.
// Only the .json-children wrapper (indentation via margin-left) should ever
// introduce structural nesting/whitespace.
//
// `term` is the active search term, threaded through recursively so string
// values anywhere in the tree get the same highlighting the collapsed row
// preview already had - previously this only escaped values and never knew
// what was searched for, so a match buried inside an expanded JSON payload
// was invisible even though it's the reason that row matched at all.
function renderJsonNode(value, keyLabel, depth, term) {
    const keyHtml = keyLabel !== null
        ? `<span class="json-key">"${escapeHtml(keyLabel)}"</span>: `
        : '';

    if (value === null) {
        return `<div class="json-line">${keyHtml}<span class="json-null">null</span></div>`;
    }
    if (typeof value === 'boolean') {
        return `<div class="json-line">${keyHtml}<span class="json-bool">${value}</span></div>`;
    }
    if (typeof value === 'number') {
        return `<div class="json-line">${keyHtml}<span class="json-number">${value}</span></div>`;
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

function renderDetailContent(text, term) {
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
            // copy the indented version, not the single-line raw string,
            // that's what's actually useful to paste elsewhere
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

    // keep the client-side cache capped to one page's worth while logs
    // stream in live. Without this, allRequests grows unbounded past
    // pageLimit and page 1 silently shows more than 100 rows until a
    // refresh resets it. The row that rolls off here isn't lost — it's
    // still on the server, reachable by paging forward with Next.
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
            // an existing row dropped off the bottom of the page, so the
            // cheap "just prepend one row" path is no longer accurate -
            // re-render fully from the (now-capped) array instead
            applyFilters();
        } else {
            renderNewRequest(req);
        }
    } else {
        pendingNewCount++;
        updateLiveTailUI();
    }
}

// beacon briefly flips to alert red when an error just came through, so
// the header status dot means something instead of just pulsing forever
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

// wraps every case-insensitive occurrence of the search term in <mark>,
// escaping first so we never inject the raw (unescaped) search text
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
        <div class="request-item" data-id="${req.id}" data-level="${level}">
            <div class="request-header" onclick="toggleDetails(this)">
                ${containerBadge}
                <span class="level level-${level}">${level}</span>
                <span class="message">${highlightMatch(messageRaw, term)}</span>
                <span class="timestamp">${timeLabel}</span>
            </div>
            <div class="request-details ${expandedSet.has(req.id) ? 'open' : ''}">
                ${req.logger ? `<div class="detail-section"><div class="detail-label-row"><span class="detail-label">Logger</span><button class="copy-btn" onclick="copyDetailField('${req.id}', 'logger', this)">Copy</button></div><div class="detail-content"><pre>${highlightMatch(req.logger, term)}</pre></div></div>` : ''}
                ${req.raw ? `<div class="detail-section"><div class="detail-label-row"><span class="detail-label">Raw Line</span><button class="copy-btn" onclick="copyDetailField('${req.id}', 'raw', this)">Copy</button></div><div class="detail-content">${renderDetailContent(req.raw, term)}</div></div>` : ''}
            </div>
        </div>`;
}

function toggleDetails(header) {
    const id = header.parentElement.dataset.id;
    const details = header.nextElementSibling;
    details.classList.toggle('open');
    if (details.classList.contains('open')) expandedSet.add(id);
    else expandedSet.delete(id);
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
    const payload = filtered.map(({ id, ...rest }) => rest); // drop the client-only synthetic id
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

    // knownContainers is populated from /api/containers plus anything new
    // seen live - the same source the Container filter dropdown uses, so
    // this number now always matches what that dropdown lists. Previously
    // this counted only containers present in the currently loaded page,
    // which disagreed with the dropdown whenever the page was filtered
    // or just didn't happen to include every container.
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
        // no stored session at all - go straight to login, no fetch
        // needed so there's nothing to wait on
        if (loadingEl) loadingEl.classList.add('hidden');
        LOGIN_PAGE.classList.remove('hidden');
        return;
    }

    try {
        const res = await fetch('/api/me');
        if (!res.ok) {
            // cookie expired or was never valid, stale localStorage flag
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