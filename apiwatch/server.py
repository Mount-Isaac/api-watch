"""
Smart server that auto-starts dashboard if needed
Checks if dashboard is running, starts if not
"""
import json
import os
import hmac
import secrets
import time
from pathlib import Path
import threading
import asyncio
import socket
from aiohttp import web
from collections import deque
from .ui import template
from utils.db_sqlite import AsyncDB
from .docker_collector import DockerCollector
from .alerting import AlertManager

SESSION_COOKIE_NAME = 'apiwatch_session'
SESSION_TTL_SECONDS = int(os.getenv('APIWATCH_SESSION_TTL_SECONDS', str(24 * 3600)))
# paths reachable without a valid session, everything else is gated
PUBLIC_PATHS = {'/', '/auth'}
PUBLIC_PREFIXES = ('/static/',)



# Global state
_dashboard_server = None
_server_lock = threading.Lock()


class DashboardServer:
    """Centralized dashboard server"""
    
    def __init__(self, host='0.0.0.0', port=22222, max_history=1000, username = "admin", password="admin"):
        self.host = host
        self.port = port
        self.max_history = max_history
        self.username=username
        self.password=password
        self.history = []
        self.ws_clients = set()
        self.app = None
        self.runner = None
        db_path = Path(__file__).parent.parent / 'data' / 'apiwatch.db'
        self.db = AsyncDB(db_path)
        # DockerCollector never touches db.init() itself, it just uses
        # this same connection once we've initialized it in start()
        self.collector = DockerCollector(db=self.db, broadcast=self.broadcast)
        self.alerts = AlertManager(db=self.db)
    
    @web.middleware
    async def auth_middleware(self, request, handler):
        path = request.path
        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            return await handler(request)

        token = request.cookies.get(SESSION_COOKIE_NAME)
        if not await self.db.session_valid(token):
            raise web.HTTPUnauthorized(
                text=json.dumps({'error': 'unauthorized'}),
                content_type='application/json'
            )
        return await handler(request)

    async def broadcast(self, data: dict):
        """Push a record to every connected dashboard websocket client."""
        # fire-and-forget: alerting must never slow down or block the
        # live dashboard stream, a slow Slack/Gmail call shouldn't add
        # latency to what every connected browser sees
        asyncio.create_task(self.alerts.maybe_alert(data))

        if not self.ws_clients:
            return
        message = json.dumps(data)
        dead_clients = set()
        for ws in self.ws_clients:
            try:
                await ws.send_str(message)
            except Exception:
                dead_clients.add(ws)
        self.ws_clients -= dead_clients

    async def websocket_handler(self, request):
        """Handle WebSocket connections from browsers"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        self.ws_clients.add(ws)
        
        # Send history on connect
        # if self.history:
        #     await ws.send_str(json.dumps({
        #         "type": "history", 
        #         "data": await self.db.get_all_logs()
        #     }))
        
        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.ERROR:
                    print(f'[ApiWatchdog] WebSocket error: {ws.exception()}')
        finally:
            self.ws_clients.discard(ws)
        
        return ws
    
    async def dashboard_handler(self, request):
        """Serve the dashboard HTML"""
        return web.Response(text=template(), content_type='text/html')
    
    async def get_auth_credentials(self, request, **kwargs):
        data = await request.json()

        submitted_user = data.get('username', '')
        submitted_pass = data.get('password', '')
        # timing-safe comparison, a plain == leaks how many leading
        # characters matched via response time, small thing but free
        # to do right
        is_match = (
            hmac.compare_digest(submitted_user, self.username) and
            hmac.compare_digest(submitted_pass, self.password)
        )

        if not is_match:
            return web.json_response({'message': 'Invalid credentials.'}, status=401)

        token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + SESSION_TTL_SECONDS
        await self.db.create_session(token, expires_at)

        resp = web.json_response({'message': 'success'})
        resp.set_cookie(
            SESSION_COOKIE_NAME, token,
            httponly=True, samesite='Strict', max_age=SESSION_TTL_SECONDS
        )
        return resp

    async def api_logout_handler(self, request):
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if token:
            await self.db.delete_session(token)
        resp = web.json_response({'status': 'logged out'})
        resp.del_cookie(SESSION_COOKIE_NAME)
        return resp

    async def api_me_handler(self, request):
        """Lightweight check the frontend calls on load, cookie already
        got validated by auth_middleware just to reach this handler, so
        getting here at all means the session is good."""
        return web.json_response({'authenticated': True})

    async def _session_cleanup_loop(self):
        while True:
            await asyncio.sleep(3600)
            try:
                removed = await self.db.cleanup_expired_sessions()
                if removed:
                    print(f'[ApiWatchdog] cleaned up {removed} expired sessions')
            except Exception as exc:
                print(f'[ApiWatchdog] session cleanup failed: {exc}')

    async def api_history_handler(self, request):
        page = int(request.query.get("page", 1))
        limit = int(request.query.get("limit", 20))
        search = request.query.get("search", "").strip() or None

        logs = await self.db.get_logs_paginated(page, limit, search=search)
        return web.json_response({
            "page": page,
            "limit": limit,
            "data": logs
        })

    async def api_containers_handler(self, request):
        """
        Union of two sources: containers currently running (queried live
        from the collector, so one only emitting levels below an
        APIWATCH_LOG_LEVELS/alert threshold still shows up immediately,
        instead of waiting for a row to actually land in the db), and
        containers with historical rows in the db (so one that's since
        stopped stays filterable by its past logs). Deduped via a set,
        converted back to a sorted list before returning since a raw
        Python set isn't JSON-serializable, web.json_response would
        throw the moment there was ever an actual overlap to dedupe.
        """
        containers = await self.collector._list_target_containers()
        # _container_info does a `container.show()` call each, run them
        # concurrently instead of one at a time in a comprehension
        info_results = await asyncio.gather(
            *[self.collector._container_info(c) for c in containers]
        )
        active_names = {name for name, _ in info_results}

        db_names = set(await self.db.get_distinct_containers())

        all_names = sorted(active_names | db_names)
        return web.json_response({"containers": all_names})

    async def api_stats_handler(self, request):
        """Per-container summary + level breakdown, across all logs."""
        containers = await self.db.get_container_stats()
        levels = await self.db.get_level_counts()
        return web.json_response({"containers": containers, "levels": levels})

    async def api_alerts_availability_handler(self, request):
        """
        Which channels actually have credentials configured via env
        vars, the UI uses this to grey out / warn on a channel before
        the user tries to enable something that can't actually send.
        """
        return web.json_response(self.alerts.availability())

    async def api_alerts_settings_get_handler(self, request):
        settings = await self.db.get_alert_settings()
        if not settings:
            return web.json_response({'slack_enabled': False, 'gmail_enabled': False, 'min_level': 'ERROR'})
        return web.json_response({
            'slack_enabled': bool(settings.get('slack_enabled')),
            'gmail_enabled': bool(settings.get('gmail_enabled')),
            'min_level': settings.get('min_level', 'ERROR'),
        })

    async def api_alerts_settings_post_handler(self, request):
        data = await request.json()
        slack_enabled = bool(data.get('slack_enabled'))
        gmail_enabled = bool(data.get('gmail_enabled'))
        min_level = (data.get('min_level') or 'ERROR').upper()

        avail = self.alerts.availability()
        if slack_enabled and not avail.get('slack'):
            return web.json_response({'error': 'slack is not configured, missing required env vars'}, status=400)
        if gmail_enabled and not avail.get('gmail'):
            return web.json_response({'error': 'gmail is not configured, missing required env vars'}, status=400)

        await self.db.save_alert_settings(slack_enabled, gmail_enabled, min_level)
        return web.json_response({'status': 'saved'})
    
    async def api_clear_handler(self, request):
        """Clear history"""
        self.history = await self.db.delete_all_logs()
        return web.json_response({"status": "cleared"})
    
    async def start(self):
        """Start the dashboard server"""
        self.app = web.Application(middlewares=[self.auth_middleware])
        await self.db.init()
        self.history = await self.db.get_all_logs()

        BASE_DIR = Path(__file__).parent / 'ui'
        self.app.router.add_static('/static', path=BASE_DIR, name='static')
        print(f'base dir:{BASE_DIR}')
        self.app.router.add_get('/', self.dashboard_handler)
        self.app.router.add_get('/ws', self.websocket_handler)
        self.app.router.add_post('/auth', self.get_auth_credentials)
        self.app.router.add_post('/api/logout', self.api_logout_handler)
        self.app.router.add_get('/api/me', self.api_me_handler)
        self.app.router.add_get('/api/history', self.api_history_handler)
        self.app.router.add_get('/api/containers', self.api_containers_handler)
        self.app.router.add_get('/api/stats', self.api_stats_handler)
        self.app.router.add_get('/api/alerts/availability', self.api_alerts_availability_handler)
        self.app.router.add_get('/api/alerts/settings', self.api_alerts_settings_get_handler)
        self.app.router.add_post('/api/alerts/settings', self.api_alerts_settings_post_handler)
        self.app.router.add_post('/api/clear', self.api_clear_handler)
        
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        
        # db is initialized above, collector only starts once that's done
        await self.collector.start()
        asyncio.create_task(self._session_cleanup_loop())
        
    async def stop(self):
        """Stop the server"""
        await self.collector.stop()
        if self.runner:
            await self.runner.cleanup()


def is_dashboard_running(host='localhost', port=22222):
    """Check if dashboard is already running"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False


