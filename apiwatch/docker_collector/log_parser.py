"""
apiwatch v2, phase 2: shape raw log lines into structured documents.

Real containers emit multiple log formats from the same stdout stream,
gunicorn's own lines look nothing like your app's logger lines. This
parser tries known formats first and falls back to a raw record rather
than dropping or crashing on anything it doesn't recognize. A log
collector that throws away lines it can't parse is worse than useless,
you lose exactly the weird lines you'd want to see.

Phase 3: on top of level/logger/message extraction, every line is also
scanned for an embedded structured value (dict, list, or tuple) and, if
found, parsed into `parsed_data`. This runs once here rather than in the
UI, so search, export, and alerts all benefit from it too, not just the
JSON tree view.
"""

import ast
import json
import re
from datetime import datetime, timezone
from typing import Optional

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


def _find_balanced(text: str, start: int) -> Optional[str]:
    """
    Starting at an opening bracket, walk forward tracking nesting depth
    and quoted-string state (so a '}' inside a string value doesn't end
    the match early), return the substring up to and including the
    matching close bracket, or None if it never balances (truncated
    line, mismatched brackets, log line got cut off mid-write, etc).
    """
    open_char = text[start]
    close_char = {'{': '}', '[': ']', '(': ')'}[open_char]

    depth = 0
    in_string = None  # None, or the quote character currently open
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == in_string:
                in_string = None
            continue

        if ch in ('"', "'"):
            in_string = ch
        elif ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    return None


def extract_structured_data(text: str):
    """
    Find the first bracketed structure in a log line and parse it, if
    possible. Tries real JSON first (covers lines that already embed
    valid JSON, e.g. 'data: {"a": 1}'), then falls back to Python's
    literal syntax via ast.literal_eval (covers dict/list/tuple reprs
    like `str()`/`repr()` produce, e.g. "{'a': 1}", which is NOT valid
    JSON but is exactly what a lot of Python apps log when they do
    something like `logger.info(f"body | {payload}")`).

    Only '{' and '[' are treated as candidate start characters, '('
    deliberately isn't, bare parentheses are extremely common in plain
    English text ("see docs (here)") and would trigger constant failed
    parse attempts for no benefit. A tuple nested inside a dict or list
    is still caught fine, since the outer '{'/'[' is the trigger and
    ast.literal_eval parses the whole nested structure in one pass.

    Returns the parsed value (tuples get converted to lists so the
    result is always JSON-serializable downstream), or None if nothing
    parseable is found.
    """
    if not text:
        return None

    for i, ch in enumerate(text):
        if ch not in ('{', '['):
            continue

        candidate = _find_balanced(text, i)
        if candidate is None:
            continue

        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            pass

        try:
            value = ast.literal_eval(candidate)
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            continue

        if isinstance(value, tuple):
            value = list(value)
        if isinstance(value, (dict, list)):
            return value

    return None


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
        "parsed_data": None,        # structured value extracted from the line, if any
    }

    m = PYLOG_RE.match(raw_line)
    if m:
        doc["level"] = m.group("level")
        doc["logger"] = m.group("logger")
        doc["message"] = m.group("message")
        doc["source_timestamp"] = m.group("timestamp")
    else:
        m = GUNICORN_RE.match(raw_line)
        if m:
            doc["level"] = m.group("level")
            doc["message"] = m.group("message")
            doc["source_timestamp"] = m.group("timestamp")
        else:
            hint = LEVEL_HINT_RE.search(raw_line)
            if hint:
                doc["level"] = hint.group(1).replace("WARN", "WARNING")

    # runs once, regardless of which branch above matched, against the
    # already-cleaned message (prefix like level/timestamp/logger already
    # stripped where applicable, so the scan starts closer to the actual
    # payload instead of re-scanning the whole raw line every time)
    doc["parsed_data"] = extract_structured_data(doc["message"])

    return doc


if __name__ == "__main__":
    # test straight against real and representative lines
    sample_lines = [
        "[2026-07-29 19:41:48 +0000] [1] [INFO] Starting gunicorn 23.0.0",
        "WARNING 2026-07-29 19:43:41,687 phone_locking.api API error response: imei_1 cannot be empty",
        "ERROR 2026-07-29 19:46:27,128 phone_locking.api API [lock-device] response: 'device_brand' is a required field.",
        "INFO:AFRILOC:[TENANTS][DETAIL] body | {'user_id': 33, 'username': 'isaac', 'enterprise_code': 'TEST-002'}",
        'INFO:     172.18.0.7:38898 - "POST /api/v1/auth/login HTTP/1.0" 401 Unauthorized',
        '{"status":401,"elapsed_ms":279.5,"body":{"detail":"Invalid email or password"}}',
        "something totally unstructured a dev printed by accident",
    ]

    for line in sample_lines:
        parsed = parse_log_line(line, "abc123", "django_app-django-1", "django_app")
        print(f"{parsed['level']:<8} logger={parsed['logger']!s:<20} parsed_data={parsed['parsed_data']}")