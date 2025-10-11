template = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>api-watch - Live Monitor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --bg-primary: #0a0a0a;
            --bg-secondary: #111;
            --bg-tertiary: #1a1a1a;
            --border: #222;
            --border-hover: #333;
            --text-primary: #e0e0e0;
            --text-secondary: #888;
            --text-tertiary: #666;
            --accent: #00ff88;
            --accent-hover: #00cc6a;
            --success-bg: #1a4d2e;
            --success-text: #00ff88;
            --error-bg: #4d1a1a;
            --error-text: #ff4d4d;
            --warning-bg: #4d3a1a;
            --warning-text: #ffb84d;
            --info-bg: #1a3a4d;
            --info-text: #4da6ff;
        }
        
        body.light-mode {
            --bg-primary: #f5f5f5;
            --bg-secondary: #fff;
            --bg-tertiary: #fafafa;
            --border: #e0e0e0;
            --border-hover: #ccc;
            --text-primary: #1a1a1a;
            --text-secondary: #666;
            --text-tertiary: #999;
            --accent: #00cc6a;
            --accent-hover: #00a858;
            --success-bg: #e8f5e9;
            --success-text: #2e7d32;
            --error-bg: #ffebee;
            --error-text: #c62828;
            --warning-bg: #fff3e0;
            --warning-text: #e65100;
            --info-bg: #e3f2fd;
            --info-text: #1565c0;
        }
        
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            font-size: 13px;
            transition: background 0.3s, color 0.3s;
        }
        
        .hidden { display: none !important; }
        
        .header { 
            background: var(--bg-secondary);
            padding: 12px 20px;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        
        .header h1 { 
            font-size: 16px;
            font-weight: 600;
            color: var(--accent);
        }
        
        .header-left {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        
        .header-right {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .status { 
            display: flex;
            gap: 15px;
            align-items: center;
            font-size: 12px;
        }
        
        .status-dot { 
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--accent);
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse { 
            0%, 100% { opacity: 1; } 
            50% { opacity: 0.5; } 
        }
        
        .btn { 
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            color: var(--text-secondary);
            padding: 6px 12px;
            cursor: pointer;
            border-radius: 4px;
            font-size: 12px;
            transition: all 0.2s;
        }
        
        .btn:hover { 
            background: var(--bg-secondary);
            color: var(--text-primary);
            border-color: var(--border-hover);
        }
        
        .btn-icon {
            padding: 6px 10px;
            display: flex;
            align-items: center;
            gap: 5px;
        }
        
        .container { 
            padding: 20px;
            max-width: 1400px;
            margin: 0 auto;
            padding-bottom: 60px;
        }
        
        .controls {
            background: var(--bg-secondary);
            padding: 15px;
            border-radius: 6px;
            border: 1px solid var(--border);
            margin-bottom: 20px;
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            align-items: center;
        }
        
        .control-group {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .control-label {
            font-size: 11px;
            text-transform: uppercase;
            color: var(--text-secondary);
            font-weight: 600;
        }
        
        .select {
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            color: var(--text-primary);
            padding: 6px 10px;
            border-radius: 4px;
            font-size: 12px;
            cursor: pointer;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        
        .stat-card {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 15px;
        }
        
        .stat-label {
            font-size: 11px;
            text-transform: uppercase;
            color: var(--text-secondary);
            font-weight: 600;
            margin-bottom: 8px;
        }
        
        .stat-value {
            font-size: 24px;
            font-weight: 600;
            color: var(--text-primary);
        }
        
        .stat-chart {
            margin-top: 10px;
            height: 40px;
            display: flex;
            align-items: flex-end;
            gap: 2px;
        }
        
        .chart-bar {
            flex: 1;
            background: var(--accent);
            opacity: 0.3;
            border-radius: 2px 2px 0 0;
            transition: all 0.3s;
        }
        
        .chart-bar.active {
            opacity: 1;
        }
        
        .request-item { 
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 6px;
            margin-bottom: 10px;
            overflow: hidden;
            transition: all 0.2s;
        }
        
        .request-item:hover { 
            border-color: var(--border-hover);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }
        
        .request-header { 
            padding: 12px 15px;
            display: flex;
            gap: 12px;
            align-items: center;
            cursor: pointer;
            user-select: none;
        }
        
        .service-badge { 
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 10px;
            background: var(--bg-tertiary);
            color: var(--text-secondary);
            font-weight: 600;
            text-transform: uppercase;
        }
        
        .method { 
            padding: 4px 8px;
            border-radius: 3px;
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
        }
        
        .method.GET { background: var(--success-bg); color: var(--success-text); }
        .method.POST { background: var(--info-bg); color: var(--info-text); }
        .method.PUT { background: var(--warning-bg); color: var(--warning-text); }
        .method.DELETE { background: var(--error-bg); color: var(--error-text); }
        .method.PATCH { background: var(--warning-bg); color: var(--warning-text); }
        
        .path { 
            flex: 1;
            font-weight: 500;
            color: var(--text-primary);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .status-code { 
            padding: 4px 8px;
            border-radius: 3px;
            font-weight: 600;
            font-size: 11px;
        }
        
        .status-code.success { background: var(--success-bg); color: var(--success-text); }
        .status-code.error { background: var(--error-bg); color: var(--error-text); }
        .status-code.redirect { background: var(--info-bg); color: var(--info-text); }
        
        .duration { color: var(--text-secondary); font-size: 11px; }
        .timestamp { color: var(--text-tertiary); font-size: 11px; }
        
        .request-details { 
            padding: 0 15px 15px;
            display: none;
            border-top: 1px solid var(--border);
            background: var(--bg-tertiary);
        }
        
        .request-details.open { display: block; }
        
        .detail-section { margin-top: 12px; }
        
        .detail-label { 
            color: var(--text-secondary);
            font-size: 11px;
            text-transform: uppercase;
            margin-bottom: 6px;
            font-weight: 600;
        }
        
        .detail-content { 
            background: var(--bg-primary);
            padding: 10px;
            border-radius: 4px;
            border: 1px solid var(--border);
            overflow-x: auto;
        }
        
        .detail-content pre { 
            margin: 0;
            color: var(--text-primary);
            white-space: pre-wrap;
            word-wrap: break-word;
            font-size: 12px;
        }
        
        .empty-state { 
            text-align: center;
            padding: 60px 20px;
            color: var(--text-tertiary);
        }
        
        .link { 
            text-decoration: none;
            color: var(--accent);
            transition: opacity 0.2s;
        }
        
        .link:hover {
            opacity: 0.8;
        }
        
        .footer { 
            position: fixed;
            bottom: 0;
            left: 0;
            width: 100%;
            text-align: center;
            background: var(--bg-primary);
            border-top: 1px solid var(--border);
            padding: 8px 0;
            color: var(--text-tertiary);
            font-size: 12px;
        }

        /* Login page */
        .login-container {
            height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            text-align: center;
        }
        
        .login-box {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            padding: 30px 40px;
            border-radius: 8px;
            width: 320px;
        }
        
        .login-box h2 { 
            color: var(--accent);
            font-size: 20px;
            margin-bottom: 20px;
        }
        
        .login-input { 
            width: 100%;
            padding: 10px;
            border: 1px solid var(--border);
            border-radius: 4px;
            margin-bottom: 12px;
            background: var(--bg-tertiary);
            color: var(--text-primary);
            font-size: 14px;
            transition: border-color 0.2s;
        }
        
        .login-input:focus {
            outline: none;
            border-color: var(--accent);
        }
        
        .login-input.error {
            border-color: var(--error-text);
        }
        
        .login-btn { 
            width: 100%;
            background: var(--accent);
            color: #000;
            border: none;
            padding: 10px;
            border-radius: 4px;
            cursor: pointer;
            font-weight: 600;
            transition: background 0.2s;
        }
        
        .login-btn:hover { 
            background: var(--accent-hover);
        }
        
        .login-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        .error { 
            color: var(--error-text);
            font-size: 13px;
            margin-top: 10px;
        }
        
        .theme-toggle {
            width: 40px;
            height: 20px;
            background: var(--bg-tertiary);
            border-radius: 10px;
            position: relative;
            cursor: pointer;
            border: 1px solid var(--border);
        }
        
        .theme-toggle-slider {
            width: 16px;
            height: 16px;
            background: var(--accent);
            border-radius: 50%;
            position: absolute;
            top: 1px;
            left: 2px;
            transition: transform 0.2s;
        }
        
        body.light-mode .theme-toggle-slider {
            transform: translateX(18px);
        }
    </style>
</head>
<body>
    <!-- Login Page -->
    <div id="login-page" class="login-container">
        <div class="login-box">
            <h2>api-watch</h2>
            <form id="login-form" onsubmit="login(event)">
                <input 
                    type="text" 
                    id="username" 
                    class="login-input" 
                    placeholder="Username"
                    required
                    autocomplete="username"
                >
                <input 
                    type="password" 
                    id="password" 
                    class="login-input" 
                    placeholder="Password"
                    required
                    autocomplete="current-password"
                >
                <button type="submit" class="login-btn" id="login-btn">Login</button>
            </form>
            <div id="login-error" class="error hidden">Invalid credentials</div>
        </div>
    </div>

    <!-- Dashboard -->
    <div id="dashboard" class="hidden">
        <div class="header">
            <div class="header-left">
                <h1>api-watch</h1>
                <div class="status">
                    <div class="status-dot"></div>
                    <span>Live</span>
                    <span>|</span>
                    <span id="request-count">0 requests</span>
                </div>
            </div>
            <div class="header-right">
                <div class="theme-toggle" onclick="toggleTheme()">
                    <div class="theme-toggle-slider"></div>
                </div>
                <button class="btn" onclick="clearRequests()">Clear</button>
                <button class="btn" onclick="logout()">Logout</button>
            </div>
        </div>
        
        <div class="container">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Total Requests</div>
                    <div class="stat-value" id="total-requests">0</div>
                    <div class="stat-chart" id="chart-total"></div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Success Rate</div>
                    <div class="stat-value" id="success-rate">100%</div>
                    <div class="stat-chart" id="chart-success"></div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Avg Response Time</div>
                    <div class="stat-value" id="avg-time">0ms</div>
                    <div class="stat-chart" id="chart-time"></div>
                </div>
            </div>
            
            <div class="controls">
                <div class="control-group">
                    <span class="control-label">Status:</span>
                    <select class="select" id="filter-status" onchange="applyFilters()">
                        <option value="all">All</option>
                        <option value="2xx">2xx Success</option>
                        <option value="3xx">3xx Redirect</option>
                        <option value="4xx">4xx Client Error</option>
                        <option value="5xx">5xx Server Error</option>
                    </select>
                </div>
                
                <div class="control-group">
                    <span class="control-label">Method:</span>
                    <select class="select" id="filter-method" onchange="applyFilters()">
                        <option value="all">All</option>
                        <option value="GET">GET</option>
                        <option value="POST">POST</option>
                        <option value="PUT">PUT</option>
                        <option value="DELETE">DELETE</option>
                        <option value="PATCH">PATCH</option>
                    </select>
                </div>
                
                <div class="control-group">
                    <span class="control-label">Sort By:</span>
                    <select class="select" id="sort-by" onchange="applySort()">
                        <option value="time-desc">Newest First</option>
                        <option value="time-asc">Oldest First</option>
                        <option value="duration-desc">Slowest First</option>
                        <option value="duration-asc">Fastest First</option>
                        <option value="status-asc">Status (Low to High)</option>
                        <option value="status-desc">Status (High to Low)</option>
                    </select>
                </div>
            </div>
            
            <div id="requests"></div>
            <div id="empty-state" class="empty-state">
                <p>Waiting for API requests...</p>
            </div>
        </div>

        <div class="footer">
            <span>&copy; Isaac Kyalo</span> |
            <a class="link" href="https://github.com/mount-isaac/api-watch" target="_blank">GitHub</a>
        </div>
    </div>

    <script>
        const DASHBOARD = document.getElementById('dashboard');
        const LOGIN_PAGE = document.getElementById('login-page');
        const ERROR_EL = document.getElementById('login-error');
        const requestsEl = document.getElementById('requests');
        const emptyStateEl = document.getElementById('empty-state');
        const countEl = document.getElementById('request-count');
        
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
                const res = await fetch('/auth');
                const creds = await res.json();

                if (username === creds.username && password === creds.password) {
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
                applyFilters();
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
                        <span class="timestamp">${new Date(req.timestamp).toLocaleTimeString()}</span>
                    </div>
                    <div class="request-details">
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

        function clearRequests() {
            if (confirm('Clear all requests?')) {
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
    </script>
</body>
</html>"""
