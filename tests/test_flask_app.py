from flask import Flask, jsonify, request
from apiwatch import ApiWatcher
from apiwatch.middleware_flask import FlaskWatchMiddleware


app = Flask(__name__)

# Initialize watcher - it will HTTP POST to dashboard server
api_watcher = ApiWatcher(
    service_name='flask-service',
    dashboard_host='localhost',
    dashboard_port=22222,
    auto_start_dashboard=False
)

FlaskWatchMiddleware(app, api_watcher)


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "service": "flask-service"
    })


@app.route('/api/users', methods=['GET'])
def get_users():
    users = [
        {"id": 1, "name": "Alice", "email": "alice@example.com"},
        {"id": 2, "name": "Bob", "email": "bob@example.com"},
        {"id": 3, "name": "Charlie", "email": "charlie@example.com"}
    ]
    return jsonify({"users": users, "count": len(users)})


@app.route('/api/hello', methods=['POST'])
def hello():
    data = request.get_json() or {}
    return jsonify({
        "message": f"Hello {data.get('name', 'World')}!",
        "service": "flask-service"
    })


if __name__ == '__main__':
    print("=" * 60)
    print("Flask Service + ApiWatchdog")
    print("=" * 60)
    print("Dashboard: http://localhost:22222 (run separately!)")
    print("API: http://localhost:5000")
    print("=" * 60)
    print("\nMake sure dashboard is running first:")
    print("  python -m apiwatchdog")
    print("\nTest commands:")
    print("  curl http://localhost:5000/api/health")
    print("  curl http://localhost:5000/api/users")
    print("  curl -X POST http://localhost:5000/api/hello -H 'Content-Type: application/json' -d '{\"name\":\"Dev\"}'")
    print("=" * 60)
    print()
    
    app.run(port=6000, debug=True, use_reloader=False)