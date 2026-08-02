const DASHBOARD = document.getElementById('dashboard');
const LOGIN_PAGE = document.getElementById('login-page');
const ERROR_EL = document.getElementById('login-error');
const requestsEl = document.getElementById('requests');
const emptyStateEl = document.getElementById('empty-state');
const countEl = document.getElementById('request-count');
const containerFilterEl = document.getElementById('filter-container');

const LEVEL_RANK = { CRITICAL: 0, ERROR: 1, WARNING: 2, INFO: 3, DEBUG: 4, UNKNOWN: 5 };
const ERROR_LEVELS = new Set(['CRITICAL', 'ERROR']);

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
let pageLimit = 10;
let loadingPage = false;

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

function logout() {
    localStorage.removeItem('auth');
    DASHBOARD.classList.add('hidden');
    LOGIN_PAGE.classList.remove('hidden');

    if (ws) ws.close();
    allRequests = [];
    all_requests_count = 0;
    stats = { total: 0, errors: 0, history: [] };
    knownContainers = new Set();

    countEl.textContent = `${all_requests_count} logs`;
    document.getElementById('total-requests').textContent = all_requests_count;

    requestsEl.innerHTML = '';
    emptyStateEl.style.display = 'block';
}

// ---------------- WebSocket ----------------
function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.hostname}:${window.location.port}/ws`);

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        addRequest(data);
    };

    ws.onclose = () => console.log('WebSocket disconnected');
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
}

function noteContainer(name) {
    if (!name || knownContainers.has(name)) return;
    // a new container shows up mid-session, we add it, we never remove
    // one just because it stopped, its past logs are still browsable
    knownContainers.add(name);
    renderContainerOptions();
}

// ---------------- Pagination ----------------
async function fetchPage(page) {
    if (loadingPage) return;
    loadingPage = true;

    const res = await fetch(`/api/history?page=${page}&limit=${pageLimit}`);
    const result = await res.json();

    currentPage = result.page;
    all_requests_count = result.data.total;
    allRequests = result.data.results;

    allRequests.forEach(r => noteContainer(r.container_name));
    recalcStats();

    renderRequests(allRequests);
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

// ---------------- Requests handling ----------------
function addRequest(req, skipRender = false) {
    emptyStateEl.style.display = 'none';

    req.id = Date.now() + Math.random();
    allRequests.unshift(req);
    all_requests_count++;
    noteContainer(req.container_name);

    stats.total++;
    if (ERROR_LEVELS.has(req.level)) stats.errors++;

    stats.history.push({ time: Date.now(), isError: ERROR_LEVELS.has(req.level) });
    if (stats.history.length > 20) stats.history.shift();

    updateStats();

    if (!skipRender) renderNewRequest(req);
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
    if (sortBy !== 'time-desc') {
        applyFilters();
        return;
    }
    requestsEl.insertAdjacentHTML('afterbegin', renderRequest(req));
}

function renderRequest(req) {
    const level = req.level || 'UNKNOWN';
    const containerBadge = req.container_name
        ? `<span class="service-badge">${req.container_name}</span>`
        : '';
    const timestamp = req.timestamp ? new Date(req.timestamp) : null;
    const timeLabel = timestamp && !isNaN(timestamp) ? timestamp.toLocaleTimeString() : '---';

    return `
        <div class="request-item" data-id="${req.id}">
            <div class="request-header" onclick="toggleDetails(this)">
                ${containerBadge}
                <span class="level level-${level}">${level}</span>
                <span class="message">${req.message || req.raw || ''}</span>
                <span class="timestamp">${timeLabel}</span>
            </div>
            <div class="request-details ${expandedSet.has(req.id) ? 'open' : ''}">
                ${req.logger ? `<div class="detail-section"><div class="detail-label">Logger</div><div class="detail-content"><pre>${req.logger}</pre></div></div>` : ''}
                ${req.raw ? `<div class="detail-section"><div class="detail-label">Raw Line</div><div class="detail-content"><pre>${req.raw}</pre></div></div>` : ''}
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
function applyFilters() {
    const levelFilter = document.getElementById('filter-level').value;
    const containerFilter = containerFilterEl.value;

    let filtered = allRequests.filter(req => {
        const levelMatch = levelFilter === 'all' || (req.level || 'UNKNOWN') === levelFilter;
        const containerMatch = containerFilter === 'all' || req.container_name === containerFilter;
        return levelMatch && containerMatch;
    });

    renderRequests(filtered);
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

// ---------------- Stats & Charts ----------------
function updateStats() {
    countEl.textContent = `${all_requests_count} log${all_requests_count !== 1 ? 's' : ''}`;
    document.getElementById('total-requests').textContent = all_requests_count;

    const errorRate = stats.total > 0 ? Math.round((stats.errors / stats.total) * 100) : 0;
    document.getElementById('error-rate').textContent = errorRate + '%';

    // distinct containers within the currently loaded window, this is
    // an approximation of "active", we don't have a live container list
    // to compare against here, only what's shown up in logs so far
    const containersInView = new Set(allRequests.map(r => r.container_name).filter(Boolean));
    document.getElementById('active-containers').textContent = containersInView.size;

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

        requestsEl.innerHTML = '';
        emptyStateEl.style.display = 'block';
        updateStats();
    }
}

// ---------------- Initialize ----------------
loadTheme();

if (localStorage.getItem('auth') === 'true') {
    LOGIN_PAGE.classList.add('hidden');
    DASHBOARD.classList.remove('hidden');
    loadContainers();
    fetchPage(1);
    initWebSocket();
}