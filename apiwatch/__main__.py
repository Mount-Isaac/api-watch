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
    
    asyncio.run(run_standalone(
        host='0.0.0.0', 
        port=22222, 
        username=username, 
        password=password
    ))
