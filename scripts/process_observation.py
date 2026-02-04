#!/usr/bin/env python3
"""
Process observation data safely - called by observe.sh.
Avoids shell interpolation vulnerabilities.
"""

import json
import sys
import os
import hashlib
import time
import re

# Patterns to redact from logged data
SENSITIVE_PATTERNS = [
    (r'(?i)(api[_-]?key|token|secret|password|credential|auth)["\']?\s*[:=]\s*["\']?[^\s"\']+', r'\1=[REDACTED]'),
    (r'(?i)authorization:\s*bearer\s+\S+', 'Authorization: Bearer [REDACTED]'),
    (r'sk-[a-zA-Z0-9]{20,}', '[API_KEY_REDACTED]'),
    (r'ghp_[a-zA-Z0-9]{36,}', '[GITHUB_TOKEN_REDACTED]'),
    (r'gho_[a-zA-Z0-9]{36,}', '[GITHUB_TOKEN_REDACTED]'),
]


def sanitize_data(data: str) -> str:
    """Remove sensitive data before logging."""
    for pattern, replacement in SENSITIVE_PATTERNS:
        data = re.sub(pattern, replacement, data)
    return data


def generate_id() -> str:
    """Generate a unique observation ID."""
    unique = hashlib.sha256(f'{time.time()}-{os.getpid()}'.encode()).hexdigest()[:16]
    return f'obs-{unique}'


def main():
    if len(sys.argv) < 5:
        print("Usage: process_observation.py <event_type> <timestamp> <session_id> <project_path>", file=sys.stderr)
        sys.exit(1)

    event_type = sys.argv[1]
    timestamp = sys.argv[2]
    session_id = sys.argv[3]
    project_path = sys.argv[4] if sys.argv[4] != "" else None

    # Read input from stdin safely
    try:
        input_json = sys.stdin.read()
        input_data = json.loads(input_json) if input_json.strip() else {}
    except json.JSONDecodeError:
        input_data = {}

    # Skip if empty
    if not input_data:
        sys.exit(0)

    # Normalize event type
    if event_type == 'pre':
        event_type = 'pre_tool'
    elif event_type == 'post':
        event_type = 'post_tool'

    # Extract tool info
    tool_name = input_data.get('tool_name', input_data.get('tool', ''))
    tool_success = None
    tool_error = None

    if event_type == 'post_tool':
        if 'error' in input_data:
            tool_success = 0
            tool_error = str(input_data.get('error', ''))[:500]
        else:
            tool_success = 1

    # Sanitize raw JSON before storing
    raw_json = sanitize_data(json.dumps(input_data))[:1000]

    obs = {
        'id': generate_id(),
        'timestamp': timestamp,
        'session_id': session_id,
        'event_type': event_type,
        'raw_json': raw_json,
        'processed': 0
    }

    if project_path:
        obs['project_path'] = project_path
    if tool_name:
        obs['tool_name'] = tool_name
    if tool_success is not None:
        obs['tool_success'] = tool_success
    if tool_error:
        obs['tool_error'] = tool_error

    # Output JSON to stdout (observe.sh will redirect to file)
    print(json.dumps(obs))


if __name__ == '__main__':
    main()
