import time
import json

try:
    from fastapi import Request, Response
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.datastructures import Headers
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


if not FASTAPI_AVAILABLE:
    raise ImportError(
        "FastAPI is not installed. Install with: pip install apiwatchdog[fastapi]"
    )


class FastAPIWatchdogMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for ApiWatchdog - optimized for zero blocking"""
    
    def __init__(self, app, watcher, capture_request_body=True, capture_response_body=True):
        """
        Initialize FastAPI middleware
        
        Args:
            app: FastAPI application instance
            watcher: ApiWatcher instance
            capture_request_body: Whether to capture request body
            capture_response_body: Whether to capture response body
        """
        super().__init__(app)
        self.watcher = watcher
        self.capture_request_body = capture_request_body
        self.capture_response_body = capture_response_body
    
    async def dispatch(self, request: Request, call_next):
        """Process request and response"""
        start_time = time.time()
        
        # Extract request data
        request_data = None
        if self.capture_request_body:
            try:
                content_type = request.headers.get("content-type", "")
                if "application/json" in content_type:
                    # Read body (FastAPI allows multiple reads)
                    body = await request.body()
                    if body:
                        request_data = json.loads(body.decode('utf-8'))
            except Exception:
                request_data = None
        
        # Extract query params
        query_params = dict(request.query_params)
        
        # Extract headers (filter sensitive ones)
        headers = {k: v for k, v in request.headers.items()
                  if k.lower() not in ['authorization', 'cookie', 'x-api-key']}
        
        # Call the route
        try:
            response = await call_next(request)
        except Exception as e:
            # Log error and re-raise
            duration_ms = (time.time() - start_time) * 1000
            self.watcher.log_request(
                method=request.method,
                path=request.url.path,
                status_code=500,
                request_data=request_data,
                response_data={"error": str(e)},
                duration_ms=round(duration_ms, 2),
                headers=headers,
                query_params=query_params
            )
            raise
        
        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000
        
        # Extract response data
        response_data = None
        if self.capture_response_body:
            try:
                # For streaming responses, we can't capture body easily
                # Only capture for regular responses
                if hasattr(response, 'body'):
                    body = response.body
                    if body:
                        content_type = response.headers.get("content-type", "")
                        if "application/json" in content_type:
                            response_data = json.loads(body.decode('utf-8'))
                        else:
                            response_data = body.decode('utf-8')[:1000]
            except Exception:
                response_data = None
        
        # Fire-and-forget logging
        try:
            self.watcher.log_request(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                request_data=request_data,
                response_data=response_data,
                duration_ms=round(duration_ms, 2),
                headers=headers,
                query_params=query_params
            )
        except Exception as e:
            # Never let monitoring crash the app
            print(f"[ApiWatchdog] Middleware error: {e}")
        
        return response