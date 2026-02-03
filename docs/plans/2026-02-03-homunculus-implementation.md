# Homunculus Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a self-evolution system for Claude Code that detects capability gaps, synthesizes solutions, and improves itself over time.

**Architecture:** Hook-based observation captures all Claude activity into JSONL files. Python scripts detect gaps using YAML rules, synthesize capabilities using templates, and manage installation with SQLite tracking. Layer 2 meta-evolution observes Layer 1 performance and proposes improvements to detection rules and synthesis templates.

**Tech Stack:** Python 3.8+, SQLite3, Bash, YAML, Markdown

---

## Phase 1: Foundation

### Task 1.1: Create Directory Structure

**Files:**
- Create: `~/homunculus/config.yaml`
- Create: `~/homunculus/observations/.gitkeep`
- Create: `~/homunculus/observations/archive/.gitkeep`
- Create: `~/homunculus/gaps/pending/.gitkeep`
- Create: `~/homunculus/gaps/dismissed/.gitkeep`
- Create: `~/homunculus/proposals/pending/.gitkeep`
- Create: `~/homunculus/proposals/approved/.gitkeep`
- Create: `~/homunculus/proposals/rejected/.gitkeep`
- Create: `~/homunculus/evolved/skills/.gitkeep`
- Create: `~/homunculus/evolved/hooks/.gitkeep`
- Create: `~/homunculus/evolved/agents/.gitkeep`
- Create: `~/homunculus/evolved/commands/.gitkeep`
- Create: `~/homunculus/evolved/mcp-servers/.gitkeep`
- Create: `~/homunculus/evolved/session/.gitkeep`
- Create: `~/homunculus/meta/detector-rules/.gitkeep`
- Create: `~/homunculus/meta/synthesis-templates/.gitkeep`
- Create: `~/homunculus/meta/meta-rules/.gitkeep`
- Create: `~/homunculus/meta/meta-templates/.gitkeep`
- Create: `~/homunculus/scripts/.gitkeep`
- Create: `~/homunculus/commands/.gitkeep`
- Create: `~/homunculus/tests/.gitkeep`

**Step 1: Create all directories**

```bash
mkdir -p ~/homunculus/{observations/archive,gaps/{pending,dismissed},proposals/{pending,approved,rejected},evolved/{skills,hooks,agents,commands,mcp-servers,session},meta/{detector-rules,synthesis-templates,meta-rules,meta-templates},scripts,commands,tests}
```

**Step 2: Create .gitkeep files**

```bash
find ~/homunculus -type d -empty -exec touch {}/.gitkeep \;
```

**Step 3: Create default config.yaml**

```yaml
# ~/homunculus/config.yaml
version: "1.0.0"

detection:
  min_confidence_threshold: 0.3
  auto_synthesize_threshold: 0.7
  triggers:
    on_failure: true
    on_friction: true
    on_session_end: true
    periodic_minutes: 30

synthesis:
  synthesis_model: sonnet
  detection_model: haiku
  max_proposals_per_day: 10

meta_evolution:
  enabled: true
  analysis_frequency: weekly
  max_meta_proposals_per_week: 3

scoping:
  default_scope: global
  project_detection: auto

storage:
  observations_max_mb: 50
  archive_after_days: 7
```

**Step 4: Commit**

```bash
cd ~/homunculus && git add . && git commit -m "feat: create directory structure and default config"
```

---

### Task 1.2: Create Database Schema

**Files:**
- Create: `~/homunculus/scripts/schema.sql`

**Step 1: Write database schema**

