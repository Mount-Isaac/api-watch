"""
ApiWatchdog - Real-time API Request Monitoring
A lightweight, async logging tool for Flask/FastAPI
"""

__version__ = "0.1.0"
__author__ = "Isaac Kyalo"

from .watcher import ApiWatcher

__all__ = ['ApiWatcher']


def _setup_flask_support():
    """Lazy import Flask middleware"""
    try:
        from .middleware_flask import FlaskWatchdogMiddleware, watch_route
        return FlaskWatchdogMiddleware, watch_route
    except ImportError:
        return None, None

def _setup_fastapi_support():
    """Lazy import FastAPI middleware"""
    try:
        from .middleware_fastapi import FastAPIWatchdogMiddleware
        return FastAPIWatchdogMiddleware
    except ImportError:
        return None