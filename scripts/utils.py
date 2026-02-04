#!/usr/bin/env python3
"""
Homunculus core utilities.
"""

import os
import json
import logging
import sqlite3
import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Dict, List
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Paths - use CLAUDE_PLUGIN_ROOT if available (for plugin mode), otherwise ~/homunculus
HOMUNCULUS_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path.home() / "homunculus"))
DB_PATH = HOMUNCULUS_ROOT / "homunculus.db"
CONFIG_PATH = HOMUNCULUS_ROOT / "config.yaml"
OBSERVATIONS_PATH = HOMUNCULUS_ROOT / "observations" / "current.jsonl"

# Project database directory name
PROJECT_DB_DIR = ".homunculus"
PROJECT_DB_NAME = "homunculus.db"


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
        logger.debug("PyYAML not available, config loading limited")
        return {}
    except Exception as e:
        logger.warning(f"Failed to load config from {CONFIG_PATH}: {e}")
        return {}


@contextmanager
def get_db_connection(db_path: Path = DB_PATH):
    """Get a database connection context manager with integrity features enabled."""
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    # Enable foreign key enforcement
    conn.execute("PRAGMA foreign_keys = ON")
    # Use WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode = WAL")
    # Set busy timeout to 5 seconds
    conn.execute("PRAGMA busy_timeout = 5000")
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
    """Append a dict to a JSONL file with file locking for concurrent safety."""
    import fcntl

    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'a') as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(json.dumps(data) + '\n')
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


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
        except Exception as e:
            logger.warning(f"Failed to parse YAML file {file_path} with fallback parser: {e}")
            return {}
    except Exception as e:
        logger.warning(f"Failed to parse YAML file {file_path}: {e}")
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


# =============================================================================
# Project-scoped database support
# =============================================================================

def get_project_db_path(project_path: str | Path) -> Path:
    """
    Get the database path for a specific project.
    Project databases are stored in .homunculus/homunculus.db within the project.
    """
    project = Path(project_path)
    return project / PROJECT_DB_DIR / PROJECT_DB_NAME


def detect_project_root(start_path: str | Path = None) -> Optional[Path]:
    """
    Detect the project root by looking for common markers.
    Walks up from start_path looking for .git, package.json, etc.
    """
    if start_path is None:
        start_path = Path.cwd()

    current = Path(start_path).resolve()
    markers = ['.git', 'package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod', '.homunculus']

    while current != current.parent:
        for marker in markers:
            if (current / marker).exists():
                return current
        current = current.parent

    return None


def get_effective_db_path(
    scope: str = None,
    project_path: str | Path = None,
    auto_detect: bool = True
) -> Path:
    """
    Get the effective database path based on scope and config.

    Args:
        scope: 'global', 'project', or None to use config default
        project_path: Explicit project path (required if scope='project' and no auto-detect)
        auto_detect: Whether to auto-detect project root if not specified

    Returns:
        Path to the appropriate database
    """
    # Load config to get defaults
    config = load_config()
    scoping_config = config.get('scoping', {})

    # Determine effective scope
    if scope is None:
        scope = scoping_config.get('default_scope', 'global')

    if scope == 'global':
        return DB_PATH

    if scope == 'project':
        # Determine project path
        if project_path:
            project = Path(project_path)
        elif auto_detect and scoping_config.get('project_detection', 'auto') == 'auto':
            project = detect_project_root()
        else:
            project = None

        if project:
            return get_project_db_path(project)

    # Fallback to global
    return DB_PATH


def ensure_project_db_initialized(project_path: str | Path) -> bool:
    """
    Ensure a project database exists and is initialized.
    Creates the .homunculus directory and database if needed.

    Returns True if database is ready, False on error.
    """
    project = Path(project_path)
    db_dir = project / PROJECT_DB_DIR
    db_path = db_dir / PROJECT_DB_NAME

    # Create directory if needed
    db_dir.mkdir(parents=True, exist_ok=True)

    # Add .gitignore to keep project DB private
    gitignore_path = db_dir / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text("# Homunculus project database\n*.db\n*.db-journal\n")

    # Check if DB already exists and is valid
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
            row = cursor.fetchone()
            conn.close()
            if row:
                return True  # DB exists and has schema
        except sqlite3.Error:
            pass  # DB exists but may be corrupted, reinitialize

    # Initialize the database
    schema_path = HOMUNCULUS_ROOT / "scripts" / "schema.sql"
    if not schema_path.exists():
        return False

    try:
        conn = sqlite3.connect(db_path)
        conn.executescript(schema_path.read_text())

        # Mark as project-scoped
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ("initialized_at", now, now)
        )
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ("scope", "project", now)
        )
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ("project_path", str(project), now)
        )

        conn.commit()
        conn.close()
        return True
    except sqlite3.Error:
        return False


def list_project_databases() -> List[Dict[str, Any]]:
    """
    List all known project databases.
    Checks recent project paths from session history.
    """
    project_dbs = []

    try:
        # Get unique project paths from sessions
        rows = db_execute(
            """SELECT DISTINCT project_path FROM sessions
               WHERE project_path IS NOT NULL AND project_path != ''
               ORDER BY started_at DESC LIMIT 50"""
        )

        for row in rows:
            project_path = Path(row['project_path'])
            db_path = get_project_db_path(project_path)

            if db_path.exists():
                try:
                    with get_db_connection(db_path) as conn:
                        # Get some stats
                        cursor = conn.execute("SELECT COUNT(*) FROM gaps WHERE status = 'pending'")
                        pending_gaps = cursor.fetchone()[0]
                        cursor = conn.execute("SELECT COUNT(*) FROM capabilities WHERE status = 'active'")
                        capabilities = cursor.fetchone()[0]

                    project_dbs.append({
                        'project_path': str(project_path),
                        'db_path': str(db_path),
                        'pending_gaps': pending_gaps,
                        'capabilities': capabilities
                    })
                except sqlite3.Error:
                    pass
    except Exception:
        pass

    return project_dbs


class HomunculusError(Exception):
    """Base exception for Homunculus errors."""
    pass


class ConfigError(HomunculusError):
    """Configuration error."""
    pass


class DatabaseError(HomunculusError):
    """Database error."""
    pass
