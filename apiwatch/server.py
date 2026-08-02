"""
Smart server that auto-starts dashboard if needed
Checks if dashboard is running, starts if not
"""
import json
import os
from pathlib import Path
import threading
import asyncio
import socket
from aiohttp import web
from collections import deque
from .ui import template
from utils.db_sqlite import AsyncDB
from ._docker.docker_collector import DockerCollector



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
    
    async def broadcast(self, data: dict):
        """Push a record to every connected dashboard websocket client."""
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

        is_match = (
            data.get('username') == self.username and 
            data.get('password') == self.password
        )
        auth_response = { 'message': 'success' } if is_match else { 'message': 'Invalid credentials.' }
        
        return web.json_response(auth_response)

    async def api_history_handler(self, request):
        page = int(request.query.get("page", 1))
        limit = int(request.query.get("limit", 20))

        logs = await self.db.get_logs_paginated(page, limit)
        return web.json_response({
            "page": page,
            "limit": limit,
            "data": logs
        })

    async def api_containers_handler(self, request):
        """
        Distinct container names seen so far, including ones from
        containers that have since stopped, their log rows persist so
        the name stays filterable in the dashboard.
        """
        containers = await self.db.get_distinct_containers()
        return web.json_response({"containers": containers})
    
    async def api_clear_handler(self, request):
        """Clear history"""
        self.history = await self.db.delete_all_logs()
        return web.json_response({"status": "cleared"})
    
    async def start(self):
        """Start the dashboard server"""
        self.app = web.Application()
        await self.db.init()
        self.history = await self.db.get_all_logs()

        BASE_DIR = Path(__file__).parent / 'ui'
        self.app.router.add_static('/static', path=BASE_DIR, name='static')
        print(f'base dir:{BASE_DIR}')
        self.app.router.add_get('/', self.dashboard_handler)
        self.app.router.add_get('/ws', self.websocket_handler)
        self.app.router.add_post('/auth', self.get_auth_credentials)
        self.app.router.add_get('/api/history', self.api_history_handler)
        self.app.router.add_get('/api/containers', self.api_containers_handler)
        self.app.router.add_post('/api/clear', self.api_clear_handler)
        
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        
        # db is initialized above, collector only starts once that's done
        await self.collector.start()
        
        print(f"[ApiWatchdog] Dashboard started at http://{self.host}:{self.port}")
    
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


# For standalone mode
async def run_standalone(host='0.0.0.0', port=22222, username='admin', password='admin'):
    """Run dashboard as standalone server"""
    server = DashboardServer(host=host, port=port, username=username, password=password)
    await server.start()
    
    print("=" * 60)
    print("ApiWatchdog Dashboard Server (Standalone Mode)")
    print("=" * 60)
    print(f"Dashboard: http://{host}:{port}")
    print(f"WebSocket: ws://{host}:{port}/ws")
    print(f"Docker collector: watching containers ({'all' if server.collector.watch_all else 'labelled'})")
    print("=" * 60)
    print("Waiting for container logs...")
    print("=" * 60, end="\n\n")
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\n[ApiWatchdog] Shutting down...")
        await server.stop()