#!/usr/bin/env python3
"""
Archive old observations to prevent unbounded growth.
Run periodically (e.g., via cron or at session end).
"""

import json
import gzip
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any

import sys
sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    HOMUNCULUS_ROOT, load_config, read_jsonl, get_timestamp,
    get_db_connection
)


def get_archive_dir() -> Path:
    """Get or create the archive directory."""
    archive_dir = HOMUNCULUS_ROOT / "observations" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    return archive_dir


def archive_observations(dry_run: bool = False) -> Dict[str, Any]:
    """
    Archive observations older than configured threshold.

    Returns dict with:
        - archived_count: number of observations archived
        - archive_file: path to archive file (if any)
        - current_remaining: observations still in current.jsonl
    """
    config = load_config()
    storage_config = config.get('storage', {})
    archive_after_days = storage_config.get('archive_after_days', 7)
    max_mb = storage_config.get('observations_max_mb', 50)

    current_file = HOMUNCULUS_ROOT / "observations" / "current.jsonl"

    if not current_file.exists():
        return {'archived_count': 0, 'archive_file': None, 'current_remaining': 0}

    # Read all observations
    observations = read_jsonl(current_file)

    if not observations:
        return {'archived_count': 0, 'archive_file': None, 'current_remaining': 0}

    # Calculate cutoff date
    cutoff = datetime.utcnow() - timedelta(days=archive_after_days)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Separate old and recent observations
    old_observations = []
    recent_observations = []

    for obs in observations:
        timestamp = obs.get('timestamp', '')
        if timestamp and timestamp < cutoff_str:
            old_observations.append(obs)
        else:
            recent_observations.append(obs)

    if not old_observations:
        return {
            'archived_count': 0,
            'archive_file': None,
            'current_remaining': len(recent_observations)
        }

    if dry_run:
        return {
            'archived_count': len(old_observations),
            'archive_file': '[dry run]',
            'current_remaining': len(recent_observations),
            'dry_run': True
        }

    # Create archive file
    archive_dir = get_archive_dir()
    archive_date = datetime.utcnow().strftime("%Y-%m-%d")
    archive_file = archive_dir / f"{archive_date}.jsonl.gz"

    # If archive file exists, append to it
    existing_archived = []
    if archive_file.exists():
        with gzip.open(archive_file, 'rt', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        existing_archived.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    # Write combined archive
    all_archived = existing_archived + old_observations
    with gzip.open(archive_file, 'wt', encoding='utf-8') as f:
        for obs in all_archived:
            f.write(json.dumps(obs) + '\n')

    # Update current.jsonl with only recent observations
    with open(current_file, 'w') as f:
        for obs in recent_observations:
            f.write(json.dumps(obs) + '\n')

    # Update database - mark archived observations as processed
    try:
        with get_db_connection() as conn:
            for obs in old_observations:
                obs_id = obs.get('id')
                if obs_id:
                    conn.execute(
                        "UPDATE observations SET processed = 1 WHERE id = ?",
                        (obs_id,)
                    )
            conn.commit()
    except Exception as e:
        print(f"Warning: Could not update database: {e}")

    return {
        'archived_count': len(old_observations),
        'archive_file': str(archive_file),
        'current_remaining': len(recent_observations)
    }


def cleanup_old_archives(keep_days: int = 30) -> List[str]:
    """
    Remove archive files older than keep_days.

    Returns list of removed files.
    """
    archive_dir = get_archive_dir()
    cutoff = datetime.utcnow() - timedelta(days=keep_days)
    removed = []

    for archive_file in archive_dir.glob("*.jsonl.gz"):
        # Parse date from filename (YYYY-MM-DD.jsonl.gz)
        try:
            date_str = archive_file.stem.replace('.jsonl', '')
            file_date = datetime.strptime(date_str, "%Y-%m-%d")

            if file_date < cutoff:
                archive_file.unlink()
                removed.append(str(archive_file))
        except ValueError:
            continue

    return removed


def check_size_limit() -> Dict[str, Any]:
    """Check if observations are approaching size limit."""
    config = load_config()
    max_mb = config.get('storage', {}).get('observations_max_mb', 50)

    current_file = HOMUNCULUS_ROOT / "observations" / "current.jsonl"

    if not current_file.exists():
        return {'size_mb': 0, 'limit_mb': max_mb, 'percent_used': 0}

    size_bytes = current_file.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    percent_used = (size_mb / max_mb) * 100 if max_mb > 0 else 0

    return {
        'size_mb': round(size_mb, 2),
        'limit_mb': max_mb,
        'percent_used': round(percent_used, 1),
        'warning': percent_used > 80
    }


def should_auto_archive() -> bool:
    """
    Check if auto-archive should run based on thresholds.

    Returns True if:
    - Size is above 50% of limit, OR
    - More than 24 hours since last archive, OR
    - More than 1000 observations in current.jsonl
    """
    config = load_config()
    storage_config = config.get('storage', {})
    max_mb = storage_config.get('observations_max_mb', 50)
    archive_after_days = storage_config.get('archive_after_days', 7)

    current_file = HOMUNCULUS_ROOT / "observations" / "current.jsonl"

    if not current_file.exists():
        return False

    # Check size threshold (50%)
    size_info = check_size_limit()
    if size_info['percent_used'] > 50:
        return True

    # Check observation count (more than 1000)
    observations = read_jsonl(current_file)
    if len(observations) > 1000:
        return True

    # Check time since last archive
    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT value FROM metadata WHERE key = 'last_archive_run'"
            )
            row = cursor.fetchone()
            if row:
                last_run = datetime.fromisoformat(row[0].replace('Z', '+00:00'))
                if datetime.now(last_run.tzinfo) - last_run > timedelta(hours=24):
                    return True
            else:
                # Never run before
                return True
    except Exception:
        pass

    return False


