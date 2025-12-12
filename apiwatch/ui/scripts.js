const DASHBOARD = document.getElementById('dashboard');
const LOGIN_PAGE = document.getElementById('login-page');
const ERROR_EL = document.getElementById('login-error');
const requestsEl = document.getElementById('requests');
const emptyStateEl = document.getElementById('empty-state');
const countEl = document.getElementById('request-count');

let expandedSet = new Set();
let allRequests = [];
let ws;
let stats = {
    total: 0,
    success: 0,
    error: 0,
    durations: [],
    history: []
};
let all_requests_count = 0;
let currentPage = 1;
let pageLimit = 100;
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
    stats = { total: 0, success: 0, error: 0, durations: [], history: [] };

    // Reset displayed counts
    countEl.textContent = `${all_requests_count} requests`;
    document.getElementById('total-requests').textContent = all_requests_count;

    // Clear request list
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

// ---------------- Pagination ----------------
async function fetchPage(page) {
    if (loadingPage) return;
    loadingPage = true;

    const res = await fetch(`/api/history?page=${page}&limit=${pageLimit}`);
    const result = await res.json();

    currentPage = result.page;
    all_requests_count = result.data.total;
    allRequests = result.data.results;

    // Recalculate stats from allRequests
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

    // Update stats incrementally
    stats.total++;
    const statusCode = parseInt(req.status_code);
    if (statusCode >= 200 && statusCode < 400) stats.success++;
    else stats.error++;

    if (req.duration_ms) {
        stats.durations.push(req.duration_ms);
        if (stats.durations.length > 20) stats.durations.shift();
    }

    stats.history.push({ time: Date.now(), success: statusCode < 400 });
    if (stats.history.length > 20) stats.history.shift();

    updateStats();

    if (!skipRender) renderNewRequest(req);
}

function recalcStats() {
    stats.total = allRequests.length;
    stats.success = allRequests.filter(r => parseInt(r.status_code) >= 200 && parseInt(r.status_code) < 400).length;
    stats.error = stats.total - stats.success;
    stats.durations = allRequests.filter(r => r.duration_ms).map(r => r.duration_ms);
    stats.history = allRequests.slice(-20).map(r => ({ time: new Date(r.timestamp).getTime(), success: parseInt(r.status_code) < 400 }));
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
    const serviceBadge = req.service ? `<span class="service-badge">${req.service}</span>` : '';
    const statusClass = req.status_code < 300 ? 'success' : req.status_code < 400 ? 'redirect' : 'error';

    return `
        <div class="request-item" data-id="${req.id}">
            <div class="request-header" onclick="toggleDetails(this)">
                ${serviceBadge}
                <span class="method ${req.method}">${req.method}</span>
                <span class="path">${req.path}</span>
                <span class="status-code ${statusClass}">${req.status_code || '---'}</span>
                <span class="duration">${req.duration_ms ? req.duration_ms + 'ms' : '---'}</span>
                <span class="timestamp">${new Date(req.timestamp).toLocaleTimeString()} UTC</span>
            </div>
            <div class="request-details ${expandedSet.has(req.id) ? 'open' : ''}">
                ${req.query_params && Object.keys(req.query_params).length ? `<div class="detail-section"><div class="detail-label">Query Parameters</div><div class="detail-content"><pre>${JSON.stringify(req.query_params, null, 2)}</pre></div></div>` : ''}
                ${req.request_data ? `<div class="detail-section"><div class="detail-label">Request Body</div><div class="detail-content"><pre>${JSON.stringify(req.request_data, null, 2)}</pre></div></div>` : ''}
                ${req.response_data ? `<div class="detail-section"><div class="detail-label">Response</div><div class="detail-content"><pre>${typeof req.response_data === 'object' ? JSON.stringify(req.response_data, null, 2) : req.response_data}</pre></div></div>` : ''}
                ${req.headers && Object.keys(req.headers).length ? `<div class="detail-section"><div class="detail-label">Headers</div><div class="detail-content"><pre>${JSON.stringify(req.headers, null, 2)}</pre></div></div>` : ''}
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
    const statusFilter = document.getElementById('filter-status').value;
    const methodFilter = document.getElementById('filter-method').value;

    let filtered = allRequests.filter(req => {
        const statusCode = parseInt(req.status_code);
        let statusMatch = true;
        if (statusFilter !== 'all') {
            const filterRange = parseInt(statusFilter.substring(0, 1));
            statusMatch = Math.floor(statusCode / 100) === filterRange;
        }
        const methodMatch = methodFilter === 'all' || req.method === methodFilter;
        return statusMatch && methodMatch;
    });

    renderRequests(filtered);
}

function applySort() {
    applyFilters();
}

function renderRequests(requests) {
    const sortBy = document.getElementById('sort-by').value;

    let sorted = [...requests];
    switch(sortBy) {
        case 'time-asc': sorted.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp)); break;
        case 'time-desc': sorted.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)); break;
        case 'duration-asc': sorted.sort((a, b) => (a.duration_ms || 0) - (b.duration_ms || 0)); break;
        case 'duration-desc': sorted.sort((a, b) => (b.duration_ms || 0) - (a.duration_ms || 0)); break;
        case 'status-asc': sorted.sort((a, b) => (a.status_code || 0) - (b.status_code || 0)); break;
        case 'status-desc': sorted.sort((a, b) => (b.status_code || 0) - (a.status_code || 0)); break;
    }

    requestsEl.innerHTML = sorted.map(req => renderRequest(req)).join('');
    emptyStateEl.style.display = sorted.length === 0 && allRequests.length > 0 ? 'block' : 'none';
}

// ---------------- Stats & Charts ----------------
function updateStats() {
    countEl.textContent = `${all_requests_count} request${all_requests_count !== 1 ? 's' : ''}`;
    document.getElementById('total-requests').textContent = all_requests_count;

    const successRate = stats.total > 0 ? Math.round((stats.success / stats.total) * 100) : 0;
    document.getElementById('success-rate').textContent = successRate + '%';

    const avgTime = stats.durations.length > 0 
        ? (stats.durations.reduce((a, b) => a + b, 0) / stats.durations.length).toFixed(2)
        : '0.00';
    document.getElementById('avg-time').textContent = avgTime + 'ms';

    updateCharts(); 
}


function updateCharts() {
    const chartTotal = document.getElementById('chart-total');
    chartTotal.innerHTML = stats.history.slice(-10).map((h, i) => `<div class="chart-bar ${i === stats.history.length - 1 ? 'active' : ''}" style="height: ${20 + (i * 2)}px"></div>`).join('');

    const chartSuccess = document.getElementById('chart-success');
    chartSuccess.innerHTML = stats.history.slice(-10).map(h => `<div class="chart-bar ${h.success ? 'active' : ''}" style="height: ${h.success ? 40 : 15}px; opacity: ${h.success ? 1 : 0.3}"></div>`).join('');

    const chartTime = document.getElementById('chart-time');
    const maxDuration = Math.max(...stats.durations.slice(-10), 1);
    chartTime.innerHTML = stats.durations.slice(-10).map(d => `<div class="chart-bar" style="height: ${(d / maxDuration) * 40}px"></div>`).join('');
}

// ---------------- Clear ----------------
async function clearRequests() {
    if (confirm('Clear all requests?')) {
        const res = await fetch('/api/clear', { method: 'POST', headers: { 'Content-Type': 'application/json' }});
        await res.json();

        allRequests = [];
        all_requests_count = 0;
        stats = { total: 0, success: 0, error: 0, durations: [], history: [] };

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
    fetchPage(1);
    initWebSocket();
}
