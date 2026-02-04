#!/usr/bin/env bash
#
# Homunculus Observation Hook
# Captures Claude Code tool use events and writes to observations.jsonl
#

set -euo pipefail

# Use CLAUDE_PLUGIN_ROOT if available, otherwise fall back to ~/homunculus
HOMUNCULUS_ROOT="${CLAUDE_PLUGIN_ROOT:-${HOME}/homunculus}"
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

# Read JSON from stdin
read_input() {
    cat 2>/dev/null || echo "{}"
}

# Main observation handler
observe() {
    local event_type="$1"
    local input_json

    # Read input from stdin
    input_json=$(read_input)

    # Skip if empty
    if [[ -z "$input_json" || "$input_json" == "{}" ]]; then
        exit 0
    fi

    local session_id
    session_id=$(get_session_id)

    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    local project_path
    project_path="${PWD:-}"

    # Build observation JSON using Python for reliability
    python3 -c "
import json
import sys
import hashlib
import time

# Generate unique ID
unique = hashlib.sha256(f'{time.time()}'.encode()).hexdigest()[:16]
obs_id = f'obs-{unique}'

try:
    input_data = json.loads('''$input_json''')
except:
    input_data = {}

# Determine event type
event_type = '$event_type'
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

obs = {
    'id': obs_id,
    'timestamp': '$timestamp',
    'session_id': '$session_id',
    'project_path': '$project_path' if '$project_path' else None,
    'event_type': event_type,
    'tool_name': tool_name if tool_name else None,
    'tool_success': tool_success,
    'tool_error': tool_error,
    'raw_json': json.dumps(input_data)[:1000],
    'processed': 0
}

# Remove None values
obs = {k: v for k, v in obs.items() if v is not None}

print(json.dumps(obs))
" >> "$OBSERVATIONS_FILE" 2>/dev/null || true
}

# Handle stop event (end of session)
handle_stop() {
    local session_id
    session_id=$(get_session_id)

    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    python3 -c "
import json
import hashlib
import time

unique = hashlib.sha256(f'{time.time()}'.encode()).hexdigest()[:16]

print(json.dumps({
    'id': f'obs-{unique}',
    'timestamp': '$timestamp',
    'session_id': '$session_id',
    'event_type': 'stop',
    'processed': 0
}))
" >> "$OBSERVATIONS_FILE" 2>/dev/null || true

    # Clean up session file
    rm -f "$SESSION_FILE" 2>/dev/null || true
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
