import time 
import json
from functools import wraps
from .import ApiWatcher

try:
    from flask import request, g 
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

if not FLASK_AVAILABLE:
    raise ImportError(
        "Flask is not installed. Intall with pip install api-watch-dog[flask]"
    )

class FlaskWatchDogMiddleware:
    """Flask middleware for ApiWatchdog - optimized for zero blocking"""

    def __init__(self, app, watcher, capture_request_body=True, capture_response_body=True):
        """
        Initialize Flask middleware

        Args:
            app: Flask application instance
            watcher: ApiWatcher instance
            capture_request_body: whether to capture request body. Default = True
            capture_response_body: whether to capture response body. Default = True
        """
        self.app = app
        self.watcher:ApiWatcher = watcher
        self.capture_request_body = capture_request_body
        self.capture_response_body = capture_response_body

        # Register hooks
        self._register_hooks()
    

    def _register_hooks(self):
        """Register Flask before/after request hooks"""

        @self.app.before_request
        def before_request():
            g.start_time = time.time()
        
        @self.app.after_request
        def after_request(response):
            try:
                duration_ms = (time.time() - g.start_time) * 1000

                # Extract request data 
                request_data = None
                if self.capture_request_body and request.is_json:
                    try:
                        request_data = request.get_json()
                    except Exception as e:
                        request_data = None
                elif self.capture_request_body and request.form:
                    request_data = dict(request.form)


                # Extract response data 
                response_data = None
                if self.capture_response_body:
                    try:
                        if response.is_json:
                            response_data = response.get_json()
                        elif response.data:
                            # decode 
                            response_data = response.data.encode('utf8')[:1000] # 1000 chars
                    except Exception:
                        response_data = None
                

                # Extract headers: filter authentication key:val
                headers = { 
                    key:value for key,value in request.headers.items()
                    if key.lower() not in ['authorization', 'cookie', 'api-key']
                }

                # Fire-and-forget-logging
                log_request = {
                    'method': request.method,
                    'path': request.path,
                    'status_code': response.status_code,
                    'request_data': request_data,
                    'response_data': response_data,
                    'duration_ms': round(duration_ms, 2),
                    'headers': headers,
                    'query_params': dict(request.args)

                }
                self.watcher.log_request(**log_request)
                print(f'{request.method} request logged from {request.path}')
            except Exception as e:
                print(f'[api-watch-dog] middleware error: {e}')
            
            return response


def watch_route(watcher:ApiWatcher):
    """
    Decorator for manual route watching (alternate middleware)

    Usage:
        @app.route('/api/users/')
        @watch_route(api_watcher)
        def get_users():
            return jsonify(users)
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            start_time = time.time()

            # Extract request info
            request_data = None
            if request.is_json:
                try:
                    request_data = request.get_json()
                except Exception:
                    pass
            
            # run route 
            response = f(*args, **kwargs)

            # total request duration
            duration_ms = (time.time() - start_time * 1000)

            # log (async Fire-forget)
            log_request = {
                'method': request.method,
                'path': request.path,
                'status_code': 200 if not 'error' in response else 400,
                'request_data': request_data,
                'response_data': str(response)[:500] if response else None,
                'duration_ms': round(duration_ms, 2),
                'headers': dict(request.headers),
                'query_params': dict(request.args)
            }
            watcher.log_request(**log_request)
            return response
        return wrapper
    return decorator