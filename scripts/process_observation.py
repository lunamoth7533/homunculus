#!/usr/bin/env python3
"""
Process observation data safely - called by observe.sh.
Avoids shell interpolation vulnerabilities.

Error handling strategy:
- Never crash (would break Claude Code hooks)
- Log errors to file for debugging
- Graceful degradation on failures
"""

import json
import sys
import os
import hashlib
import time
import re
import logging
import sqlite3
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Dict, Any

# Determine paths
HOMUNCULUS_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path.home() / "homunculus"))
LOG_DIR = HOMUNCULUS_ROOT / "logs"
LOG_FILE = LOG_DIR / "observations.log"
DB_PATH = HOMUNCULUS_ROOT / "homunculus.db"

# Patterns to redact from logged data
SENSITIVE_PATTERNS = [
    (r'(?i)(api[_-]?key|token|secret|password|credential|auth)["\']?\s*[:=]\s*["\']?[^\s"\']+', r'\1=[REDACTED]'),
    (r'(?i)authorization:\s*bearer\s+\S+', 'Authorization: Bearer [REDACTED]'),
    (r'sk-[a-zA-Z0-9]{20,}', '[API_KEY_REDACTED]'),
    (r'ghp_[a-zA-Z0-9]{36,}', '[GITHUB_TOKEN_REDACTED]'),
    (r'gho_[a-zA-Z0-9]{36,}', '[GITHUB_TOKEN_REDACTED]'),
    (r'xox[baprs]-[a-zA-Z0-9-]+', '[SLACK_TOKEN_REDACTED]'),
    (r'(?i)aws[_-]?secret[_-]?access[_-]?key["\']?\s*[:=]\s*["\']?[^\s"\']+', 'AWS_SECRET=[REDACTED]'),
]


def ensure_session_exists(session_id: str, timestamp: str, project_path: Optional[str] = None) -> bool:
    """
    Ensure session exists in database, creating it if necessary.
    Returns True if session was created (first observation), False if it already existed.
    """
    if not DB_PATH.exists():
        return False

    try:
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        cursor = conn.cursor()

        # Check if session exists
        cursor.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        existing = cursor.fetchone()

        if existing:
            # Session exists, increment observation count
            cursor.execute(
                "UPDATE sessions SET observation_count = observation_count + 1 WHERE id = ?",
                (session_id,)
            )
            conn.commit()
            conn.close()
            return False
        else:
            # Create new session
            cursor.execute(
                """INSERT INTO sessions (id, started_at, project_path, observation_count)
                   VALUES (?, ?, ?, 1)""",
                (session_id, timestamp, project_path)
            )
            conn.commit()
            conn.close()
            return True

    except Exception as e:
        # Log but don't crash
        try:
            logger = logging.getLogger("homunculus.observation")
            logger.warning(f"Error tracking session: {e}")
        except Exception:
            pass
        return False


def end_session(session_id: str, timestamp: str) -> bool:
    """Mark a session as ended in the database."""
    if not DB_PATH.exists():
        return False

    try:
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ? AND ended_at IS NULL",
            (timestamp, session_id)
        )
        conn.commit()
        conn.close()
        return True

    except Exception as e:
        try:
            logger = logging.getLogger("homunculus.observation")
            logger.warning(f"Error ending session: {e}")
        except Exception:
            pass
        return False


def setup_logging() -> logging.Logger:
    """Set up logging with rotation."""
    logger = logging.getLogger("homunculus.observation")

    # Only configure if not already configured
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)

        try:
            # Ensure log directory exists
            LOG_DIR.mkdir(parents=True, exist_ok=True)

            # Rotating file handler: 1MB max, keep 3 backups
            file_handler = RotatingFileHandler(
                LOG_FILE,
                maxBytes=1_000_000,
                backupCount=3,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s'
            ))
            logger.addHandler(file_handler)
        except Exception:
            # If we can't set up file logging, use null handler
            logger.addHandler(logging.NullHandler())

    return logger


# Initialize logger at module level
logger = setup_logging()