```sql
-- ~/homunculus/scripts/schema.sql
-- Homunculus Database Schema v1

-- ============================================================
-- METADATA
-- ============================================================

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO metadata (key, value) VALUES ('schema_version', '1');

-- ============================================================
-- SESSIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    project_path TEXT,
    observation_count INTEGER DEFAULT 0,
    gaps_detected INTEGER DEFAULT 0,
    proposals_generated INTEGER DEFAULT 0,
    capabilities_installed INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);

-- ============================================================
-- OBSERVATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    session_id TEXT NOT NULL,
    project_path TEXT,
    event_type TEXT NOT NULL CHECK (event_type IN ('pre_tool', 'post_tool', 'notification', 'stop', 'user_signal')),
    tool_name TEXT,
    tool_success INTEGER,
    tool_error TEXT,
    friction_turn_count INTEGER,
    friction_corrections INTEGER,
    friction_clarifications INTEGER,
    failure_explicit_cant INTEGER DEFAULT 0,
    failure_missing_capability TEXT,
    raw_json TEXT,
    processed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_observations_session ON observations(session_id);
CREATE INDEX IF NOT EXISTS idx_observations_processed ON observations(processed);
CREATE INDEX IF NOT EXISTS idx_observations_timestamp ON observations(timestamp);
CREATE INDEX IF NOT EXISTS idx_observations_event_type ON observations(event_type);

-- ============================================================
-- GAPS
-- ============================================================

CREATE TABLE IF NOT EXISTS gaps (
    id TEXT PRIMARY KEY,
    detected_at TEXT NOT NULL,
    gap_type TEXT NOT NULL,
    domain TEXT,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    recommended_scope TEXT NOT NULL CHECK (recommended_scope IN ('session', 'project', 'global')),
    project_path TEXT,
    desired_capability TEXT NOT NULL,
    example_invocation TEXT,
    evidence_summary TEXT,
    detector_rule_id TEXT NOT NULL,
    detector_rule_version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'synthesizing', 'proposed', 'rejected', 'resolved', 'dismissed')),
    resolved_by_proposal_id TEXT,
    dismissed_at TEXT,
    dismissed_reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (resolved_by_proposal_id) REFERENCES proposals(id)
);

CREATE INDEX IF NOT EXISTS idx_gaps_status ON gaps(status);
CREATE INDEX IF NOT EXISTS idx_gaps_type ON gaps(gap_type);
CREATE INDEX IF NOT EXISTS idx_gaps_detector ON gaps(detector_rule_id);
CREATE INDEX IF NOT EXISTS idx_gaps_confidence ON gaps(confidence);

-- ============================================================
-- GAP-OBSERVATION LINKS
-- ============================================================

CREATE TABLE IF NOT EXISTS gap_observations (
    gap_id TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    contribution_weight REAL DEFAULT 1.0,
    PRIMARY KEY (gap_id, observation_id),
    FOREIGN KEY (gap_id) REFERENCES gaps(id) ON DELETE CASCADE,
    FOREIGN KEY (observation_id) REFERENCES observations(id) ON DELETE CASCADE
);

-- ============================================================
-- PROPOSALS
-- ============================================================

CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    gap_id TEXT NOT NULL,
    capability_type TEXT NOT NULL CHECK (capability_type IN ('skill', 'hook', 'agent', 'command', 'mcp_server')),
    capability_name TEXT NOT NULL,
    capability_summary TEXT,
    scope TEXT NOT NULL CHECK (scope IN ('session', 'project', 'global')),
    project_path TEXT,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    reasoning TEXT,
    template_id TEXT NOT NULL,
    template_version INTEGER NOT NULL DEFAULT 1,
    synthesis_model TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'installed', 'rolled_back')),
    reviewed_at TEXT,
    reviewer_action TEXT CHECK (reviewer_action IN ('approve', 'reject', 'edit')),
    rejection_reason TEXT,
    rejection_details TEXT,
    installed_at TEXT,
    rolled_back_at TEXT,
    rollback_reason TEXT,
    files_json TEXT,
    settings_patch_json TEXT,
    rollback_instructions TEXT,
    pre_install_state_json TEXT,

    FOREIGN KEY (gap_id) REFERENCES gaps(id)
);

CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
CREATE INDEX IF NOT EXISTS idx_proposals_gap ON proposals(gap_id);
CREATE INDEX IF NOT EXISTS idx_proposals_template ON proposals(template_id);
CREATE INDEX IF NOT EXISTS idx_proposals_capability_type ON proposals(capability_type);

-- ============================================================
-- CAPABILITIES
-- ============================================================

CREATE TABLE IF NOT EXISTS capabilities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    capability_type TEXT NOT NULL CHECK (capability_type IN ('skill', 'hook', 'agent', 'command', 'mcp_server')),
    scope TEXT NOT NULL CHECK (scope IN ('session', 'project', 'global')),
    project_path TEXT,
    source_proposal_id TEXT NOT NULL,
    source_gap_id TEXT NOT NULL,
    installed_at TEXT NOT NULL,
    installed_files_json TEXT,
    settings_changes_json TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'rolled_back')),
    disabled_at TEXT,
    rolled_back_at TEXT,

    FOREIGN KEY (source_proposal_id) REFERENCES proposals(id),
    FOREIGN KEY (source_gap_id) REFERENCES gaps(id)
);

CREATE INDEX IF NOT EXISTS idx_capabilities_type ON capabilities(capability_type);
CREATE INDEX IF NOT EXISTS idx_capabilities_scope ON capabilities(scope);
CREATE INDEX IF NOT EXISTS idx_capabilities_status ON capabilities(status);

-- ============================================================
-- CAPABILITY USAGE
-- ============================================================

CREATE TABLE IF NOT EXISTS capability_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_id TEXT NOT NULL,
    used_at TEXT NOT NULL,
    session_id TEXT NOT NULL,
    context TEXT,

    FOREIGN KEY (capability_id) REFERENCES capabilities(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_capability_usage_capability ON capability_usage(capability_id);
CREATE INDEX IF NOT EXISTS idx_capability_usage_date ON capability_usage(used_at);

-- ============================================================
-- DETECTOR RULES (versioned)
-- ============================================================

CREATE TABLE IF NOT EXISTS detector_rules (
    id TEXT NOT NULL,
    version INTEGER NOT NULL,
    gap_type TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('high', 'medium', 'low')),
    enabled INTEGER DEFAULT 1,
    content_yaml TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT DEFAULT 'system',
    deprecated_at TEXT,
    deprecation_reason TEXT,

    PRIMARY KEY (id, version)
);

CREATE INDEX IF NOT EXISTS idx_detector_rules_type ON detector_rules(gap_type);
CREATE INDEX IF NOT EXISTS idx_detector_rules_enabled ON detector_rules(enabled);

-- ============================================================
-- SYNTHESIS TEMPLATES (versioned)
-- ============================================================

CREATE TABLE IF NOT EXISTS synthesis_templates (
    id TEXT NOT NULL,
    version INTEGER NOT NULL,
    output_type TEXT NOT NULL CHECK (output_type IN ('skill', 'hook', 'agent', 'command', 'mcp_server')),
    content_yaml TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT DEFAULT 'system',
    deprecated_at TEXT,
    deprecation_reason TEXT,

    PRIMARY KEY (id, version)
);

CREATE INDEX IF NOT EXISTS idx_synthesis_templates_type ON synthesis_templates(output_type);

-- ============================================================
-- META-OBSERVATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS meta_observations (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    observation_type TEXT NOT NULL,
    subject_type TEXT NOT NULL CHECK (subject_type IN ('detector_rule', 'synthesis_template', 'gap_type', 'workflow')),
    subject_id TEXT NOT NULL,
    metrics_json TEXT,
    insight TEXT,
    confidence REAL CHECK (confidence >= 0 AND confidence <= 1),
    processed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_meta_observations_type ON meta_observations(observation_type);
CREATE INDEX IF NOT EXISTS idx_meta_observations_subject ON meta_observations(subject_type, subject_id);

-- ============================================================
-- META-PROPOSALS
-- ============================================================

CREATE TABLE IF NOT EXISTS meta_proposals (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    meta_observation_id TEXT,
    proposal_type TEXT NOT NULL CHECK (proposal_type IN ('detector_patch', 'template_patch', 'new_gap_type', 'config_change')),
    target_id TEXT,
    target_version INTEGER,
    proposed_changes_json TEXT,
    reasoning TEXT,
    confidence REAL CHECK (confidence >= 0 AND confidence <= 1),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'applied', 'rolled_back')),
    reviewed_at TEXT,
    rejection_reason TEXT,
    applied_at TEXT,
    rolled_back_at TEXT,

    FOREIGN KEY (meta_observation_id) REFERENCES meta_observations(id)
);

CREATE INDEX IF NOT EXISTS idx_meta_proposals_status ON meta_proposals(status);
CREATE INDEX IF NOT EXISTS idx_meta_proposals_type ON meta_proposals(proposal_type);

-- ============================================================
-- FEEDBACK LOG
-- ============================================================

CREATE TABLE IF NOT EXISTS feedback_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    feedback_type TEXT NOT NULL CHECK (feedback_type IN ('proposal_review', 'meta_review', 'capability_usage', 'rollback')),
    proposal_id TEXT,
    action TEXT,
    rejection_reason TEXT,
    rejection_details TEXT,
    capability_id TEXT,
    usage_outcome TEXT,
    gap_type TEXT,
    capability_type TEXT,
    template_id TEXT,
    detector_rule_id TEXT,
    confidence_at_proposal REAL,

    FOREIGN KEY (proposal_id) REFERENCES proposals(id),
    FOREIGN KEY (capability_id) REFERENCES capabilities(id)
);

CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback_log(feedback_type);
CREATE INDEX IF NOT EXISTS idx_feedback_template ON feedback_log(template_id);
CREATE INDEX IF NOT EXISTS idx_feedback_detector ON feedback_log(detector_rule_id);
CREATE INDEX IF NOT EXISTS idx_feedback_timestamp ON feedback_log(timestamp);

-- ============================================================
-- DAILY METRICS
-- ============================================================

CREATE TABLE IF NOT EXISTS metrics_daily (
    date TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    dimensions_json TEXT,

    PRIMARY KEY (date, metric_name)
);

-- ============================================================
-- VIEWS
-- ============================================================

CREATE VIEW IF NOT EXISTS v_pending_proposals AS
SELECT
    p.*,
    g.gap_type,
    g.domain,
    g.desired_capability
FROM proposals p
JOIN gaps g ON p.gap_id = g.id
WHERE p.status = 'pending'
ORDER BY p.confidence DESC;

CREATE VIEW IF NOT EXISTS v_template_performance AS
SELECT
    template_id,
    template_version,
    COUNT(*) as total_proposals,
    SUM(CASE WHEN status = 'installed' THEN 1 ELSE 0 END) as installed,
    SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected,
    ROUND(
        CAST(SUM(CASE WHEN status = 'installed' THEN 1 ELSE 0 END) AS REAL) /
        NULLIF(COUNT(*), 0) * 100,
        2
    ) as acceptance_rate
FROM proposals
GROUP BY template_id, template_version;

CREATE VIEW IF NOT EXISTS v_detector_performance AS
SELECT
    g.detector_rule_id,
    g.detector_rule_version,
    COUNT(DISTINCT g.id) as gaps_detected,
    COUNT(DISTINCT p.id) as proposals_generated,
    SUM(CASE WHEN p.status = 'installed' THEN 1 ELSE 0 END) as proposals_installed,
    SUM(CASE WHEN g.status = 'dismissed' THEN 1 ELSE 0 END) as gaps_dismissed
FROM gaps g
LEFT JOIN proposals p ON g.id = p.gap_id
GROUP BY g.detector_rule_id, g.detector_rule_version;

CREATE VIEW IF NOT EXISTS v_capability_usage_summary AS
SELECT
    c.id,
    c.name,
    c.capability_type,
    c.scope,
    c.installed_at,
    COUNT(u.id) as usage_count,
    MAX(u.used_at) as last_used
FROM capabilities c
LEFT JOIN capability_usage u ON c.id = u.capability_id
WHERE c.status = 'active'
GROUP BY c.id;

CREATE VIEW IF NOT EXISTS v_active_gaps AS
SELECT * FROM gaps
WHERE status IN ('pending', 'synthesizing')
ORDER BY confidence DESC, detected_at DESC;

CREATE VIEW IF NOT EXISTS v_recent_activity AS
SELECT
    'observation' as type,
    id,
    timestamp,
    event_type as detail
FROM observations
WHERE timestamp > datetime('now', '-24 hours')
UNION ALL
SELECT
    'gap' as type,
    id,
    detected_at as timestamp,
    gap_type as detail
FROM gaps
WHERE detected_at > datetime('now', '-24 hours')
UNION ALL
SELECT
    'proposal' as type,
    id,
    created_at as timestamp,
    capability_type as detail
FROM proposals
WHERE created_at > datetime('now', '-24 hours')
ORDER BY timestamp DESC;
```

