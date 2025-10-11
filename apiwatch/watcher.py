import asyncio
import json
import time
import threading
from collections import deque
from datetime import datetime
from typing import Dict, Any, Optional
from queue import Queue
import traceback


class ApiWatcher:
    """
    Async API monitoring with zero-blocking fire-and-forget pattern.
    Auto-starts dashboard if not running (like RabbitMQ with pika)
    """

    def __init__(self, 
        service_name='main-app', 
        max_history:int=1000, 
        dashboard_host:str='localhost', 
        dashboard_port:int=22222,
        dashboard_username:str='admin',
        dashboard_password:str='admin',
        auto_start_dashboard:bool=True
    ):
        """
        Initialize ApiWatcher
        
        Args:
            service_name: Name of this microservice
            max_history: Maximum number of requests to keep in memory (local cache)
            dashboard_host: Host where dashboard server is running
            dashboard_port: Port where dashboard server is running
            auto_start_dashboard: Auto-start dashboard if not running (default: True)
        """
        self.service_name = service_name
        self.max_history = max_history
        self.dashboard_host = dashboard_host
        self.dashboard_port = dashboard_port
        self.request_queue = Queue()
        self.history = deque(maxlen=max_history)
        self.loop = None
        self.worker_thread = None
        self._running = False

        print(f'[ApiWatchdog] Service: {service_name}')
        
        # Auto-start dashboard if enabled
        if auto_start_dashboard:
            from .server import start_dashboard_server
            start_dashboard_server(
                host=dashboard_host, 
                port=dashboard_port, 
                username=dashboard_username, 
                password=dashboard_password
            )
        
        # Start background worker
        self._start_worker()

    def _start_worker(self):
        """Start background async worker thread"""
        self._running = True
        self.worker_thread = threading.Thread(target=self._run_async_worker, daemon=True)
        self.worker_thread.start()

    def _run_async_worker(self):
        """Run async event loop in background thread"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._process_queue())
    
    async def _process_queue(self):
        """Process request queue asynchronously"""
        while self._running:
            try:
                if not self.request_queue.empty():
                    data = self.request_queue.get_nowait()
                    data['service'] = self.service_name
                    self.history.append(data)

                    # Send to dashboard via HTTP POST
                    await self._send_to_dashboard(data)
                else:
                    await asyncio.sleep(0.01)
            except Exception as e:
                print(f'[ApiWatchdog] Error processing queue: {e}')
                traceback.print_exc()

    async def _send_to_dashboard(self, data: Dict[str, Any]):
        """Send data to dashboard server via HTTP POST"""
        try:
            import aiohttp
            url = f"http://{self.dashboard_host}:{self.dashboard_port}/api/publish"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=1)) as resp:
                    if resp.status != 200:
                        print(f"[ApiWatchdog] Failed to publish: {resp.status}")
        except aiohttp.ClientConnectorError:
            # Dashboard not running - silently fail
            pass
        except Exception:
            # Don't crash the app if dashboard is down
            pass

    def log_request(self,
            method: str,
            path: str,
            status_code: Optional[int] = None,
            request_data: Optional[Dict] = None,
            response_data: Optional[Any] = None,
            duration_ms: Optional[float] = None,
            headers: Optional[Dict] = None,
            query_params: Optional[Dict] = None
        ):
        """Fire-and-forget request logging (non-blocking)"""
        log_entry = {
            "id": f"{int(time.time() * 1000)}",
            "timestamp": datetime.utcnow().isoformat(),
            "method": method,
            "path": path,
            "status_code": status_code,
            "request_data": request_data,
            "response_data": response_data,
            "duration_ms": duration_ms,
            "headers": headers,
            "query_params": query_params
        }

        try:
            self.request_queue.put_nowait(log_entry)
        except Exception as e:
            print(f'[ApiWatchdog] Failed to queue request: {e}')

    def get_history(self):
        """Get local cached requests"""
        return list(self.history)

    def clear_history(self):
        """Clear local request history"""
        self.history.clear()

    def shutdown(self):
        """Gracefully shutdown watcher"""
        self._running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=2)