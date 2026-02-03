#!/usr/bin/env python3
"""
Homunculus core utilities.
"""

import json
import sqlite3
import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Dict, List
from contextlib import contextmanager

# Paths
HOMUNCULUS_ROOT = Path.home() / "homunculus"
DB_PATH = HOMUNCULUS_ROOT / "homunculus.db"
CONFIG_PATH = HOMUNCULUS_ROOT / "config.yaml"
OBSERVATIONS_PATH = HOMUNCULUS_ROOT / "observations" / "current.jsonl"


def generate_id(prefix: str = "id") -> str:
    """Generate a unique ID with prefix."""
    unique = hashlib.sha256(f"{datetime.now(timezone.utc).isoformat()}{uuid.uuid4()}".encode()).hexdigest()[:12]
    return f"{prefix}-{unique}"


def get_timestamp() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_config() -> Dict[str, Any]:
    """Load configuration from config.yaml."""
    if not CONFIG_PATH.exists():
        return {}

    try:
        import yaml
        return yaml.safe_load(CONFIG_PATH.read_text()) or {}
    except ImportError:
        # Fallback to basic parsing if yaml not available
        return {}
    except Exception:
        return {}


@contextmanager
def get_db_connection(db_path: Path = DB_PATH):
    """Get a database connection context manager."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def db_execute(query: str, params: tuple = (), db_path: Path = DB_PATH) -> List[Dict]:
    """Execute a query and return results as list of dicts."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def db_execute_write(query: str, params: tuple = (), db_path: Path = DB_PATH) -> int:
    """Execute a write query and return lastrowid."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, params)
        conn.commit()
        return cursor.lastrowid


def read_jsonl(file_path: Path) -> List[Dict]:
    """Read a JSONL file and return list of dicts."""
    if not file_path.exists():
        return []

    results = []
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return results


def append_jsonl(file_path: Path, data: Dict) -> None:
    """Append a dict to a JSONL file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'a') as f:
        f.write(json.dumps(data) + '\n')


def _simple_yaml_parse(text: str) -> Dict:
    """Simple YAML parser for basic key-value and list structures."""
    result = {}
    current_key = None
    current_list = None
    indent_stack = [(0, result)]

    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()

        # Skip empty lines and comments
        if not stripped or stripped.startswith('#'):
            i += 1
            continue

        # Skip document markers
        if stripped == '---':
            i += 1
            continue

        indent = len(line) - len(stripped)

        # Handle list items
        if stripped.startswith('- '):
            item_content = stripped[2:].strip()

            # Find the right container based on indent
            while indent_stack and indent_stack[-1][0] >= indent and len(indent_stack) > 1:
                indent_stack.pop()

            container = indent_stack[-1][1]

            if current_key and current_key in container:
                if not isinstance(container[current_key], list):
                    container[current_key] = []

                # Check if it's a dict item or simple value
                if ':' in item_content and not item_content.startswith('"'):
                    # Dict item in list
                    item_dict = {}
                    key, val = item_content.split(':', 1)
                    item_dict[key.strip()] = _parse_yaml_value(val.strip())
                    container[current_key].append(item_dict)
                else:
                    container[current_key].append(_parse_yaml_value(item_content))
            i += 1
            continue

        # Handle key-value pairs
        if ':' in stripped:
            colon_pos = stripped.find(':')
            key = stripped[:colon_pos].strip()
            value = stripped[colon_pos + 1:].strip()

            # Find the right container based on indent
            while indent_stack and indent_stack[-1][0] >= indent and len(indent_stack) > 1:
                indent_stack.pop()

            container = indent_stack[-1][1]

            if value:
                # Inline value
                container[key] = _parse_yaml_value(value)
            else:
                # Nested structure or list follows
                container[key] = {}
                current_key = key
                indent_stack.append((indent, container))

        i += 1

    return result


def _parse_yaml_value(value: str) -> Any:
    """Parse a YAML value string."""
    if not value:
        return None

    # Remove quotes
    if (value.startswith('"') and value.endswith('"')) or \
       (value.startswith("'") and value.endswith("'")):
        return value[1:-1]

    # Boolean
    if value.lower() == 'true':
        return True
    if value.lower() == 'false':
        return False

    # None
    if value.lower() in ('null', '~', 'none'):
        return None

    # Number
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    return value


def load_yaml_file(file_path: Path) -> Dict:
    """Load a YAML file."""
    if not file_path.exists():
        return {}

    text = file_path.read_text()

    try:
        import yaml
        return yaml.safe_load(text) or {}
    except ImportError:
        # Fallback to simple parser
        try:
            return _simple_yaml_parse(text)
        except Exception:
            return {}
    except Exception:
        return {}


def save_yaml_file(file_path: Path, data: Dict) -> None:
    """Save a dict to a YAML file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import yaml
        file_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    except ImportError:
        file_path.write_text(json.dumps(data, indent=2))


def format_table(headers: List[str], rows: List[List[str]], max_width: int = 80) -> str:
    """Format data as a simple ASCII table."""
    if not rows:
        return "No data"

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(cell)))

    # Truncate if too wide
    total = sum(widths) + len(widths) * 3
    if total > max_width:
        scale = max_width / total
        widths = [max(5, int(w * scale)) for w in widths]

    # Build table
    lines = []

    # Header
    header_line = "  ".join(h.ljust(widths[i])[:widths[i]] for i, h in enumerate(headers))
    lines.append(header_line)
    lines.append("-" * len(header_line))

    # Rows
    for row in rows:
        row_line = "  ".join(str(cell).ljust(widths[i])[:widths[i]] for i, cell in enumerate(row) if i < len(widths))
        lines.append(row_line)

    return "\n".join(lines)


def truncate_string(s: str, max_len: int = 50) -> str:
    """Truncate a string with ellipsis."""
    if len(s) <= max_len:
        return s
    return s[:max_len-3] + "..."


class HomunculusError(Exception):
    """Base exception for Homunculus errors."""
    pass


class ConfigError(HomunculusError):
    """Configuration error."""
    pass


class DatabaseError(HomunculusError):
    """Database error."""
    pass