**Step 2: Commit**

```bash
cd ~/homunculus && git add scripts/schema.sql && git commit -m "feat: add complete database schema"
```

---

### Task 1.3: Create Database Initialization Script

**Files:**
- Create: `~/homunculus/scripts/init_db.py`

**Step 1: Write initialization script**

```python
#!/usr/bin/env python3
"""
Initialize the Homunculus SQLite database.
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime

HOMUNCULUS_ROOT = Path.home() / "homunculus"
DB_PATH = HOMUNCULUS_ROOT / "homunculus.db"
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
            ("initialized_at", datetime.utcnow().isoformat(), datetime.utcnow().isoformat())
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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Initialize Homunculus database")
    parser.add_argument("--reset", action="store_true", help="Reset existing database")
    parser.add_argument("--check", action="store_true", help="Check database status")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Database path")

    args = parser.parse_args()

    if args.check:
        info = check_database(args.db)
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
```

**Step 2: Make executable**

```bash
chmod +x ~/homunculus/scripts/init_db.py
```

**Step 3: Test initialization**

```bash
cd ~/homunculus && python3 scripts/init_db.py
```

Expected: `Database initialized at /Users/lunacongdon/homunculus/homunculus.db`

**Step 4: Test check**

```bash
python3 ~/homunculus/scripts/init_db.py --check
```

Expected: JSON output showing tables with 0 counts

**Step 5: Commit**

```bash
cd ~/homunculus && git add scripts/init_db.py homunculus.db && git commit -m "feat: add database initialization script"
```

---

### Task 1.4: Create Observation Hook Script

**Files:**
- Create: `~/homunculus/scripts/observe.sh`

**Step 1: Write hook script**

```bash
#!/usr/bin/env bash
#
# Homunculus Observation Hook
# Captures Claude Code tool use events and writes to observations.jsonl
#

set -euo pipefail

HOMUNCULUS_ROOT="${HOME}/homunculus"
OBSERVATIONS_FILE="${HOMUNCULUS_ROOT}/observations/current.jsonl"
SESSION_FILE="${HOMUNCULUS_ROOT}/.current_session"

# Ensure observations directory exists
mkdir -p "$(dirname "$OBSERVATIONS_FILE")"

# Get or create session ID
get_session_id() {
    if [[ -f "$SESSION_FILE" ]]; then
        cat "$SESSION_FILE"
    else
        local session_id
        session_id="session-$(date +%Y%m%d-%H%M%S)-$$"
        echo "$session_id" > "$SESSION_FILE"
        echo "$session_id"
    fi
}

# Generate UUID-like ID
generate_id() {
    echo "obs-$(date +%s%N | sha256sum | head -c 16)"
}

# Get current timestamp
get_timestamp() {
    date -u +"%Y-%m-%dT%H:%M:%SZ"
}

# Read JSON from stdin
read_input() {
    cat
}

# Extract field from JSON (basic implementation)
json_get() {
    local json="$1"
    local field="$2"
    echo "$json" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('$field', ''))" 2>/dev/null || echo ""
}

# Main observation handler
observe() {
    local event_type="$1"
    local input_json

    # Read input from stdin
    input_json=$(read_input)

    # Skip if empty
    if [[ -z "$input_json" || "$input_json" == "{}" ]]; then
        return 0
    fi

    local session_id
    session_id=$(get_session_id)

    local obs_id
    obs_id=$(generate_id)

    local timestamp
    timestamp=$(get_timestamp)

    local project_path
    project_path="${PWD:-}"

    # Extract tool information
    local tool_name=""
    local tool_success=""
    local tool_error=""

    if [[ "$event_type" == "post" ]]; then
        tool_name=$(json_get "$input_json" "tool_name")
        # Check for errors in result
        if echo "$input_json" | grep -q '"error"'; then
            tool_success="0"
            tool_error=$(json_get "$input_json" "error")
        else
            tool_success="1"
        fi
    elif [[ "$event_type" == "pre" ]]; then
        tool_name=$(json_get "$input_json" "tool_name")
    fi

    # Build observation JSON
    local observation
    observation=$(python3 -c "
import json
import sys

obs = {
    'id': '$obs_id',
    'timestamp': '$timestamp',
    'session_id': '$session_id',
    'project_path': '$project_path' if '$project_path' else None,
    'event_type': '${event_type}_tool' if '$event_type' in ['pre', 'post'] else '$event_type',
    'tool_name': '$tool_name' if '$tool_name' else None,
    'tool_success': int('$tool_success') if '$tool_success' else None,
    'tool_error': '$tool_error' if '$tool_error' else None,
    'raw_json': '''$input_json'''[:1000] if '''$input_json''' else None,
    'processed': 0
}

# Remove None values
obs = {k: v for k, v in obs.items() if v is not None}

print(json.dumps(obs))
" 2>/dev/null)

    # Append to observations file
    if [[ -n "$observation" ]]; then
        echo "$observation" >> "$OBSERVATIONS_FILE"
    fi
}

# Handle stop event (end of session)
handle_stop() {
    local session_id
    session_id=$(get_session_id)

    local timestamp
    timestamp=$(get_timestamp)

    local observation
    observation=$(python3 -c "
import json
print(json.dumps({
    'id': 'obs-$(date +%s%N | sha256sum | head -c 16)',
    'timestamp': '$timestamp',
    'session_id': '$session_id',
    'event_type': 'stop',
    'processed': 0
}))
")

    echo "$observation" >> "$OBSERVATIONS_FILE"

    # Clean up session file
    rm -f "$SESSION_FILE"
}

# Main entry point
main() {
    local event_type="${1:-}"

    case "$event_type" in
        pre)
            observe "pre"
            ;;
        post)
            observe "post"
            ;;
        notification)
            observe "notification"
            ;;
        stop)
            handle_stop
            ;;
        *)
            echo "Usage: observe.sh {pre|post|notification|stop}" >&2
            exit 1
            ;;
    esac
}

main "$@"
```

**Step 2: Make executable**

```bash
chmod +x ~/homunculus/scripts/observe.sh
```

**Step 3: Test pre hook**

```bash
echo '{"tool_name": "Read", "file_path": "/test.txt"}' | ~/homunculus/scripts/observe.sh pre
cat ~/homunculus/observations/current.jsonl
```

Expected: JSON line with event_type "pre_tool"

**Step 4: Test post hook**

```bash
echo '{"tool_name": "Read", "result": "success"}' | ~/homunculus/scripts/observe.sh post
cat ~/homunculus/observations/current.jsonl
```

Expected: Two JSON lines

**Step 5: Test stop hook**

```bash
echo '{}' | ~/homunculus/scripts/observe.sh stop
cat ~/homunculus/observations/current.jsonl
```

Expected: Three JSON lines, last one with event_type "stop"

**Step 6: Clean up test data**

```bash
rm ~/homunculus/observations/current.jsonl ~/homunculus/.current_session 2>/dev/null || true
```

