"""
Shape raw log lines into structured documents.
Real containers emit multiple log formats from the same stdout stream,

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

# python logging default-ish format, what your Django/Flask/FastAPI/Express/Springboot/Apolo app is emitting:
# WARNING 2026-07-29 19:43:41,687 phone_locking.api API error response: ...
PYLOG_RE = re.compile(
    r'^(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+'
    r'(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+'
    r'(?P<logger>\S+)\s+(?P<message>.*)$'
)

# docker-compose stdout prefix
COMPOSE_PREFIX_RE = re.compile(
    r'^(?P<service>\S+)\s*\|\s*'
    r'(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s*'
    r'(?P<rest>.*)$'
)

# fallback
LEVEL_HINT_RE = re.compile(r'\b(CRITICAL|ERROR|WARNING|WARN|INFO|DEBUG)\b')


def _find_balanced(text: str, start: int) -> Optional[str]:
    """
    Starting at an opening bracket, walk forward tracking nesting depth
    and quoted-string state (so a '}' inside a string value doesn't end
    the match early), return the substring
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
    Find the first bracketed structure in a log line and parse it

    Returns the parsed value: result is always JSON-serializable downstream), 
    or None if nothing parseable is found.
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
        except (ValueError, SyntaxError, MemoryError, RecursionError, TypeError):
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
        "source_timestamp": None,   
        "received_at": datetime.now(timezone.utc),  
        "parsed_data": None,        
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
            # Not a recognized structured format. Strip a docker-compose
            body_for_hint = raw_line
            m = COMPOSE_PREFIX_RE.match(raw_line)
            if m:
                doc["message"] = m.group("rest")
                doc["source_timestamp"] = m.group("timestamp")
                body_for_hint = m.group("rest")

            hint = LEVEL_HINT_RE.search(body_for_hint)
            if hint:
                doc["level"] = hint.group(1).replace("WARN", "WARNING")
            # else: level stays "UNKNOWN" -- doc is still returned, never dropped.

    doc["parsed_data"] = extract_structured_data(doc["message"])

    return doc


if __name__ == "__main__":
    sample_lines = [
        "[2026-07-29 19:41:48 +0000] [1] [INFO] Starting gunicorn 23.0.0",
        "WARNING 2026-07-29 19:43:41,687 phone_locking.api API error response: imei_1 cannot be empty",
        "ERROR 2026-07-29 19:46:27,128 phone_locking.api API [lock-device] response: 'device_brand' is a required field.",
        "INFO:DUKA:[STORE][DETAIL] body | {'user_id': 33, 'username': 'isaac', 'enterprise_code': 'TEST-002'}",
        'INFO:     172.18.0.7:38898 - "POST /api/v1/auth/login HTTP/1.0" 401 Unauthorized',
        '{"status":401,"elapsed_ms":279.5,"body":{"detail":"Invalid email or password"}}',
        "something totally unstructured a dev printed by accident",
        'whatsapp  | 2026-08-04T23:54:23.586311981Z {"type":"dm","phone":"254759856000","name":"Isaac","message":"","webhook_called":true,"response":null,"error":"Error: connect ECONNREFUSED 127.0.0.1:15000"}',
    ]

    for line in sample_lines:
        parsed = parse_log_line(line, "abc123", "django_app-django-1", "django_app")
        print(f"{parsed['level']:<8} logger={parsed['logger']!s:<20} ts={parsed['source_timestamp']!s:<32} parsed_data={parsed['parsed_data']}")