"""
DockerCollector: watches container stdout/stderr via aiodocker and feeds
parsed log lines into the dashboard's db + websocket broadcast.
"""
import aiodocker
import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Dict, Optional


def _preview_message(message) -> str:
    """
    message is the real payload, level/logger are frequently null. If
    the message is itself JSON, show its shape (dict keys, or list
    length) instead of dumping the whole thing. Otherwise treat it as
    plain text and truncate to the first 100 chars.
    """
    if not message:
        return ""

    parsed = None
    if isinstance(message, str):
        try:
            parsed = json.loads(message)
        except (TypeError, ValueError):
            parsed = None
    elif isinstance(message, (dict, list)):
        parsed = message

    if isinstance(parsed, dict):
        return f"keys={list(parsed.keys())}"
    if isinstance(parsed, list):
        return f"list[{len(parsed)} items]"

    text = str(message)
    return text[:100] + "..." if len(text) > 100 else text


class DockerCollector:
    def __init__(
        self,
        db,
        broadcast: Optional[Callable[[dict], Awaitable[None]]] = None,
        label_filter: Optional[str] = None,
        watch_all: Optional[bool] = None,
        exclude_names: Optional[set] = None,
        poll_interval: Optional[int] = None,
        batch_size: Optional[int] = None,
        batch_interval: Optional[int] = None,
        checkpoint_interval: Optional[int] = None,
        retention_hours: Optional[int] = None,
        cleanup_interval: Optional[int] = None,
    ):
        """
        Args:
            db: already-initialized AsyncDB instance (server.py owns this)
            broadcast: optional async callable(record: dict), used to push
                each parsed line to connected dashboard websocket clients
                as it arrives. Pass None to run standalone with no live
                push, db writes still happen either way.
            label_filter: e.g. 'apiwatch.collect=true', ignored if watch_all
            watch_all: watch every running container instead of only
                labelled ones
            exclude_names: container names to skip when watch_all is True
        Any arg left as None falls back to its APIWATCH_* env var.
        """
        self.db = db
        self.broadcast = broadcast

        self.label_filter = label_filter or os.getenv(
            "APIWATCH_COLLECT_LABEL", "apiwatch.collect=true"
        )
        self.watch_all = (
            watch_all
            if watch_all is not None
            else os.getenv("APIWATCH_WATCH_ALL", "false").lower() == "true"
        )
        self.exclude_names = exclude_names or set(
            n.strip() for n in os.getenv("APIWATCH_EXCLUDE", "").split(",") if n.strip()
        )
        self.poll_interval = poll_interval or int(os.getenv("APIWATCH_POLL_INTERVAL", "5"))
        self.batch_size = batch_size or int(os.getenv("APIWATCH_BATCH_SIZE", "50"))
        self.batch_interval = batch_interval or int(os.getenv("APIWATCH_BATCH_INTERVAL", "2"))
        self.checkpoint_interval = checkpoint_interval or int(
            os.getenv("APIWATCH_CHECKPOINT_INTERVAL", "5")
        )
        self.retention_hours = retention_hours or int(os.getenv("APIWATCH_RETENTION_HOURS", "72"))
        self.cleanup_interval = cleanup_interval or int(
            os.getenv("APIWATCH_CLEANUP_INTERVAL_SECONDS", "3600")
        )

        raw_levels = os.getenv("APIWATCH_LOG_LEVELS", "ERROR,WARNING,CRITICAL,INFO,UNKNOWN,DEBUG")
        self.log_level_filter = (
            {lvl.strip().upper() for lvl in raw_levels.split(",") if lvl.strip()}
            if raw_levels else None
        )

        self.docker: Optional[aiodocker.Docker] = None
        self.watched: Dict[str, asyncio.Task] = {}
        self._poll_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    # ---- lifecycle ----

    async def start(self):
        """Call this from server.py's start(), after db.init() has run."""
        if self._running:
            return
        self.docker = aiodocker.Docker(url=os.getenv("DOCKER_HOST"))
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        """Call this from server.py's stop(). Does not touch the db."""
        self._running = False

        if self._poll_task:
            self._poll_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()

        for task in list(self.watched.values()):
            task.cancel()
        self.watched.clear()

        if self.docker:
            await self.docker.close()
            self.docker = None

        print("[ApiWatchdog] Docker collector stopped", flush=True)

    # ---- container discovery ----

    async def _container_info(self, container):
        info = await container.show()
        name = info.get("Name", "").lstrip("/")
        labels = (info.get("Config") or {}).get("Labels") or {}
        return name, labels

    async def _list_target_containers(self):
        filters = None
        if not self.watch_all:
            filters = {"label": [self.label_filter]}

        containers = await self.docker.containers.list(filters=filters)

        if not self.watch_all:
            return containers

        result = []
        for c in containers:
            name, _ = await self._container_info(c)
            if name not in self.exclude_names:
                result.append(c)
        return result

    # ---- log shaping ----

    def _record_from_parsed(self, parsed: dict) -> dict:
        """
        Build the db record straight from the parser output. timestamp
        always comes from received_at (a real datetime we generated)
        """
        return {
            "id": str(uuid.uuid4()),
            "container_id": parsed["container_id"],
            "container_name": parsed["container_name"],
            "service": parsed["service_label"],
            "level": (parsed["level"] or "UNKNOWN").upper(),
            "logger": parsed["logger"],
            "message": parsed["message"],
            "raw": parsed["raw"],
            "parsed_data": (
                json.dumps(parsed["parsed_data"])
                if parsed.get("parsed_data") is not None else None
            ),
            "timestamp": parsed["received_at"].isoformat(),
        }

    # ---- streaming ----

    async def _stream_container(self, container, container_id, container_name, service_label, since_ts):
        from .log_parser import parse_log_line

        buffer = []
        last_flush = time.time()
        last_checkpoint = time.time()

        try:
            async for raw_line in container.log(
                stdout=True, stderr=True, follow=True, since=since_ts
            ):
                line = raw_line.rstrip("\n")

                # parsing (especially the structured-data extraction inside
                # parse_log_line) runs against arbitrary real-world text
                try:
                    parsed = parse_log_line(
                        raw_line=line,
                        container_id=container_id,
                        container_name=container_name,
                        service_label=service_label,
                    )
                    record = self._record_from_parsed(parsed)
                except Exception as exc:
                    print(f"[ApiWatchdog] failed to parse a line from {container_name}: {exc}", flush=True)
                    continue

                now = time.time()

                # checkpoint advances regardless of the filter below, a
                # container that only ever emits filtered-out levels
                if now - last_checkpoint >= self.checkpoint_interval:
                    await self.db.set_checkpoint(container_id, container_name, int(now))
                    last_checkpoint = now

                # env-configured allowlist, dropped here means gone for
                # good, never stored, never broadcast, never printed.
                if self.log_level_filter and record["level"] not in self.log_level_filter:
                    continue

                buffer.append(record)

                # terminal output is just a heartbeat, not the actual
                # log, the dashboard is where the real content lives.
                # message is the field that actually carries the data
                print(f"{container_name}: {_preview_message(record['message'])}", flush=True)

                # push live to the dashboard immediately, independent of
                # the db batch flush below, so the UI doesn't lag behind
                if self.broadcast:
                    await self.broadcast(record)

                if len(buffer) >= self.batch_size or now - last_flush >= self.batch_interval:
                    await self.db.insert_logs_batch(buffer)
                    buffer.clear()
                    last_flush = now

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"error streaming {container_name}: {exc}", flush=True)
        finally:
            if buffer:
                await self.db.insert_logs_batch(buffer)
            await self.db.set_checkpoint(container_id, container_name, int(time.time()))
            print(f"stopped watching {container_name}", flush=True)

    # ---- loops ----

    async def _poll_loop(self):
        while self._running:
            try:
                containers = await self._list_target_containers()
            except Exception as exc:
                print(f"failed to list containers: {exc}", flush=True)
                await asyncio.sleep(self.poll_interval)
                continue

            live_ids = [c.id for c in containers]
            checkpoints = await self.db.get_all_checkpoints()

            for c in containers:
                if c.id not in self.watched:
                    name, labels = await self._container_info(c)
                    service_label = labels.get("apiwatch.name", name)
                    since_ts = checkpoints.get(c.id, int(time.time()))
                    task = asyncio.create_task(
                        self._stream_container(c, c.id, name, service_label, since_ts)
                    )
                    self.watched[c.id] = task
                    print(f"now watching {name}", flush=True)

            for cid in list(self.watched):
                task = self.watched[cid]
                still_live = cid in live_ids
                # a task can finish on its own (an exception inside
                # _stream_container that its own try/except swallowed,
                # or the container's log stream simply ended)
                if not still_live or task.done():
                    if not task.done():
                        task.cancel()
                    del self.watched[cid]

            # checkpoints get pruned when a container disappears, the
            # log rows themselves are untouched, they stay queryable
            await self.db.remove_checkpoints_except(live_ids)
            await asyncio.sleep(self.poll_interval)

    async def _cleanup_loop(self):
        while self._running:
            await asyncio.sleep(self.cleanup_interval)
            cutoff = (
                datetime.now(timezone.utc) - timedelta(hours=self.retention_hours)
            ).strftime("%Y-%m-%d %H:%M:%S")
            try:
                deleted = await self.db.delete_logs_older_than(cutoff)
                if deleted:
                    print(f"retention sweep removed {deleted} rows", flush=True)
            except Exception as exc:
                print(f"retention sweep failed: {exc}", flush=True)