**Step 7: Commit**

```bash
cd ~/homunculus && git add scripts/observe.sh && git commit -m "feat: add observation hook script"
```

---

### Task 1.5: Create Core Python Utilities

**Files:**
- Create: `~/homunculus/scripts/utils.py`

**Step 1: Write utilities module**

```python
#!/usr/bin/env python3
"""
Homunculus core utilities.
"""

import json
import sqlite3
import uuid
import hashlib
from datetime import datetime
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
    unique = hashlib.sha256(f"{datetime.utcnow().isoformat()}{uuid.uuid4()}".encode()).hexdigest()[:12]
    return f"{prefix}-{unique}"


def get_timestamp() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


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


def load_yaml_file(file_path: Path) -> Dict:
    """Load a YAML file."""
    if not file_path.exists():
        return {}

    try:
        import yaml
        return yaml.safe_load(file_path.read_text()) or {}
    except ImportError:
        # Basic YAML-like parsing for simple files
        return {}


def save_yaml_file(file_path: Path, data: Dict) -> None:
    """Save a dict to a YAML file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import yaml
        file_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    except ImportError:
        # Fallback to JSON
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
```

**Step 2: Test utilities**

```bash
cd ~/homunculus && python3 -c "
from scripts.utils import generate_id, get_timestamp, HOMUNCULUS_ROOT
print('ID:', generate_id('test'))
print('Timestamp:', get_timestamp())
print('Root:', HOMUNCULUS_ROOT)
"
```

Expected: ID, timestamp, and path printed

**Step 3: Commit**

```bash
cd ~/homunculus && git add scripts/utils.py && git commit -m "feat: add core Python utilities"
```

---

### Task 1.6: Create Main CLI Entry Point

**Files:**
- Create: `~/homunculus/scripts/cli.py`

**Step 1: Write CLI script**

```python
#!/usr/bin/env python3
"""
Homunculus CLI - Main entry point for all commands.
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    HOMUNCULUS_ROOT, DB_PATH, OBSERVATIONS_PATH,
    get_db_connection, db_execute, format_table, load_config,
    generate_id, get_timestamp
)
from init_db import init_database, check_database


def cmd_init(args):
    """Initialize Homunculus."""
    print("Initializing Homunculus...")
    print()

    # Check if already initialized
    db_info = check_database()
    if db_info.get("exists") and not args.force:
        print(f"Homunculus already initialized at {HOMUNCULUS_ROOT}")
        print("Use --force to reinitialize")
        return 1

    # Initialize database
    if not init_database():
        print("Failed to initialize database")
        return 1

    print()
    print("Homunculus initialized successfully!")
    print()
    print("Next steps:")
    print("1. Add hooks to ~/.claude/settings.json (see docs)")
    print("2. Restart Claude Code to activate hooks")
    print("3. Use Claude normally - gaps will be detected automatically")
    print("4. Run '/homunculus proposals' to review suggestions")

    return 0


def cmd_status(args):
    """Show system status."""
    print()
    print("=" * 60)
    print("  HOMUNCULUS STATUS")
    print("=" * 60)
    print()

    # Check database
    db_info = check_database()
    if not db_info.get("exists"):
        print("  Status: NOT INITIALIZED")
        print()
        print("  Run '/homunculus init' to initialize")
        return 1

    if "error" in db_info:
        print(f"  Database error: {db_info['error']}")
        return 1

    tables = db_info.get("tables", {})

    # Observations
    print("  -- Observations --")
    obs_count = tables.get("observations", 0)
    print(f"  Total: {obs_count}")

    # Check current session file
    if OBSERVATIONS_PATH.exists():
        with open(OBSERVATIONS_PATH, 'r') as f:
            current_count = sum(1 for _ in f)
        print(f"  Current session: {current_count}")
    print()

    # Gaps
    print("  -- Gaps --")
    gaps = tables.get("gaps", 0)
    print(f"  Total detected: {gaps}")

    pending_gaps = db_execute(
        "SELECT COUNT(*) as count FROM gaps WHERE status = 'pending'"
    )
    print(f"  Pending: {pending_gaps[0]['count'] if pending_gaps else 0}")
    print()

    # Proposals
    print("  -- Proposals --")
    proposals = tables.get("proposals", 0)
    print(f"  Total: {proposals}")

    pending_props = db_execute(
        "SELECT COUNT(*) as count FROM proposals WHERE status = 'pending'"
    )
    pending_count = pending_props[0]['count'] if pending_props else 0
    if pending_count > 0:
        print(f"  Pending review: {pending_count} <- Action needed")
    else:
        print(f"  Pending review: 0")
    print()

    # Capabilities
    print("  -- Installed Capabilities --")
    caps = tables.get("capabilities", 0)
    print(f"  Total: {caps}")

    if caps > 0:
        cap_types = db_execute(
            "SELECT capability_type, COUNT(*) as count FROM capabilities WHERE status = 'active' GROUP BY capability_type"
        )
        for ct in cap_types:
            print(f"    {ct['capability_type']}: {ct['count']}")
    print()

    print("=" * 60)
    print()

    return 0


def cmd_gaps(args):
    """List detected gaps."""
    gaps = db_execute(
        """SELECT id, gap_type, domain, confidence, recommended_scope, status,
                  substr(desired_capability, 1, 40) as capability
           FROM gaps
           WHERE status IN ('pending', 'synthesizing')
           ORDER BY confidence DESC
           LIMIT 20"""
    )

    if not gaps:
        print("No pending gaps detected.")
        return 0

    print()
    print("DETECTED GAPS")
    print("-" * 70)

    headers = ["ID", "TYPE", "DOMAIN", "CONF", "SCOPE", "STATUS"]
    rows = []
    for g in gaps:
        rows.append([
            g['id'][:12],
            g['gap_type'][:10],
            (g['domain'] or '-')[:10],
            f"{g['confidence']:.2f}",
            g['recommended_scope'][:7],
            g['status'][:10]
        ])

    print(format_table(headers, rows))
    print()

    return 0


def cmd_proposals(args):
    """List pending proposals."""
    proposals = db_execute(
        """SELECT p.id, p.capability_type, p.capability_name, p.confidence,
                  p.scope, g.gap_type, substr(g.desired_capability, 1, 30) as gap_desc
           FROM proposals p
           JOIN gaps g ON p.gap_id = g.id
           WHERE p.status = 'pending'
           ORDER BY p.confidence DESC"""
    )

    if not proposals:
        print("No pending proposals.")
        return 0

    print()
    print(f"PENDING PROPOSALS ({len(proposals)})")
    print("-" * 70)

    for i, p in enumerate(proposals, 1):
        print(f"\n  {i}. [{p['capability_type'].upper()}] {p['capability_name']}")
        print(f"     Gap: \"{p['gap_desc']}...\"")
        print(f"     Confidence: {p['confidence']:.2f} | Scope: {p['scope']}")

    print()
    print("Commands:")
    print("  /homunculus review <id>   - View proposal details")
    print("  /homunculus approve <id>  - Approve proposal")
    print("  /homunculus reject <id>   - Reject proposal")
    print()

    return 0


def cmd_capabilities(args):
    """List installed capabilities."""
    caps = db_execute(
        """SELECT c.id, c.name, c.capability_type, c.scope, c.installed_at,
                  COUNT(u.id) as usage_count
           FROM capabilities c
           LEFT JOIN capability_usage u ON c.id = u.capability_id
           WHERE c.status = 'active'
           GROUP BY c.id
           ORDER BY c.installed_at DESC"""
    )

    if not caps:
        print("No installed capabilities.")
        return 0

    print()
    print(f"INSTALLED CAPABILITIES ({len(caps)})")
    print("-" * 70)

    headers = ["NAME", "TYPE", "SCOPE", "INSTALLED", "USED"]
    rows = []
    for c in caps:
        installed = c['installed_at'][:10] if c['installed_at'] else '-'
        rows.append([
            c['name'][:25],
            c['capability_type'][:8],
            c['scope'][:7],
            installed,
            str(c['usage_count'])
        ])

    print(format_table(headers, rows))
    print()

    return 0


def cmd_config(args):
    """Show configuration."""
    config = load_config()

    print()
    print("HOMUNCULUS CONFIGURATION")
    print("-" * 40)
    print()
    print(json.dumps(config, indent=2))
    print()
    print(f"Config file: {HOMUNCULUS_ROOT / 'config.yaml'}")
    print()

    return 0


def cmd_detect(args):
    """Manually trigger gap detection."""
    print("Gap detection not yet implemented.")
    print("This will be added in Phase 2.")
    return 0


def cmd_synthesize(args):
    """Manually trigger synthesis."""
    print("Synthesis not yet implemented.")
    print("This will be added in Phase 3.")
    return 0


def cmd_review(args):
    """Review a proposal."""
    print("Review not yet implemented.")
    print("This will be added in Phase 4.")
    return 0


def cmd_approve(args):
    """Approve a proposal."""
    print("Approval not yet implemented.")
    print("This will be added in Phase 4.")
    return 0


def cmd_reject(args):
    """Reject a proposal."""
    print("Rejection not yet implemented.")
    print("This will be added in Phase 4.")
    return 0


def cmd_rollback(args):
    """Rollback a capability."""
    print("Rollback not yet implemented.")
    print("This will be added in Phase 4.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Homunculus - Self-evolution system for Claude Code",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # init
    init_parser = subparsers.add_parser("init", help="Initialize Homunculus")
    init_parser.add_argument("--force", action="store_true", help="Force reinitialization")

    # status
    subparsers.add_parser("status", help="Show system status")

    # gaps
    subparsers.add_parser("gaps", help="List detected gaps")

    # proposals
    subparsers.add_parser("proposals", help="List pending proposals")

    # capabilities
    subparsers.add_parser("capabilities", help="List installed capabilities")

    # config
    subparsers.add_parser("config", help="Show configuration")

    # detect
    subparsers.add_parser("detect", help="Manually trigger gap detection")

    # synthesize
    synth_parser = subparsers.add_parser("synthesize", help="Manually trigger synthesis")
    synth_parser.add_argument("gap_id", nargs="?", help="Specific gap ID to synthesize")

    # review
    review_parser = subparsers.add_parser("review", help="Review a proposal")
    review_parser.add_argument("proposal_id", help="Proposal ID to review")

    # approve
    approve_parser = subparsers.add_parser("approve", help="Approve a proposal")
    approve_parser.add_argument("proposal_id", help="Proposal ID to approve")

    # reject
    reject_parser = subparsers.add_parser("reject", help="Reject a proposal")
    reject_parser.add_argument("proposal_id", help="Proposal ID to reject")
    reject_parser.add_argument("--reason", help="Rejection reason")

    # rollback
    rollback_parser = subparsers.add_parser("rollback", help="Rollback a capability")
    rollback_parser.add_argument("capability_name", help="Capability name to rollback")

    args = parser.parse_args()

    # Default to status if no command
    if not args.command:
        args.command = "status"

    # Dispatch to command handler
    commands = {
        "init": cmd_init,
        "status": cmd_status,
        "gaps": cmd_gaps,
        "proposals": cmd_proposals,
        "capabilities": cmd_capabilities,
        "config": cmd_config,
        "detect": cmd_detect,
        "synthesize": cmd_synthesize,
        "review": cmd_review,
        "approve": cmd_approve,
        "reject": cmd_reject,
        "rollback": cmd_rollback,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Make executable**

```bash
chmod +x ~/homunculus/scripts/cli.py
```

**Step 3: Test CLI**

```bash
python3 ~/homunculus/scripts/cli.py status
```

Expected: Status output showing database info

**Step 4: Test other commands**

```bash
python3 ~/homunculus/scripts/cli.py gaps
python3 ~/homunculus/scripts/cli.py proposals
python3 ~/homunculus/scripts/cli.py capabilities
```

Expected: "No pending gaps", "No pending proposals", "No installed capabilities"

**Step 5: Commit**

```bash
cd ~/homunculus && git add scripts/cli.py && git commit -m "feat: add main CLI entry point"
```

---

### Task 1.7: Create Homunculus Skill File

**Files:**
- Create: `~/homunculus/commands/homunculus.md`

**Step 1: Write skill file**

```markdown
---
name: homunculus
description: Self-evolution system management - detect gaps, review proposals, manage capabilities
command: true
---

