#!/usr/bin/env bash
#
# Homunculus Observation Hook
# Captures Claude Code tool use events and writes to observations.jsonl
#
# SECURITY: Uses separate Python script to avoid shell injection vulnerabilities

set -euo pipefail

# Use CLAUDE_PLUGIN_ROOT if available, otherwise fall back to ~/homunculus
HOMUNCULUS_ROOT="${CLAUDE_PLUGIN_ROOT:-${HOME}/homunculus}"

# Validate HOMUNCULUS_ROOT exists and is a directory
if [[ ! -d "$HOMUNCULUS_ROOT" ]]; then
    exit 0  # Silently exit if not installed
fi

OBSERVATIONS_FILE="${HOMUNCULUS_ROOT}/observations/current.jsonl"
SESSION_FILE="${HOMUNCULUS_ROOT}/.current_session"
PROCESS_SCRIPT="${HOMUNCULUS_ROOT}/scripts/process_observation.py"

# Ensure observations directory exists
mkdir -p "$(dirname "$OBSERVATIONS_FILE")"

# Get or create session ID (with secure random component)
get_session_id() {
    if [[ -f "$SESSION_FILE" ]]; then
        cat "$SESSION_FILE"
    else
        local session_id
        local random_part
        # Use /dev/urandom for cryptographically secure randomness
        random_part=$(head -c 8 /dev/urandom 2>/dev/null | xxd -p 2>/dev/null || echo "$$")
        session_id="session-$(date +%Y%m%d-%H%M%S)-${random_part}"
        echo "$session_id" > "$SESSION_FILE"
        echo "$session_id"
    fi
}

# Main observation handler - uses Python script for safe processing
observe() {
    local event_type="$1"
    local session_id
    local timestamp
    local project_path

    session_id=$(get_session_id)
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    project_path="${PWD:-}"

    # Pipe stdin to Python script, which handles JSON safely
    # The Python script outputs the observation JSON to stdout
    if [[ -f "$PROCESS_SCRIPT" ]]; then
        python3 "$PROCESS_SCRIPT" "$event_type" "$timestamp" "$session_id" "$project_path" \
            >> "$OBSERVATIONS_FILE" 2>/dev/null || true
    fi
}

# Handle stop event (end of session)
handle_stop() {
    local session_id
    local timestamp
    local random_part

    session_id=$(get_session_id)
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    random_part=$(head -c 8 /dev/urandom 2>/dev/null | xxd -p 2>/dev/null || echo "$$")

    # Write stop observation directly (no user input involved)
    cat >> "$OBSERVATIONS_FILE" 2>/dev/null <<EOF || true
{"id": "obs-${random_part}", "timestamp": "${timestamp}", "session_id": "${session_id}", "event_type": "stop", "processed": 0}
EOF

    # End session in database
    python3 -c "
import sys
sys.path.insert(0, '${HOMUNCULUS_ROOT}/scripts')
from process_observation import end_session
end_session('${session_id}', '${timestamp}')
" 2>/dev/null || true

    # Clean up session file
    rm -f "$SESSION_FILE" 2>/dev/null || true
}

# Main entry point
main() {
    local event_type="${1:-}"

    case "$event_type" in
        pre|pre_tool)
            observe "pre"
            ;;
        post|post_tool)
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
