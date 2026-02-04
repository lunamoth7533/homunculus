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


def apply_confidence_decay() -> int:
    """
    Apply confidence decay to old pending gaps.
    Gaps lose 5% confidence per day of inactivity.

    Returns number of gaps updated.
    """
    try:
        with get_db_connection() as conn:
            # Decay gaps that haven't been updated in 24+ hours
            # Confidence decays by 5% per day, minimum 0.1
            cursor = conn.execute("""
                UPDATE gaps
                SET confidence = MAX(0.1, confidence * 0.95),
                    updated_at = ?
                WHERE status = 'pending'
                  AND updated_at < datetime('now', '-1 day')
            """, (get_timestamp(),))
            conn.commit()
            return cursor.rowcount
    except Exception as e:
        print(f"Error applying confidence decay: {e}")
        return 0


def set_last_attempt_time(timestamp: str = None) -> bool:
    """Record current time as last detection attempt time (for visibility into failures)."""
    if timestamp is None:
        timestamp = get_timestamp()

    try:
        with get_db_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO metadata (key, value, updated_at)
                   VALUES ('last_detection_attempt', ?, ?)""",
                (timestamp, timestamp)
            )
            conn.commit()
        return True
    except Exception:
        return False


def run_periodic_detection() -> dict:
    """
    Run detection if periodic interval has passed.
    Also applies confidence decay to old gaps.
    Returns dict with results.

    Note: last_detection_time is set AFTER successful detection to avoid
    suppressing retries when detection fails.
    """
    if not should_run_detection():
        return {
            'ran': False,
            'reason': 'Not enough time elapsed since last detection'
        }

    # Record that we're attempting detection (for visibility)
    set_last_attempt_time()

    # Apply confidence decay to old gaps
    decayed = apply_confidence_decay()

    try:
        from detector import run_detection
        gaps = run_detection()

        # Only record successful detection time AFTER success
        set_last_detection_time()

        return {
            'ran': True,
            'gaps_detected': len(gaps),
            'gaps_decayed': decayed,
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
        # Don't update last_detection_time on failure - allow retry on next interval
        return {
            'ran': True,
            'error': str(e),
            'gaps_detected': 0,
            'gaps_decayed': decayed
        }


def main():
    """Run periodic detection and print results."""
    import argparse

    parser = argparse.ArgumentParser(description="Periodic gap detection")
    parser.add_argument("--force", action="store_true", help="Force detection even if interval hasn't passed")
    parser.add_argument("--status", action="store_true", help="Show last detection time")
    parser.add_argument("--decay", action="store_true", help="Apply confidence decay to old gaps")

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

    if args.decay:
        decayed = apply_confidence_decay()
        print(f"Applied confidence decay to {decayed} gap(s).")
        return 0

    if args.force:
        set_last_detection_time()
        decayed = apply_confidence_decay()
        from detector import run_detection
        gaps = run_detection()
        print(f"Detection complete. Found {len(gaps)} gap(s). Decayed {decayed} old gaps.")
        return 0

    result = run_periodic_detection()

    if result['ran']:
        gaps_count = result.get('gaps_detected', 0)
        decayed_count = result.get('gaps_decayed', 0)
        if 'error' in result:
            print(f"Detection error: {result['error']}")
        else:
            msg = f"Periodic detection complete. Found {gaps_count} gap(s)."
            if decayed_count > 0:
                msg += f" Decayed {decayed_count} old gaps."
            print(msg)
    else:
        print(f"Skipped: {result.get('reason', 'unknown')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