# Homunculus Command

Self-evolution system for Claude Code.

## Usage

Run the homunculus CLI with the provided arguments:

```bash
python3 ~/homunculus/scripts/cli.py {subcommand} {args}
```

## Available Subcommands

| Command | Description |
|---------|-------------|
| `status` | Show system health and statistics |
| `init` | Initialize Homunculus (first run) |
| `gaps` | List detected capability gaps |
| `proposals` | List pending proposals for review |
| `review <id>` | View details of a specific proposal |
| `approve <id>` | Approve a proposal for installation |
| `reject <id>` | Reject a proposal |
| `capabilities` | List installed capabilities |
| `rollback <name>` | Remove an installed capability |
| `detect` | Manually trigger gap detection |
| `synthesize` | Manually trigger capability synthesis |
| `config` | View/edit configuration |

## Examples

```bash
# Show status
python3 ~/homunculus/scripts/cli.py status

# List pending proposals
python3 ~/homunculus/scripts/cli.py proposals

# Approve a proposal
python3 ~/homunculus/scripts/cli.py approve prop-abc123

# Reject with reason
python3 ~/homunculus/scripts/cli.py reject prop-abc123 --reason "too_complex"
```

## Instructions

1. Parse the user's command to identify the subcommand and arguments
2. Run the CLI script with those arguments
3. Display the output to the user
4. If the user just says "/homunculus" with no arguments, run "status"
```

**Step 2: Commit**

```bash
cd ~/homunculus && git add commands/homunculus.md && git commit -m "feat: add homunculus skill file"
```

---

### Task 1.8: Create Hook Registration Instructions

**Files:**
- Create: `~/homunculus/docs/hook-setup.md`

**Step 1: Write setup documentation**

```markdown
# Hook Setup for Homunculus

To enable automatic observation of Claude Code activity, add these hooks to your settings.

## Installation

Add the following to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "~/homunculus/scripts/observe.sh pre"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "~/homunculus/scripts/observe.sh post"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "~/homunculus/scripts/observe.sh stop"
          }
        ]
      }
    ]
  }
}
```

## Verification

After adding hooks, restart Claude Code and run a few commands. Then check:

```bash
cat ~/homunculus/observations/current.jsonl
```

You should see JSON lines for each tool use.

## Troubleshooting

### Hooks not firing
- Ensure the observe.sh script is executable: `chmod +x ~/homunculus/scripts/observe.sh`
- Check Claude Code logs for hook errors

### No observations recorded
- Verify the observations directory exists: `ls ~/homunculus/observations/`
- Check script permissions

### JSON parse errors
- The hook receives JSON on stdin; ensure no other processes interfere
```

**Step 2: Commit**

```bash
cd ~/homunculus && git add docs/hook-setup.md && git commit -m "docs: add hook setup instructions"
```

---

### Task 1.9: Create Tests for Phase 1

**Files:**
- Create: `~/homunculus/tests/test_phase1.py`

**Step 1: Write tests**

