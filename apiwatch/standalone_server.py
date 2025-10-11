"""
Standalone Dashboard Server
Run this separately: python -m apiwatchdog.standalone_server

All microservices will connect to this via HTTP POST
"""
import asyncio
import json
from aiohttp import web
from collections import deque


class DashboardServer:
    """Centralized dashboard server - runs as separate process"""
    
    def __init__(self, host='0.0.0.0', port=22222, max_history=1000, username='admin', password='admin'):
        self.host = host
        self.port = port
        self.max_history = max_history
        self.history = deque(maxlen=max_history)
        self.ws_clients = set()
        self.app = None
        self.runner = None
        self.username=username
        self.password=password
    
    async def websocket_handler(self, request):
        """Handle WebSocket connections from browsers"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        self.ws_clients.add(ws)
        print(f"[Dashboard] Browser connected. Total clients: {len(self.ws_clients)}")
        
        # Send history on connect
        if self.history:
            await ws.send_str(json.dumps({
                "type": "history", 
                "data": list(self.history)
            }))
        
        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.ERROR:
                    print(f'[Dashboard] WebSocket error: {ws.exception()}')
        finally:
            self.ws_clients.discard(ws)
            print(f"[Dashboard] Browser disconnected. Total clients: {len(self.ws_clients)}")
        
        return ws
    
    async def dashboard_handler(self, request):
        """Serve the dashboard HTML"""
        from .template_ui import template
        return web.Response(text=template, content_type='text/html')
    
    async def api_publish_handler(self, request):
        """
        Receive request data from microservices and broadcast to browsers
        """
        try:
            data = await request.json()
            
            # Store in history
            self.history.append(data)
            
            # Broadcast to all browser WebSocket clients
            if self.ws_clients:
                message = json.dumps(data)
                dead_clients = set()
                
                for ws in self.ws_clients:
                    try:
                        await ws.send_str(message)
                    except Exception:
                        dead_clients.add(ws)
                
                # Remove dead clients
                self.ws_clients -= dead_clients
            
            return web.json_response({'status': 'ok'})
        except Exception as e:
            print(f"[Dashboard] Publish error: {e}")
            return web.json_response({'status': 'error', 'message': str(e)}, status=500)
    
    async def api_history_handler(self, request):
        """Get all request history"""
        return web.json_response(list(self.history))
    
    async def api_clear_handler(self, request):
        """Clear history"""
        self.history.clear()
        return web.json_response({"status": "cleared"})
    
    async def start(self):
        """Start the dashboard server"""
        self.app = web.Application()
        self.app.router.add_get('/', self.dashboard_handler)
        self.app.router.add_get('/ws', self.websocket_handler)
        self.app.router.add_post('/api/publish', self.api_publish_handler)
        self.app.router.add_get('/api/history', self.api_history_handler)
        self.app.router.add_post('/api/clear', self.api_clear_handler)
        
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        
        print("=" * 60)
        print("🐕 ApiWatchdog Dashboard Server")
        print("=" * 60)
        print(f"📊 Dashboard: http://{self.host}:{self.port}")
        print(f"🔌 WebSocket: ws://{self.host}:{self.port}/ws")
        print(f"📡 Publish Endpoint: http://{self.host}:{self.port}/api/publish")
        print("=" * 60)
        print("Waiting for microservices to connect...")
        print("=" * 60)
    
    async def stop(self):
        """Stop the server"""
        if self.runner:
            await self.runner.cleanup()


async def main():
    """Run the standalone server"""
    server = DashboardServer(host='0.0.0.0', port=22222, username='admin', password='admin')
    await server.start()
    
    # Keep running forever
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\n[Dashboard] Shutting down...")
        await server.stop()


if __name__ == '__main__':
    asyncio.run(main())
