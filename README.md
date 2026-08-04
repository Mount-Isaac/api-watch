# api-watch

**Stop grepping `docker logs`. Stop standing up Loki for a five-person team.**

One container. No Redis, no log-shipping agent, no config sprawl. Point it at your Docker socket, get a live, searchable, alerting dashboard in under a minute.

![status](https://img.shields.io/badge/status-active-brightgreen) ![license](https://img.shields.io/badge/license-MIT-blue)

![api-watch demo](./images/apiwatch.gif)

---

## Why api-watch

Grafana + Loki is the right tool once you've outgrown a single box. Until then, it's a lot of infrastructure to stand up just to read logs.

api-watch sits in between:

- **Real persistence.** SQLite-backed, configurable retention, survives restarts. Search, filter, and export logs from hours or days ago — not just what's streaming right now.
- **One container, zero dependencies.** No Redis, no Postgres, no separate ingestion pipeline.
- **Actually readable JSON.** Structured log lines expand into a collapsible, syntax-highlighted tree — not a wall of escaped text.
- **Alerting built in.** Slack and/or Gmail, fires on your chosen severity threshold, with cooldowns so a log flood doesn't flood your phone too.
- **Built for small teams, not enterprises.** No SSO, no multi-host clustering — that's Grafana's job. If you need those, you've outgrown this tool, and that's fine.

## Features

- Live-tailing container logs over WebSocket, with pause/resume so a busy stream doesn't yank rows out from under you mid-read
- Server-side search across the full log history — not just what's loaded on screen — with matches highlighted in both keys and values of parsed JSON
- Filter by level and container, sortable by time or severity
- Auto-parses `logging` output (any language) and JSON log formats; falls back gracefully on anything else
- Expandable JSON tree view with copy-to-clipboard (pretty-printed)
- Slack + Gmail alerting, independent toggles, per-channel cooldowns, configurable severity threshold
- Real server-side session auth (not just a client-side flag)
- Configurable retention window with automatic cleanup
- Export filtered logs to a file
- Auto-discovers containers by label, or watch everything on the host
- Dark/light themes

## Quickstart

```bash
docker run -d \
  --name apiwatch \
  -p 22222:22222 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v apiwatch-data:/app/data \
  -e WATCHDOG_USERNAME=admin \
  -e WATCHDOG_PASSWORD=changeme \
  theisaac/api-watch:latest
```

Open `http://localhost:22222`, log in, done.

api-watch only watches containers labelled `apiwatch.collect=true`:

```bash
docker run -d --label apiwatch.collect=true myapp:latest
```

### docker-compose

```yaml
services:
  apiwatch:
    image: theisaac/api-watch:latest
    ports:
      - "22222:22222"
    restart: unless-stopped
    environment:
      - WATCHDOG_USERNAME=admin
      - WATCHDOG_PASSWORD=changeme
    volumes:
      - ./data:/app/data
      - /var/run/docker.sock:/var/run/docker.sock
```

## Target docker container (e.g. Backend)

```yaml
services:
  backend:
    image: registry.gitlab.com/org_name/repo_group/backend:latest
    ports:
      - "5000:5000"
    restart: unless-stopped
    env_file:
      - /opt/configs/.env
    volumes:
      - /var/logs/backend:/app/logs
    labels:
      - "apiwatch.collect=true"
```

## Configuration

All env vars are optional except credentials.

| Variable | Default | Purpose |
|---|---|---|
| `WATCHDOG_USERNAME` / `WATCHDOG_PASSWORD` | `admin`/`password` | Dashboard login. **Change these.** |
| `API_WATCH_DASHBOARD_HOST` | `0.0.0.0` | Bind address |
| `API_WATCH_DASHBOARD_PORT` | `22222` | Port |
| `APIWATCH_COLLECT_LABEL` | `apiwatch.collect=true` | Label filter when not watching everything |
| `APIWATCH_WATCH_ALL` | `false` | Watch every container, ignore the label filter |
| `APIWATCH_EXCLUDE` | — | Comma-separated container names to skip when `WATCH_ALL=true` |
| `APIWATCH_LOG_LEVELS` | — (all levels) | Comma-separated allowlist (case-insensitive), e.g. `INFO,WARNING,ERROR`. Anything outside this list is dropped before storage, not just hidden. |
| `APIWATCH_RETENTION_HOURS` | `72` | How long logs are kept before the cleanup sweep deletes them |
| `APIWATCH_SESSION_TTL_SECONDS` | `86400` | How long a login session stays valid |
| `APIWATCH_SLACK_WEBHOOK_URL` | — | Enables Slack alerting |
| `APIWATCH_GMAIL_USER` / `APIWATCH_GMAIL_APP_PASSWORD` | — | Enables Gmail alerting (use an [App Password](https://myaccount.google.com/apppasswords), not your real password) |
| `APIWATCH_ALERT_EMAIL_TO` | same as `GMAIL_USER` | Alert email recipient |
| `APIWATCH_ALERT_COOLDOWN_SECONDS` | `300` | Minimum gap between alerts on the same channel |
| `APIWATCH_PUBLIC_URL` | — | If set, alert emails include a link back to your dashboard |

## Data & retention

Logs live in a SQLite file under `/app/data` inside the container — mount a volume there or you lose history on every restart. Logs older than `APIWATCH_RETENTION_HOURS` are swept automatically on an hourly timer. There's an export-to-cold-storage step too: the export button on the UI saves filtered history as a JSON file to local disk.

## Known limitations

Being upfront about what this tool intentionally doesn't do:

- Single shared login, no per-user accounts or SSO
- Single Docker host, no cluster/multi-host aggregation
- Search is `LIKE`-based — fine at this scale, not built for millions of rows

If you need any of these, Grafana + Loki is genuinely the better tool for that job.

## Contributing

Issues and PRs welcome. This started as an internal tool for a small startup's ops team — feedback from other small teams running it is exactly what shapes what gets built next.

## License

MIT

## Support

If this saved you from standing up Loki for a 5-person team, [buy me a coffee](https://ko-fi.com/isaackyalo) ☕

Built by [Isaac Kyalo — GitHub](https://github.com/mount-isaac/api-watch)