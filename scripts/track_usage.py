#!/usr/bin/env python3
"""
Capability usage tracking for Homunculus.
Records when evolved capabilities are used.
"""

import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    get_db_connection, db_execute, get_timestamp, generate_id
)


def record_usage(
    capability_name: str,
    session_id: Optional[str] = None,
    context: Optional[str] = None
) -> bool:
    """
    Record that a capability was used.

    Args:
        capability_name: Name of the capability (or ID)
        session_id: Current session ID (optional)
        context: Additional context about usage (optional)

    Returns:
        True if recorded successfully
    """
    try:
        # Find capability by name or ID
        caps = db_execute(
            """SELECT id FROM capabilities
               WHERE name = ? OR id = ? OR id LIKE ?""",
            (capability_name, capability_name, f"{capability_name}%")
        )

        if not caps:
            return False

        capability_id = caps[0]['id']
        timestamp = get_timestamp()

        with get_db_connection() as conn:
            conn.execute(
                """INSERT INTO capability_usage (capability_id, used_at, session_id, context)
                   VALUES (?, ?, ?, ?)""",
                (capability_id, timestamp, session_id, context)
            )
            conn.commit()
        return True

    except Exception as e:
        print(f"Error recording usage: {e}", file=sys.stderr)
        return False


def get_usage_stats(capability_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get usage statistics for capabilities.

    Args:
        capability_name: Filter by capability name (optional)

    Returns:
        List of usage stats per capability
    """
    if capability_name:
        return db_execute(
            """SELECT c.name, c.capability_type, COUNT(u.id) as usage_count,
                      MAX(u.used_at) as last_used, MIN(u.used_at) as first_used
               FROM capabilities c
               LEFT JOIN capability_usage u ON c.id = u.capability_id
               WHERE c.name = ? OR c.id LIKE ?
               GROUP BY c.id
               ORDER BY usage_count DESC""",
            (capability_name, f"{capability_name}%")
        )
    else:
        return db_execute(
            """SELECT c.name, c.capability_type, COUNT(u.id) as usage_count,
                      MAX(u.used_at) as last_used, MIN(u.used_at) as first_used
               FROM capabilities c
               LEFT JOIN capability_usage u ON c.id = u.capability_id
               WHERE c.status = 'active'
               GROUP BY c.id
               ORDER BY usage_count DESC"""
        )


def detect_and_record_usage(observation: Dict[str, Any]) -> List[str]:
    """
    Analyze an observation and record usage for any matching capabilities.
    Returns list of capability names that were recorded.

    This is a heuristic approach - it looks for capability names or patterns
    in the observation that might indicate the capability was used.
    """
    recorded = []

    try:
        # Get active capabilities
        caps = db_execute(
            """SELECT id, name, capability_type FROM capabilities WHERE status = 'active'"""
        )

        if not caps:
            return []

        # Get raw observation content
        raw_json = observation.get('raw_json', '')
        tool_name = observation.get('tool_name', '')
        session_id = observation.get('session_id')

        # Check each capability
        for cap in caps:
            cap_name = cap['name'].lower()
            cap_type = cap['capability_type']

            # Check if capability name appears in observation
            if cap_name in raw_json.lower():
                if record_usage(cap['id'], session_id, f"Detected in {tool_name}"):
                    recorded.append(cap['name'])

            # For skills, check if the skill file path appears
            if cap_type == 'skill':
                skill_path = f"evolved/skills/{cap['name']}"
                if skill_path.lower() in raw_json.lower():
                    if record_usage(cap['id'], session_id, f"Skill referenced"):
                        recorded.append(cap['name'])

    except Exception as e:
        print(f"Error detecting usage: {e}", file=sys.stderr)

    return recorded


def main():
    """CLI for usage tracking."""
    import argparse

    parser = argparse.ArgumentParser(description="Track capability usage")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # record
    record_parser = subparsers.add_parser("record", help="Record capability usage")
    record_parser.add_argument("capability", help="Capability name or ID")
    record_parser.add_argument("--session", help="Session ID")
    record_parser.add_argument("--context", help="Usage context")

    # stats
    stats_parser = subparsers.add_parser("stats", help="Show usage statistics")
    stats_parser.add_argument("capability", nargs="?", help="Filter by capability")

    args = parser.parse_args()

    if args.command == "record":
        if record_usage(args.capability, args.session, args.context):
            print(f"Recorded usage for: {args.capability}")
        else:
            print(f"Failed to record usage (capability not found?)")
            return 1

    elif args.command == "stats":
        stats = get_usage_stats(args.capability)
        if not stats:
            print("No capabilities found")
            return 0

        print(f"{'CAPABILITY':<30} {'TYPE':<10} {'USES':<6} {'LAST USED':<20}")
        print("-" * 70)
        for s in stats:
            last = s['last_used'][:10] if s['last_used'] else 'Never'
            print(f"{s['name']:<30} {s['capability_type']:<10} {s['usage_count']:<6} {last:<20}")

    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