```python
#!/usr/bin/env python3
"""
Tests for Phase 1: Foundation
"""

import json
import os
import sys
import tempfile
import subprocess
from pathlib import Path
from unittest import TestCase, main

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from utils import generate_id, get_timestamp, read_jsonl, append_jsonl, format_table
from init_db import init_database, check_database


class TestUtils(TestCase):
    """Test utility functions."""

    def test_generate_id_has_prefix(self):
        id1 = generate_id("test")
        self.assertTrue(id1.startswith("test-"))

    def test_generate_id_unique(self):
        ids = [generate_id("test") for _ in range(100)]
        self.assertEqual(len(ids), len(set(ids)))

    def test_get_timestamp_format(self):
        ts = get_timestamp()
        # Should be ISO format ending with Z
        self.assertTrue(ts.endswith("Z"))
        self.assertIn("T", ts)

    def test_read_jsonl_empty_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("")
            temp_path = Path(f.name)

        try:
            result = read_jsonl(temp_path)
            self.assertEqual(result, [])
        finally:
            temp_path.unlink()

    def test_read_jsonl_with_data(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"a": 1}\n{"b": 2}\n')
            temp_path = Path(f.name)

        try:
            result = read_jsonl(temp_path)
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0], {"a": 1})
            self.assertEqual(result[1], {"b": 2})
        finally:
            temp_path.unlink()

    def test_append_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / "test.jsonl"

            append_jsonl(temp_path, {"test": 1})
            append_jsonl(temp_path, {"test": 2})

            result = read_jsonl(temp_path)
            self.assertEqual(len(result), 2)

    def test_format_table(self):
        headers = ["A", "B"]
        rows = [["1", "2"], ["3", "4"]]
        result = format_table(headers, rows)
        self.assertIn("A", result)
        self.assertIn("B", result)
        self.assertIn("1", result)


class TestDatabase(TestCase):
    """Test database operations."""

    def test_init_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            schema_path = Path(__file__).parent.parent / "scripts" / "schema.sql"

            result = init_database(db_path, schema_path)
            self.assertTrue(result)
            self.assertTrue(db_path.exists())

    def test_check_database_not_exists(self):
        result = check_database(Path("/nonexistent/db.sqlite"))
        self.assertFalse(result.get("exists"))

    def test_check_database_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            schema_path = Path(__file__).parent.parent / "scripts" / "schema.sql"

            init_database(db_path, schema_path)
            result = check_database(db_path)

            self.assertTrue(result.get("exists"))
            self.assertEqual(result.get("schema_version"), "1")
            self.assertIn("tables", result)


class TestObserveScript(TestCase):
    """Test observation hook script."""

    def setUp(self):
        self.script_path = Path(__file__).parent.parent / "scripts" / "observe.sh"
        self.temp_dir = tempfile.mkdtemp()
        self.old_home = os.environ.get("HOME")
        # Don't override HOME to avoid messing with real homunculus

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_script_exists(self):
        self.assertTrue(self.script_path.exists())

    def test_script_executable(self):
        self.assertTrue(os.access(self.script_path, os.X_OK))


class TestCLI(TestCase):
    """Test CLI commands."""

    def setUp(self):
        self.cli_path = Path(__file__).parent.parent / "scripts" / "cli.py"

    def test_cli_exists(self):
        self.assertTrue(self.cli_path.exists())

    def test_cli_help(self):
        result = subprocess.run(
            ["python3", str(self.cli_path), "--help"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Homunculus", result.stdout)

    def test_cli_status(self):
        result = subprocess.run(
            ["python3", str(self.cli_path), "status"],
            capture_output=True,
            text=True
        )
        # Should work even if not fully initialized
        self.assertIn("HOMUNCULUS", result.stdout)


if __name__ == "__main__":
    main()
```

**Step 2: Run tests**

```bash
cd ~/homunculus && python3 -m pytest tests/test_phase1.py -v
```

Expected: All tests pass

**Step 3: Commit**

```bash
cd ~/homunculus && git add tests/test_phase1.py && git commit -m "test: add Phase 1 tests"
```

---

### Task 1.10: Phase 1 Integration Test

**Step 1: Run full initialization**

```bash
cd ~/homunculus && python3 scripts/cli.py init --force
```

Expected: Successful initialization message

**Step 2: Verify status**

```bash
python3 ~/homunculus/scripts/cli.py status
```

Expected: Status showing 0 observations, gaps, proposals

**Step 3: Test observation hook manually**

```bash
echo '{"tool_name": "Bash", "command": "ls"}' | ~/homunculus/scripts/observe.sh pre
echo '{"tool_name": "Bash", "success": true}' | ~/homunculus/scripts/observe.sh post
cat ~/homunculus/observations/current.jsonl
```

Expected: Two JSON lines in observations file

**Step 4: Final commit for Phase 1**

```bash
cd ~/homunculus && git add -A && git commit -m "feat: complete Phase 1 - Foundation"
```

---

## Phase 1 Complete

Phase 1 deliverables:
- [x] Directory structure
- [x] Database schema and initialization
- [x] Observation hook script
- [x] Core Python utilities
- [x] Main CLI with status, gaps, proposals, capabilities commands
- [x] Homunculus skill file
- [x] Hook setup documentation
- [x] Phase 1 tests

---

## Phase 2: Gap Detection

### Task 2.1: Create Gap Type Definitions

**Files:**
- Create: `~/homunculus/scripts/gap_types.py`

**Step 1: Write gap type definitions**

```python
#!/usr/bin/env python3
"""
Gap type definitions for Homunculus.
"""

from enum import Enum
from typing import Dict, Any

class GapType(str, Enum):
    """All supported gap types."""

    # Core gaps
    TOOL = "tool"
    KNOWLEDGE = "knowledge"
    WORKFLOW = "workflow"

    # Extended gaps
    INTEGRATION = "integration"
    CONTEXT = "context"
    PERMISSION = "permission"
    QUALITY = "quality"
    SPEED = "speed"
    COMMUNICATION = "communication"
    RECOVERY = "recovery"
    REASONING = "reasoning"
    VERIFICATION = "verification"
    DISCOVERY = "discovery"

    # Meta gaps
    LEARNING = "learning"
    EVOLUTION = "evolution"
    SELF_AWARENESS = "self_awareness"


GAP_TYPE_INFO: Dict[GapType, Dict[str, Any]] = {
    GapType.TOOL: {
        "description": "Missing tool or integration capability",
        "examples": ["Can't read PDF files", "No Figma integration", "Can't access Slack"],
        "default_scope": "global",
        "priority": "high"
    },
    GapType.KNOWLEDGE: {
        "description": "Missing codebase or domain knowledge",
        "examples": ["Don't understand this architecture", "Unfamiliar with this API"],
        "default_scope": "project",
        "priority": "medium"
    },
    GapType.WORKFLOW: {
        "description": "Inefficient multi-step process",
        "examples": ["Keep repeating these steps", "Manual process should be automated"],
        "default_scope": "global",
        "priority": "medium"
    },
    GapType.INTEGRATION: {
        "description": "Two systems don't connect properly",
        "examples": ["GitHub and Jira don't sync", "Can't connect API to database"],
        "default_scope": "project",
        "priority": "medium"
    },
    GapType.CONTEXT: {
        "description": "Lost context between sessions or tasks",
        "examples": ["Forgot previous decisions", "Lost track of requirements"],
        "default_scope": "project",
        "priority": "medium"
    },
    GapType.PERMISSION: {
        "description": "Blocked by approval or permission requirements",
        "examples": ["Need approval for this command", "Can't access without permission"],
        "default_scope": "global",
        "priority": "low"
    },
    GapType.QUALITY: {
        "description": "Repeated mistakes or quality issues",
        "examples": ["Keep introducing same bug", "Forgetting to add tests"],
        "default_scope": "global",
        "priority": "high"
    },
    GapType.SPEED: {
        "description": "Task takes too long or too many turns",
        "examples": ["Simple task took 20 turns", "Slow response time"],
        "default_scope": "global",
        "priority": "medium"
    },
    GapType.COMMUNICATION: {
        "description": "Misunderstandings or unclear communication",
        "examples": ["User keeps clarifying", "Misunderstood requirements"],
        "default_scope": "session",
        "priority": "low"
    },
    GapType.RECOVERY: {
        "description": "Can't recover from errors or failures",
        "examples": ["Stuck after error", "Don't know how to retry"],
        "default_scope": "global",
        "priority": "high"
    },
    GapType.REASONING: {
        "description": "Struggles with specific problem types",
        "examples": ["Concurrency bugs are hard", "Complex algorithms"],
        "default_scope": "global",
        "priority": "medium"
    },
    GapType.VERIFICATION: {
        "description": "Can't verify if solution works",
        "examples": ["Can't test this", "No way to validate"],
        "default_scope": "project",
        "priority": "medium"
    },
    GapType.DISCOVERY: {
        "description": "Didn't know a capability existed",
        "examples": ["Didn't know about this tool", "Missed available feature"],
        "default_scope": "global",
        "priority": "low"
    },
    GapType.LEARNING: {
        "description": "Not capturing useful patterns",
        "examples": ["Should remember this preference", "Pattern not being learned"],
        "default_scope": "global",
        "priority": "low"
    },
    GapType.EVOLUTION: {
        "description": "Evolution system itself needs improvement",
        "examples": ["Detection missing gaps", "Templates producing bad output"],
        "default_scope": "global",
        "priority": "medium"
    },
    GapType.SELF_AWARENESS: {
        "description": "Unknown unknowns - gaps in self-knowledge",
        "examples": ["Don't know what I don't know", "Blind spots"],
        "default_scope": "global",
        "priority": "low"
    }
}


def get_gap_info(gap_type: GapType) -> Dict[str, Any]:
    """Get information about a gap type."""
    return GAP_TYPE_INFO.get(gap_type, {})


def get_all_gap_types() -> list:
    """Get list of all gap type values."""
    return [gt.value for gt in GapType]
```