def sanitize_data(data: str) -> str:
    """Remove sensitive data before logging."""
    try:
        for pattern, replacement in SENSITIVE_PATTERNS:
            data = re.sub(pattern, replacement, data)
        return data
    except Exception as e:
        logger.warning(f"Error sanitizing data: {e}")
        return "[SANITIZATION_ERROR]"


def generate_id() -> str:
    """Generate a unique observation ID."""
    try:
        unique = hashlib.sha256(f'{time.time()}-{os.getpid()}'.encode()).hexdigest()[:16]
        return f'obs-{unique}'
    except Exception as e:
        logger.warning(f"Error generating ID: {e}")
        # Fallback to timestamp-based ID
        return f'obs-{int(time.time() * 1000)}'


def parse_input() -> Dict[str, Any]:
    """Safely parse input from stdin."""
    try:
        input_json = sys.stdin.read()
        if not input_json or not input_json.strip():
            return {}
        return json.loads(input_json)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON decode error: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error reading stdin: {e}")
        return {}


def extract_tool_info(event_type: str, input_data: Dict[str, Any]) -> tuple:
    """Extract tool information from input data."""
    tool_name = ""
    tool_success = None
    tool_error = None

    try:
        tool_name = input_data.get('tool_name', input_data.get('tool', ''))

        if event_type == 'post_tool':
            if 'error' in input_data:
                tool_success = 0
                error_val = input_data.get('error', '')
                tool_error = str(error_val)[:500] if error_val else None
            else:
                tool_success = 1
    except Exception as e:
        logger.warning(f"Error extracting tool info: {e}")

    return tool_name, tool_success, tool_error


def build_observation(
    event_type: str,
    timestamp: str,
    session_id: str,
    project_path: Optional[str],
    input_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Build the observation dictionary."""

    tool_name, tool_success, tool_error = extract_tool_info(event_type, input_data)

    # Sanitize raw JSON before storing
    try:
        raw_json = sanitize_data(json.dumps(input_data))[:1000]
    except Exception as e:
        logger.warning(f"Error serializing raw_json: {e}")
        raw_json = "{}"

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

    return obs


def main():
    """Main entry point with comprehensive error handling."""
    try:
        # Validate arguments
        if len(sys.argv) < 5:
            logger.error(f"Insufficient arguments: {sys.argv}")
            # Exit silently to not break hooks
            sys.exit(0)

        event_type = sys.argv[1]
        timestamp = sys.argv[2]
        session_id = sys.argv[3]
        project_path = sys.argv[4] if sys.argv[4] != "" else None

        logger.debug(f"Processing {event_type} event for session {session_id[:12]}...")

        # Read input from stdin safely
        input_data = parse_input()

        # Skip if empty (this is normal for some events)
        if not input_data:
            logger.debug("Empty input data, skipping")
            sys.exit(0)

        # Normalize event type
        if event_type == 'pre':
            event_type = 'pre_tool'
        elif event_type == 'post':
            event_type = 'post_tool'

        # Track session in database (creates on first observation)
        is_new_session = ensure_session_exists(session_id, timestamp, project_path)
        if is_new_session:
            logger.info(f"New session started: {session_id}")

        # Build observation
        obs = build_observation(event_type, timestamp, session_id, project_path, input_data)

        # Output JSON to stdout (observe.sh will redirect to file)
        print(json.dumps(obs))

        # Try to detect capability usage (non-blocking)
        try:
            from track_usage import detect_and_record_usage
            used = detect_and_record_usage(obs)
            if used:
                logger.debug(f"Detected usage of capabilities: {used}")
        except Exception as e:
            logger.debug(f"Usage detection skipped: {e}")

        logger.debug(f"Observation {obs['id']} processed successfully")

    except Exception as e:
        # Log the error but don't crash
        logger.error(f"Unhandled error in process_observation: {e}", exc_info=True)
        # Exit cleanly to not break hooks
        sys.exit(0)


if __name__ == '__main__':
    main()
