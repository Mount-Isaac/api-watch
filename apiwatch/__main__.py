"""
Standalone Dashboard Server
Usage: python -m apiwatchdog
"""
import asyncio
from .server import run_standalone
import os

if __name__ == '__main__':
    username = os.getenv('WATCHDOG_USERNAME', 'admin')
    password = os.getenv('WATCHDOG_PASSWORD', 'admin')
    host = os.getenv('API_WATCH_DASHBOARD_HOST', '127.0.0.1')
    port = os.getenv('API_WATCH_DASHBOARD_PORT', 22222)
    
    asyncio.run(run_standalone(
        host=host,
        port=int(port), 
        username=username, 
        password=password
    ))
