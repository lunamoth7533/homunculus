#!/usr/bin/env python3
"""
Periodic detection trigger for Homunculus.
Runs gap detection if enough time has passed since last run.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    get_db_connection, db_execute, load_config, get_timestamp
)


def get_last_detection_time() -> datetime:
    """Get timestamp of last detection run."""
    try:
        result = db_execute(
            "SELECT value FROM metadata WHERE key = 'last_detection_time'"
        )
        if result:
            return datetime.fromisoformat(result[0]['value'].replace('Z', '+00:00'))
    except Exception:
        pass

    # Default to epoch if no previous run
    return datetime.min.replace(tzinfo=timezone.utc)


def set_last_detection_time(timestamp: str = None) -> bool:
    """Record current time as last detection time."""
    if timestamp is None:
        timestamp = get_timestamp()

    try:
        with get_db_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO metadata (key, value, updated_at)
                   VALUES ('last_detection_time', ?, ?)""",
                (timestamp, timestamp)
            )
            conn.commit()
        return True
    except Exception:
        return False


def should_run_detection() -> bool:
    """Check if detection should run based on periodic_minutes config."""
    config = load_config()
    detection_config = config.get('detection', {})
    periodic_minutes = detection_config.get('periodic_minutes', 30)

    if periodic_minutes <= 0:
        return False

    last_run = get_last_detection_time()
    now = datetime.now(timezone.utc)
    elapsed = now - last_run

    return elapsed >= timedelta(minutes=periodic_minutes)


def run_periodic_detection() -> dict:
    """
    Run detection if periodic interval has passed.
    Returns dict with results.
    """
    if not should_run_detection():
        return {
            'ran': False,
            'reason': 'Not enough time elapsed since last detection'
        }

    # Record that we're starting detection
    set_last_detection_time()

    try:
        from detector import run_detection
        gaps = run_detection()

        return {
            'ran': True,
            'gaps_detected': len(gaps),
            'gaps': [
                {
                    'id': g.id,
                    'type': g.gap_type,
                    'confidence': g.confidence
                }
                for g in gaps
            ]
        }
    except Exception as e:
        return {
            'ran': True,
            'error': str(e),
            'gaps_detected': 0
        }


def main():
    """Run periodic detection and print results."""
    import argparse

    parser = argparse.ArgumentParser(description="Periodic gap detection")
    parser.add_argument("--force", action="store_true", help="Force detection even if interval hasn't passed")
    parser.add_argument("--status", action="store_true", help="Show last detection time")

    args = parser.parse_args()

    if args.status:
        last_run = get_last_detection_time()
        config = load_config()
        periodic_minutes = config.get('detection', {}).get('periodic_minutes', 30)

        if last_run == datetime.min.replace(tzinfo=timezone.utc):
            print("Last detection: Never")
        else:
            print(f"Last detection: {last_run.isoformat()}")

        print(f"Interval: {periodic_minutes} minutes")
        print(f"Should run: {should_run_detection()}")
        return 0

    if args.force:
        set_last_detection_time()
        from detector import run_detection
        gaps = run_detection()
        print(f"Detection complete. Found {len(gaps)} gap(s).")
        return 0

    result = run_periodic_detection()

    if result['ran']:
        gaps_count = result.get('gaps_detected', 0)
        if 'error' in result:
            print(f"Detection error: {result['error']}")
        else:
            print(f"Periodic detection complete. Found {gaps_count} gap(s).")
    else:
        print(f"Skipped: {result.get('reason', 'unknown')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
