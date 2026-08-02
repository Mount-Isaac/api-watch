"""
apiwatch v2, phase 2: shape raw log lines into structured documents.

Real containers emit multiple log formats from the same stdout stream,
gunicorn's own lines look nothing like your app's logger lines. This
parser tries known formats first and falls back to a raw record rather
than dropping or crashing on anything it doesn't recognize. A log
collector that throws away lines it can't parse is worse than useless,
you lose exactly the weird lines you'd want to see.
"""

import re
from datetime import datetime, timezone

# gunicorn / many WSGI servers:
# [2026-07-29 19:41:48 +0000] [1] [INFO] Starting gunicorn 23.0.0
GUNICORN_RE = re.compile(
    r'^\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})\]\s*'
    r'\[(?P<pid>\d+)\]\s*\[(?P<level>\w+)\]\s*(?P<message>.*)$'
)

# python logging default-ish format, what your Django app is emitting:
# WARNING 2026-07-29 19:43:41,687 phone_locking.api API error response: ...
PYLOG_RE = re.compile(
    r'^(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+'
    r'(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+'
    r'(?P<logger>\S+)\s+(?P<message>.*)$'
)

# fallback: does the line at least mention a level keyword anywhere,
# so a line we can't fully parse still gets bucketed sensibly
LEVEL_HINT_RE = re.compile(r'\b(CRITICAL|ERROR|WARNING|WARN|INFO|DEBUG)\b')


def parse_log_line(raw_line: str, container_id: str, container_name: str,
                    service_label: str | None = None) -> dict:
    raw_line = raw_line.rstrip("\n")

    doc = {
        "container_id": container_id,
        "container_name": container_name,
        "service_label": service_label or container_name,
        "level": "UNKNOWN",
        "logger": None,
        "message": raw_line,
        "raw": raw_line,
        "source_timestamp": None,   # timestamp claimed by the log line itself
        "received_at": datetime.now(timezone.utc),  # when we actually saw it
    }

    m = PYLOG_RE.match(raw_line)
    if m:
        doc["level"] = m.group("level")
        doc["logger"] = m.group("logger")
        doc["message"] = m.group("message")
        doc["source_timestamp"] = m.group("timestamp")
        return doc

    m = GUNICORN_RE.match(raw_line)
    if m:
        doc["level"] = m.group("level")
        doc["message"] = m.group("message")
        doc["source_timestamp"] = m.group("timestamp")
        return doc

    hint = LEVEL_HINT_RE.search(raw_line)
    if hint:
        doc["level"] = hint.group(1).replace("WARN", "WARNING")

    return doc


if __name__ == "__main__":
    # test straight against the real lines you captured
    sample_lines = [
        "[2026-07-29 19:41:48 +0000] [1] [INFO] Starting gunicorn 23.0.0",
        "[2026-07-29 19:41:48 +0000] [1] [INFO] Listening at: http://0.0.0.0:7070 (1)",
        "[2026-07-29 19:41:48 +0000] [1] [INFO] Using worker: sync",
        "[2026-07-29 19:41:48 +0000] [7] [INFO] Booting worker with pid: 7",
        "WARNING 2026-07-29 19:43:41,687 phone_locking.api API error response: imei_1 cannot be empty",
        "ERROR 2026-07-29 19:46:27,128 phone_locking.api API [lock-device] response: 'device_brand' is a required field.",
        "ERROR 2026-07-29 19:46:40,134 phone_locking.api API [info-device] response: {'ok': False, 'code': 'ERR_2026-07-29 19:46:40', 'message': 'The device is not attached to any Public Key!', 'status': 404}",
        "something totally unstructured a dev printed by accident",
    ]

    for line in sample_lines:
        parsed = parse_log_line(line, "abc123", "django_app-django-1", "django_app")
        print(f"{parsed['level']:<8} logger={parsed['logger']!s:<20} msg={parsed['message'][:60]}")