# api-watch

**Real-time API monitoring for Flask and FastAPI with zero-blocking async logging.**

[![PyPI Version](https://img.shields.io/pypi/v/api-watch.svg)](https://pypi.org/project/api-watch/)
[![Python Support](https://img.shields.io/pypi/pyversions/rabbitmq-easy.svg)](https://pypi.org/project/rabbitmq-easy/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A lightweight, developer-focused tool that streams your API requests, responses, and metadata to a beautiful real-time dashboard. Perfect for debugging, development, and understanding your API traffic.

![api-watch Dashboard](./images/api_watch.gif)

---

## Features

- **Zero Performance Impact** - Fire-and-forget async logging that never blocks your API
- **Real-time Streaming** - WebSocket-powered dashboard shows requests as they happen
- **Auto-Start Dashboard** - Just import and use, dashboard starts automatically
- **Full Visibility** - Method, path, status, timing, headers, request/response data
- **Filter by Status** - Quickly filter requests by status code
- **Request Statistics** - Visual metrics and charts
- **Minimal UI** - Clean, fast dashboard focused on what matters
- **Multi-Framework** - Works with Flask and FastAPI
- **Production Ready** - Standalone mode for Docker/Kubernetes
- **Optimized Dependencies** - Only install what you need

---

## Quick Start

### Installation




###### git clone https 
```bash
git clone https://github.com/Mount-Isaac/api-watch.git
```

###### git clone ssh 
```bash
git@github.com:Mount-Isaac/api-watch.git
```

**Terminal run:**

```bash
python -m apiwatch
```

**Docker run: easiest**

```bash
docker pull theisaac/api-watch:latest
docker compose up -d
```

**Open dashboard:**

```
http://localhost:22222
```

---

##  Dashboard Features

### Real-time Request Monitoring

- Live streaming of API requests
- Color-coded HTTP methods (GET, POST, PUT, DELETE)
- Status code highlighting (success/error)
- Response time tracking
- Service name badges (multi-service support)

### Filters & Search

- Filter by status code (2xx, 3xx, 4xx, 5xx, All)
- Sort by newest, oldest, fastest, sloweset, status(high-low)
- Filter by HTTP method


---

### Docker Compose

```yaml


services:
  apiwatch:
    image: theisaac/api-watch:v2
    ports:
      - "22222:22222"
    restart: unless-stopped
    environment:
      - API_WATCH_MAX_HISTORY=3000
      - WATCHDOG_USERNAME=admin
      - WATCHDOG_PASSWORD=password
      - APIWATCH_SLACK_WEBHOOK_URL=[your-slack-webhook-generated-from-apps]
      - APIWATCH_GMAIL_USER=[your-email]@gmail.com
      - APIWATCH_GMAIL_APP_PASSWORD=[your-app-password-generated]
    volumes:
    - ./data:/app/data
    - /var/run/docker.sock:/var/run/docker.sock
```
---