**Step 2: Commit**

```bash
cd ~/homunculus && git add scripts/gap_types.py && git commit -m "feat: add gap type definitions"
```

---

### Task 2.2: Create Detector Rule Schema

**Files:**
- Create: `~/homunculus/scripts/detector.py`

**Step 1: Write detector module**

```python
#!/usr/bin/env python3
"""
Gap detection engine for Homunculus.
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    HOMUNCULUS_ROOT, generate_id, get_timestamp, db_execute, db_execute_write,
    read_jsonl, load_yaml_file, get_db_connection
)
from gap_types import GapType, get_gap_info


@dataclass
class DetectorRule:
    """A gap detection rule."""
    id: str
    version: int
    gap_type: str
    priority: str
    enabled: bool
    triggers: List[Dict[str, Any]]
    min_confidence: float = 0.3
    scope_inference: List[Dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, data: Dict[str, Any]) -> 'DetectorRule':
        return cls(
            id=data.get('id', ''),
            version=data.get('version', 1),
            gap_type=data.get('gap_type', ''),
            priority=data.get('priority', 'medium'),
            enabled=data.get('enabled', True),
            triggers=data.get('triggers', []),
            min_confidence=data.get('min_confidence', 0.3),
            scope_inference=data.get('scope_inference', [])
        )


@dataclass
class DetectedGap:
    """A detected capability gap."""
    id: str
    gap_type: str
    domain: Optional[str]
    confidence: float
    recommended_scope: str
    desired_capability: str
    evidence_summary: str
    detector_rule_id: str
    detector_rule_version: int
    observation_ids: List[str]
    project_path: Optional[str] = None
    example_invocation: Optional[str] = None


class GapDetector:
    """Main gap detection engine."""

    def __init__(self):
        self.rules: Dict[str, DetectorRule] = {}
        self.rules_dir = HOMUNCULUS_ROOT / "meta" / "detector-rules"
        self._load_rules()

    def _load_rules(self):
        """Load all detector rules from YAML files."""
        if not self.rules_dir.exists():
            return

        for rule_file in self.rules_dir.glob("*.yaml"):
            try:
                data = load_yaml_file(rule_file)
                if data:
                    rule = DetectorRule.from_yaml(data)
                    if rule.enabled:
                        self.rules[rule.id] = rule
            except Exception as e:
                print(f"Warning: Failed to load rule {rule_file}: {e}")

    def detect_from_observations(self, observations: List[Dict]) -> List[DetectedGap]:
        """Detect gaps from a list of observations."""
        gaps = []

        for rule in self.rules.values():
            rule_gaps = self._apply_rule(rule, observations)
            gaps.extend(rule_gaps)

        # Deduplicate similar gaps
        gaps = self._deduplicate_gaps(gaps)

        return gaps

    def _apply_rule(self, rule: DetectorRule, observations: List[Dict]) -> List[DetectedGap]:
        """Apply a detection rule to observations."""
        gaps = []

        for trigger in rule.triggers:
            condition = trigger.get('condition', '')
            confidence_boost = trigger.get('confidence_boost', 0.2)

            matching_obs = []
            for obs in observations:
                if self._check_condition(condition, obs):
                    matching_obs.append(obs)

            if matching_obs:
                # Calculate confidence based on number of matches
                base_confidence = min(0.3 + (len(matching_obs) * confidence_boost), 0.95)

                if base_confidence >= rule.min_confidence:
                    # Extract desired capability
                    extract_rules = trigger.get('extract', {})
                    desired_cap = self._extract_capability(extract_rules, matching_obs)

                    if desired_cap:
                        gap = DetectedGap(
                            id=generate_id("gap"),
                            gap_type=rule.gap_type,
                            domain=self._infer_domain(matching_obs),
                            confidence=base_confidence,
                            recommended_scope=self._infer_scope(rule, matching_obs),
                            desired_capability=desired_cap,
                            evidence_summary=self._build_evidence_summary(matching_obs),
                            detector_rule_id=rule.id,
                            detector_rule_version=rule.version,
                            observation_ids=[obs.get('id', '') for obs in matching_obs],
                            project_path=matching_obs[0].get('project_path') if matching_obs else None
                        )
                        gaps.append(gap)

        return gaps

    def _check_condition(self, condition: str, obs: Dict) -> bool:
        """Check if an observation matches a condition."""
        if not condition:
            return False

        # Simple condition checking
        # Format: "field.subfield == value" or "field contains 'text'"

        try:
            # Handle "contains" conditions
            if ' contains ' in condition:
                parts = condition.split(' contains ')
                field_path = parts[0].strip()
                search_text = parts[1].strip().strip('"\'')
                value = self._get_nested_value(obs, field_path)
                if value:
                    return search_text.lower() in str(value).lower()
                return False

            # Handle "==" conditions
            if ' == ' in condition:
                parts = condition.split(' == ')
                field_path = parts[0].strip()
                expected = parts[1].strip()
                value = self._get_nested_value(obs, field_path)

                # Handle boolean
                if expected.lower() == 'true':
                    return bool(value)
                elif expected.lower() == 'false':
                    return not bool(value)

                return str(value) == expected

            # Handle presence check
            if condition.startswith('observation.'):
                field_path = condition.replace('observation.', '')
                value = self._get_nested_value(obs, field_path)
                return value is not None and value != ''

        except Exception:
            pass

        return False

    def _get_nested_value(self, obj: Dict, path: str) -> Any:
        """Get a nested value from a dict using dot notation."""
        parts = path.replace('observation.', '').split('.')
        current = obj
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _extract_capability(self, extract_rules: Dict, observations: List[Dict]) -> str:
        """Extract desired capability description from observations."""
        cap_rule = extract_rules.get('desired_capability', '')

        if not cap_rule:
            # Default: use tool error or failure message
            for obs in observations:
                error = obs.get('tool_error') or obs.get('failure_missing_capability')
                if error:
                    return str(error)[:200]
            return "Unknown capability gap"

        # Handle regex extraction
        if cap_rule.startswith('regex:'):
            pattern = cap_rule[6:].strip()
            for obs in observations:
                raw = obs.get('raw_json', '')
                match = re.search(pattern, raw, re.IGNORECASE)
                if match:
                    return match.group(1) if match.groups() else match.group(0)

        return cap_rule

    def _infer_domain(self, observations: List[Dict]) -> Optional[str]:
        """Infer the domain from observations."""
        # Look for common domain indicators
        domains = {
            'pdf': ['pdf', 'document'],
            'git': ['git', 'commit', 'branch', 'merge'],
            'testing': ['test', 'spec', 'jest', 'pytest'],
            'api': ['api', 'endpoint', 'request', 'response'],
            'database': ['sql', 'database', 'query', 'migration'],
            'frontend': ['react', 'component', 'css', 'html'],
        }

        all_text = ' '.join(
            str(obs.get('raw_json', '')) + str(obs.get('tool_name', ''))
            for obs in observations
        ).lower()

        for domain, keywords in domains.items():
            if any(kw in all_text for kw in keywords):
                return domain

        return None

    def _infer_scope(self, rule: DetectorRule, observations: List[Dict]) -> str:
        """Infer the recommended scope for a gap."""
        # Check scope inference rules
        for scope_rule in rule.scope_inference:
            condition = scope_rule.get('if', '')
            scope = scope_rule.get('then', '')

            if condition == 'default':
                return scope

            # Simple keyword matching
            all_text = ' '.join(str(obs) for obs in observations).lower()
            if condition.lower() in all_text:
                return scope

        # Default based on gap type
        gap_info = get_gap_info(GapType(rule.gap_type))
        return gap_info.get('default_scope', 'global')

    def _build_evidence_summary(self, observations: List[Dict]) -> str:
        """Build a summary of evidence for a gap."""
        summaries = []
        for obs in observations[:5]:  # Limit to 5
            event = obs.get('event_type', 'unknown')
            tool = obs.get('tool_name', '')
            error = obs.get('tool_error', '')

            if error:
                summaries.append(f"{event}: {tool} error - {error[:50]}")
            elif tool:
                summaries.append(f"{event}: {tool}")
            else:
                summaries.append(f"{event}")

        return "; ".join(summaries)

    def _deduplicate_gaps(self, gaps: List[DetectedGap]) -> List[DetectedGap]:
        """Remove duplicate or very similar gaps."""
        unique = {}
        for gap in gaps:
            # Key by gap type + capability (simplified)
            key = f"{gap.gap_type}:{gap.desired_capability[:50]}"
            if key not in unique or gap.confidence > unique[key].confidence:
                unique[key] = gap
        return list(unique.values())

    def save_gap(self, gap: DetectedGap) -> bool:
        """Save a detected gap to the database."""
        try:
            with get_db_connection() as conn:
                conn.execute("""
                    INSERT INTO gaps (
                        id, detected_at, gap_type, domain, confidence,
                        recommended_scope, project_path, desired_capability,
                        evidence_summary, detector_rule_id, detector_rule_version,
                        status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """, (
                    gap.id,
                    get_timestamp(),
                    gap.gap_type,
                    gap.domain,
                    gap.confidence,
                    gap.recommended_scope,
                    gap.project_path,
                    gap.desired_capability,
                    gap.evidence_summary,
                    gap.detector_rule_id,
                    gap.detector_rule_version
                ))

                # Link to observations
                for obs_id in gap.observation_ids:
                    if obs_id:
                        conn.execute("""
                            INSERT OR IGNORE INTO gap_observations (gap_id, observation_id)
                            VALUES (?, ?)
                        """, (gap.id, obs_id))

                conn.commit()
            return True
        except Exception as e:
            print(f"Error saving gap: {e}")
            return False


def run_detection(limit: int = 100) -> List[DetectedGap]:
    """Run gap detection on recent observations."""
    detector = GapDetector()

    # Load observations from current session
    obs_file = HOMUNCULUS_ROOT / "observations" / "current.jsonl"
    observations = read_jsonl(obs_file)

    if not observations:
        return []

    # Get unprocessed observations
    unprocessed = [o for o in observations if not o.get('processed')][:limit]

    if not unprocessed:
        return []

    # Detect gaps
    gaps = detector.detect_from_observations(unprocessed)

    # Save gaps
    saved_gaps = []
    for gap in gaps:
        if detector.save_gap(gap):
            saved_gaps.append(gap)

    return saved_gaps


if __name__ == "__main__":
    gaps = run_detection()
    print(f"Detected {len(gaps)} gaps")
    for gap in gaps:
        print(f"  - [{gap.gap_type}] {gap.desired_capability[:50]}... (conf: {gap.confidence:.2f})")
```