def record_archive_run() -> None:
    """Record the last archive run timestamp in metadata."""
    try:
        with get_db_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO metadata (key, value, updated_at)
                   VALUES ('last_archive_run', ?, ?)""",
                (get_timestamp(), get_timestamp())
            )
            conn.commit()
    except Exception as e:
        print(f"Warning: Could not record archive run: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Archive Homunculus observations")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be archived")
    parser.add_argument("--cleanup", action="store_true", help="Remove old archives (>30 days)")
    parser.add_argument("--status", action="store_true", help="Show current observation status")
    parser.add_argument("--auto", action="store_true",
                        help="Only archive if thresholds are met (for automatic runs)")

    args = parser.parse_args()

    if args.status:
        size_info = check_size_limit()
        print(f"Current observations: {size_info['size_mb']} MB / {size_info['limit_mb']} MB ({size_info['percent_used']}%)")
        if size_info.get('warning'):
            print("WARNING: Approaching size limit!")
        return 0

    if args.cleanup:
        removed = cleanup_old_archives()
        if removed:
            print(f"Removed {len(removed)} old archive(s):")
            for f in removed:
                print(f"  - {f}")
        else:
            print("No old archives to remove")
        return 0

    # Auto mode: check thresholds first
    if args.auto:
        if not should_auto_archive():
            # Silently exit - thresholds not met
            return 0

    # Default: archive observations
    result = archive_observations(dry_run=args.dry_run)

    if args.dry_run:
        print(f"[DRY RUN] Would archive {result['archived_count']} observations")
        print(f"[DRY RUN] {result['current_remaining']} observations would remain")
    else:
        if result['archived_count'] > 0:
            print(f"Archived {result['archived_count']} observations to {result['archive_file']}")
            # Record the archive run
            record_archive_run()
        else:
            print("No observations to archive")
        print(f"{result['current_remaining']} observations in current.jsonl")

    return 0


if __name__ == "__main__":
    sys.exit(main())
