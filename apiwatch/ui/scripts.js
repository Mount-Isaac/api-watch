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

// Theme management
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

// Login handling
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
            body: JSON.stringify({ username:username, password:password })
        });
        const auth_response = await res.json();

        if (auth_response.message === "success") {
            localStorage.setItem('auth', 'true');
            ERROR_EL.classList.add('hidden');
            usernameInput.classList.remove('error');
            passwordInput.classList.remove('error');
            LOGIN_PAGE.classList.add('hidden');
            DASHBOARD.classList.remove('hidden');
            initWebSocket();
        } else {
            ERROR_EL.textContent = 'Invalid credentials';
            ERROR_EL.classList.remove('hidden');
            usernameInput.classList.add('error');
            passwordInput.classList.add('error');
        }
    } catch (err) {
        console.log(err)
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
    stats = { total: 0, success: 0, error: 0, durations: [], history: [] };
}

function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.hostname}:${window.location.port}/ws`);
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'history') {
            data.data.forEach(req => addRequest(req, true));
            applyFilters();
        } else {
            addRequest(data);
        }
    };
    
    ws.onclose = () => console.log('WebSocket disconnected');
}

function renderNewRequest(req) {
    console.log(`new request: ${req}`)
    const sortBy = document.getElementById('sort-by').value;

    // We only add new request to DOM if sorting is "time-desc"
    // Otherwise applyFilters() (rare)
    if (sortBy !== 'time-desc') {
        applyFilters();
        return;
    }

    // Insert at the top WITHOUT clearing previous requests
    requestsEl.insertAdjacentHTML('afterbegin', renderRequest(req));
}

function toggleDetails(header) {
    const id = header.parentElement.dataset.id;
    const details = header.nextElementSibling;

    details.classList.toggle('open');

    if (details.classList.contains('open')) {
        expandedSet.add(id);
    } else {
        expandedSet.delete(id);
    }
}

function addRequest(req, skipRender = false) {
    emptyStateEl.style.display = 'none';
    
    req.id = Date.now() + Math.random();
    allRequests.unshift(req);
    
    // Update stats
    stats.total++;
    const statusCode = parseInt(req.status_code);
    if (statusCode >= 200 && statusCode < 400) {
        stats.success++;
    } else {
        stats.error++;
    }
    
    if (req.duration_ms) {
        stats.durations.push(req.duration_ms);
        if (stats.durations.length > 20) stats.durations.shift();
    }
    
    stats.history.push({ 
        time: Date.now(), 
        success: statusCode < 400 
    });
    if (stats.history.length > 20) stats.history.shift();
    
    updateStats();
    
    if (!skipRender) {
        renderNewRequest(req)
        // applyFilters();
    }
}

function updateStats() {
    countEl.textContent = `${stats.total} request${stats.total !== 1 ? 's' : ''}`;
    document.getElementById('total-requests').textContent = stats.total;
    
    const successRate = stats.total > 0 
        ? Math.round((stats.success / stats.total) * 100) 
        : 100;
    document.getElementById('success-rate').textContent = successRate + '%';
    
    const avgTime = stats.durations.length > 0
        ? Math.round(stats.durations.reduce((a, b) => a + b, 0) / stats.durations.length)
        : 0;
    document.getElementById('avg-time').textContent = avgTime + 'ms';
    
    updateCharts();
}

function updateCharts() {
    // Total requests chart
    const chartTotal = document.getElementById('chart-total');
    chartTotal.innerHTML = stats.history.slice(-10).map((h, i) => 
        `<div class="chart-bar ${i === stats.history.length - 1 ? 'active' : ''}" style="height: ${20 + (i * 2)}px"></div>`
    ).join('');
    
    // Success rate chart
    const chartSuccess = document.getElementById('chart-success');
    chartSuccess.innerHTML = stats.history.slice(-10).map((h, i) => 
        `<div class="chart-bar ${h.success ? 'active' : ''}" style="height: ${h.success ? 40 : 15}px; opacity: ${h.success ? 1 : 0.3}"></div>`
    ).join('');
    
    // Response time chart
    const chartTime = document.getElementById('chart-time');
    const maxDuration = Math.max(...stats.durations.slice(-10), 1);
    chartTime.innerHTML = stats.durations.slice(-10).map((d, i) => 
        `<div class="chart-bar ${i === stats.durations.length - 1 ? 'active' : ''}" style="height: ${(d / maxDuration) * 40}px"></div>`
    ).join('');
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
                <span class="status-code ${statusClass}">
                    ${req.status_code || '---'}
                </span>
                <span class="duration">${req.duration_ms ? req.duration_ms + 'ms' : '---'}</span>
                <span class="timestamp">${new Date(req.timestamp).toLocaleTimeString()} UTC</span>
            </div>

            <div class="request-details ${expandedSet.has(req.id) ? 'open' : ''}">
                ${req.query_params && Object.keys(req.query_params).length ? `
                    <div class="detail-section">
                        <div class="detail-label">Query Parameters</div>
                        <div class="detail-content"><pre>${JSON.stringify(req.query_params, null, 2)}</pre></div>
                    </div>` : ''}
                ${req.request_data ? `
                    <div class="detail-section">
                        <div class="detail-label">Request Body</div>
                        <div class="detail-content"><pre>${JSON.stringify(req.request_data, null, 2)}</pre></div>
                    </div>` : ''}
                ${req.response_data ? `
                    <div class="detail-section">
                        <div class="detail-label">Response</div>
                        <div class="detail-content"><pre>${typeof req.response_data === 'object' 
                            ? JSON.stringify(req.response_data, null, 2) 
                            : req.response_data}</pre></div>
                    </div>` : ''}
                ${req.headers && Object.keys(req.headers).length ? `
                    <div class="detail-section">
                        <div class="detail-label">Headers</div>
                        <div class="detail-content"><pre>${JSON.stringify(req.headers, null, 2)}</pre></div>
                    </div>` : ''}
            </div>
        </div>`;
}