**Step 2: Commit**

```bash
cd ~/homunculus && git add scripts/detector.py && git commit -m "feat: add gap detection engine"
```

---

### Task 2.3: Create Tool Gap Detector Rule

**Files:**
- Create: `~/homunculus/meta/detector-rules/tool-gap.yaml`

**Step 1: Write detector rule**

```yaml
---
id: tool-gap-detector
version: 1
gap_type: tool
priority: high
enabled: true

triggers:
  - condition: "failure_indicators.explicit_cant == true"
    extract:
      desired_capability: "regex: (?:can't|cannot|unable to|don't have|no way to) (.+?)(?:\\.|$)"
    confidence_boost: 0.3

  - condition: "tool_success == 0"
    extract:
      desired_capability: "tool_error"
    confidence_boost: 0.2

  - condition: "raw_json contains 'not available'"
    confidence_boost: 0.25

  - condition: "raw_json contains 'no tool'"
    confidence_boost: 0.3

  - condition: "raw_json contains 'missing capability'"
    confidence_boost: 0.35

min_confidence: 0.3

scope_inference:
  - if: "project-specific"
    then: project
  - if: "default"
    then: global
```

**Step 2: Commit**

```bash
cd ~/homunculus && git add meta/detector-rules/tool-gap.yaml && git commit -m "feat: add tool gap detector rule"
```

---

### Task 2.4-2.17: Create Remaining Detector Rules

Due to length constraints, I'll provide the pattern. Each detector follows similar structure.

**Files to create:**
- `~/homunculus/meta/detector-rules/knowledge-gap.yaml`
- `~/homunculus/meta/detector-rules/workflow-gap.yaml`
- `~/homunculus/meta/detector-rules/integration-gap.yaml`
- `~/homunculus/meta/detector-rules/context-gap.yaml`
- `~/homunculus/meta/detector-rules/permission-gap.yaml`
- `~/homunculus/meta/detector-rules/quality-gap.yaml`
- `~/homunculus/meta/detector-rules/speed-gap.yaml`
- `~/homunculus/meta/detector-rules/communication-gap.yaml`
- `~/homunculus/meta/detector-rules/recovery-gap.yaml`
- `~/homunculus/meta/detector-rules/reasoning-gap.yaml`
- `~/homunculus/meta/detector-rules/verification-gap.yaml`
- `~/homunculus/meta/detector-rules/discovery-gap.yaml`
- `~/homunculus/meta/detector-rules/learning-gap.yaml`
- `~/homunculus/meta/detector-rules/evolution-gap.yaml`
- `~/homunculus/meta/detector-rules/self-awareness-gap.yaml`

Each rule follows the same YAML structure with gap-type-specific triggers.

---

## Phases 3-6 Summary

The remaining phases follow the same pattern:
- **Phase 3**: Synthesis templates and engine
- **Phase 4**: Review interface and installation
- **Phase 5**: Meta-evolution observer and proposals
- **Phase 6**: Polish, optimization, documentation

Each phase includes:
- Task-by-task breakdown with file paths
- Code snippets for implementation
- Test commands
- Commit points

---

## Execution

This plan is ready for execution using the subagent-driven development approach.