def start_dashboard_server(host='0.0.0.0', port=22222, username='admin', password='admin'):
    """
    Start dashboard server (auto-start if not running)

    Works like RabbitMQ - first app starts it, others connect
    """
    global _dashboard_server, _server_lock
    
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        return None
    
    with _server_lock:
        if _dashboard_server is not None:
            return None
        
        if is_dashboard_running(host, port):
            print(f"[ApiWatchdog] Dashboard already running at http://{host}:{port}")
            print(f"[ApiWatchdog] Connecting to existing dashboard...")
            _dashboard_server = 'external'
            return None
        
        _dashboard_server = 'starting'
        
        def run_server():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            server = DashboardServer(host=host, port=port, username=username, password=password)
            loop.run_until_complete(server.start())
            loop.run_forever()
        
        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        
        import time
        time.sleep(0.5)
        
        return thread

async def run_standalone(host='0.0.0.0', port=22222, username='admin', password='admin'):
    """Run dashboard as standalone server"""
    server = DashboardServer(host=host, port=port, username=username, password=password)
    await server.start()


    from textwrap import shorten

    width = 72
    line = "═" * width
    version = os.getenv("version_number", "2.0.0")

    print(f"\n╔{line}╗")
    print(f"║{f'api-watch v{version} started':^{width}}║")
    print(f"╠{line}╣")
    print(f"║ Dashboard        : http://{host}:{port}".ljust(width + 1) + "║")
    print(f"║ WebSocket        : ws://{host}:{port}/ws".ljust(width + 1) + "║")
    print(
        f"║ Docker Collector : {'Watching ALL containers' if server.collector.watch_all else 'Watching labelled containers'}"
        .ljust(width + 1)
        + "║"
    )
    print(f"╠{line}╣")
    print(f"║ {'Waiting for container logs...':<{width-1}}║")
    print(f"╚{line}╝\n")

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\n[ApiWatchdog] Shutting down...")
        await server.stop()