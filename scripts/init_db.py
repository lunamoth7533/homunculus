#!/usr/bin/env python3
"""
Initialize the Homunculus SQLite database.
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    HOMUNCULUS_ROOT, DB_PATH, get_project_db_path,
    ensure_project_db_initialized, detect_project_root
)

SCHEMA_PATH = HOMUNCULUS_ROOT / "scripts" / "schema.sql"


def init_database(db_path: Path = DB_PATH, schema_path: Path = SCHEMA_PATH) -> bool:
    """Initialize the database with the schema."""
    try:
        # Ensure parent directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if schema exists
        if not schema_path.exists():
            print(f"Error: Schema file not found at {schema_path}", file=sys.stderr)
            return False

        # Read schema
        schema_sql = schema_path.read_text()

        # Connect and execute schema
        conn = sqlite3.connect(db_path)
        conn.executescript(schema_sql)

        # Update initialization timestamp
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ("initialized_at", datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat())
        )

        conn.commit()
        conn.close()

        print(f"Database initialized at {db_path}")
        return True

    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return False


def check_database(db_path: Path = DB_PATH) -> dict:
    """Check database status and return info."""
    if not db_path.exists():
        return {"exists": False}

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get schema version
        cursor.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
        row = cursor.fetchone()
        schema_version = row[0] if row else "unknown"

        # Get table counts
        tables = {}
        for table in ['observations', 'gaps', 'proposals', 'capabilities', 'sessions']:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            tables[table] = cursor.fetchone()[0]

        conn.close()

        return {
            "exists": True,
            "path": str(db_path),
            "schema_version": schema_version,
            "tables": tables
        }

    except sqlite3.Error as e:
        return {"exists": True, "error": str(e)}


def reset_database(db_path: Path = DB_PATH) -> bool:
    """Reset the database (delete and reinitialize)."""
    try:
        if db_path.exists():
            db_path.unlink()
            print(f"Deleted existing database at {db_path}")
        return init_database(db_path)
    except Exception as e:
        print(f"Error resetting database: {e}", file=sys.stderr)
        return False


def init_project_database(project_path: Path) -> bool:
    """Initialize a project-scoped database."""
    try:
        success = ensure_project_db_initialized(project_path)
        if success:
            db_path = get_project_db_path(project_path)
            print(f"Project database initialized at {db_path}")
        return success
    except Exception as e:
        print(f"Error initializing project database: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Initialize Homunculus database")
    parser.add_argument("--reset", action="store_true", help="Reset existing database")
    parser.add_argument("--check", action="store_true", help="Check database status")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Database path")
    parser.add_argument("--project", type=Path, help="Initialize project-scoped database at path")
    parser.add_argument("--auto-project", action="store_true",
                        help="Auto-detect and initialize project database from current directory")

    args = parser.parse_args()

    # Handle project database initialization
    if args.project:
        if args.check:
            db_path = get_project_db_path(args.project)
            info = check_database(db_path)
            info['scope'] = 'project'
            info['project_path'] = str(args.project)
            import json
            print(json.dumps(info, indent=2))
            sys.exit(0)

        if args.reset and get_project_db_path(args.project).exists():
            get_project_db_path(args.project).unlink()
            print(f"Deleted existing project database")

        success = init_project_database(args.project)
        sys.exit(0 if success else 1)

    if args.auto_project:
        project_root = detect_project_root()
        if not project_root:
            print("Could not detect project root. Use --project <path> instead.", file=sys.stderr)
            sys.exit(1)

        if args.check:
            db_path = get_project_db_path(project_root)
            info = check_database(db_path)
            info['scope'] = 'project'
            info['project_path'] = str(project_root)
            import json
            print(json.dumps(info, indent=2))
            sys.exit(0)

        if args.reset and get_project_db_path(project_root).exists():
            get_project_db_path(project_root).unlink()
            print(f"Deleted existing project database at {project_root}")

        success = init_project_database(project_root)
        sys.exit(0 if success else 1)

    # Default global database handling
    if args.check:
        info = check_database(args.db)
        info['scope'] = 'global'
        import json
        print(json.dumps(info, indent=2))
        sys.exit(0)

    if args.reset:
        success = reset_database(args.db)
    else:
        if args.db.exists():
            print(f"Database already exists at {args.db}")
            print("Use --reset to reinitialize or --check to view status")
            sys.exit(1)
        success = init_database(args.db)

    sys.exit(0 if success else 1)