function applyFilters() {
    const statusFilter = document.getElementById('filter-status').value;
    const methodFilter = document.getElementById('filter-method').value;
    
    let filtered = allRequests.filter(req => {
        const statusCode = parseInt(req.status_code);
        let statusMatch = true;
        
        if (statusFilter !== 'all') {
            const filterRange = parseInt(statusFilter.substring(0, 1));
            const statusRange = Math.floor(statusCode / 100);
            statusMatch = statusRange === filterRange;
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
        case 'time-asc':
            sorted.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
            break;
        case 'time-desc':
            sorted.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
            break;
        case 'duration-asc':
            sorted.sort((a, b) => (a.duration_ms || 0) - (b.duration_ms || 0));
            break;
        case 'duration-desc':
            sorted.sort((a, b) => (b.duration_ms || 0) - (a.duration_ms || 0));
            break;
        case 'status-asc':
            sorted.sort((a, b) => (a.status_code || 0) - (b.status_code || 0));
            break;
        case 'status-desc':
            sorted.sort((a, b) => (b.status_code || 0) - (a.status_code || 0));
            break;
    }
    
    requestsEl.innerHTML = sorted.map(req => renderRequest(req)).join('');
    emptyStateEl.style.display = sorted.length === 0 && allRequests.length > 0 ? 'block' : 'none';
}

async function clearRequests() {
    if (confirm('Clear all requests?')) {

        const res = await fetch('/api/clear', {
            method: 'POST',                
            headers: { 'Content-Type': 'application/json' }
        });

        await res.json();
        allRequests = [];
        stats = { total: 0, success: 0, error: 0, durations: [], history: [] };
        
        requestsEl.innerHTML = '';
        emptyStateEl.style.display = 'block';
        updateStats();
    }
}

function toggleDetails(header) {
    header.nextElementSibling.classList.toggle('open');
}

// Initialize
loadTheme();

if (localStorage.getItem('auth') === 'true') {
    LOGIN_PAGE.classList.add('hidden');
    DASHBOARD.classList.remove('hidden');
    initWebSocket();
}