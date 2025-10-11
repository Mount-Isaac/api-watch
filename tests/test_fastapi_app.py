from fastapi import FastAPI
from pydantic import BaseModel
from apiwatch import ApiWatcher
from apiwatch.middleware_fastapi import FastAPIWatchdogMiddleware


app = FastAPI()

# Initialize watcher - it will HTTP POST to dashboard server
api_watcher = ApiWatcher(
    service_name='fastapi-service',
    dashboard_host='localhost',
    dashboard_port=22222
)

app.add_middleware(FastAPIWatchdogMiddleware, watcher=api_watcher)


class HelloRequest(BaseModel):
    name: str = "World"


@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "service": "fastapi-service"
    }


@app.get("/api/users")
async def get_users():
    users = [
        {"id": 1, "name": "Alice", "email": "alice@example.com"},
        {"id": 2, "name": "Bob", "email": "bob@example.com"}
    ]
    return {"users": users, "count": len(users)}


@app.post("/api/hello")
async def hello(data: HelloRequest):
    return {
        "message": f"Hello {data.name}!",
        "service": "fastapi-service"
    }


if __name__ == '__main__':
    import uvicorn
    print("=" * 60)
    print("FastAPI Service + ApiWatchdog")
    print("=" * 60)
    print("Dashboard: http://localhost:22222 (run separately!)")
    print("API: http://localhost:8000")
    print("=" * 60)
    print("\nMake sure dashboard is running first:")
    print("  python -m apiwatchdog")
    print("\nTest commands:")
    print("  curl http://localhost:8000/api/health")
    print("  curl http://localhost:8000/api/users")
    print("  curl -X POST http://localhost:8000/api/hello -H 'Content-Type: application/json' -d '{\"name\":\"Dev\"}'")
    print("=" * 60)
    print()
    
    uvicorn.run(app, host="0.0.0.0", port=8000)