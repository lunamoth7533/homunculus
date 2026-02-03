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
    print()
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
    print("1. Add hooks to ~/.claude/settings.json (see ~/homunculus/docs/hook-setup.md)")
    print("2. Restart Claude Code to activate hooks")
    print("3. Use Claude normally - gaps will be detected automatically")
    print("4. Run '/homunculus proposals' to review suggestions")
    print()

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
    print(f"  Total in DB: {obs_count}")

    # Check current session file
    if OBSERVATIONS_PATH.exists():
        with open(OBSERVATIONS_PATH, 'r') as f:
            current_count = sum(1 for _ in f)
        print(f"  Current session: {current_count}")
    else:
        print("  Current session: 0")
    print()

    # Gaps
    print("  -- Gaps --")
    gaps = tables.get("gaps", 0)
    print(f"  Total detected: {gaps}")

    try:
        pending_gaps = db_execute(
            "SELECT COUNT(*) as count FROM gaps WHERE status = 'pending'"
        )
        print(f"  Pending: {pending_gaps[0]['count'] if pending_gaps else 0}")
    except Exception:
        print("  Pending: 0")
    print()

    # Proposals
    print("  -- Proposals --")
    proposals = tables.get("proposals", 0)
    print(f"  Total: {proposals}")

    try:
        pending_props = db_execute(
            "SELECT COUNT(*) as count FROM proposals WHERE status = 'pending'"
        )
        pending_count = pending_props[0]['count'] if pending_props else 0
        if pending_count > 0:
            print(f"  Pending review: {pending_count} <- Action needed")
        else:
            print(f"  Pending review: 0")
    except Exception:
        print("  Pending review: 0")
    print()

    # Capabilities
    print("  -- Installed Capabilities --")
    caps = tables.get("capabilities", 0)
    print(f"  Total: {caps}")

    if caps > 0:
        try:
            cap_types = db_execute(
                "SELECT capability_type, COUNT(*) as count FROM capabilities WHERE status = 'active' GROUP BY capability_type"
            )
            for ct in cap_types:
                print(f"    {ct['capability_type']}: {ct['count']}")
        except Exception:
            pass
    print()

    print("=" * 60)
    print()

    return 0


def cmd_gaps(args):
    """List detected gaps."""
    try:
        gaps = db_execute(
            """SELECT id, gap_type, domain, confidence, recommended_scope, status,
                      substr(desired_capability, 1, 40) as capability
               FROM gaps
               WHERE status IN ('pending', 'synthesizing')
               ORDER BY confidence DESC
               LIMIT 20"""
        )
    except Exception as e:
        print(f"Error: {e}")
        return 1

    if not gaps:
        print()
        print("No pending gaps detected.")
        print()
        return 0

    print()
    print(f"DETECTED GAPS ({len(gaps)})")
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
    print("Commands:")
    print("  /homunculus gap <id>        - View gap details")
    print("  /homunculus dismiss-gap <id> - Permanently ignore")
    print()

    return 0


def cmd_gap(args):
    """Show details for a specific gap."""
    gap_id = args.gap_id

    try:
        gaps = db_execute(
            "SELECT * FROM gaps WHERE id = ? OR id LIKE ?",
            (gap_id, f"{gap_id}%")
        )
    except Exception as e:
        print(f"Error: {e}")
        return 1

    if not gaps:
        print(f"Gap not found: {gap_id}")
        return 1

    gap = gaps[0]

    print()
    print(f"GAP DETAILS: {gap['id']}")
    print("-" * 50)
    print()
    print(f"  Type: {gap['gap_type']}")
    print(f"  Domain: {gap['domain'] or '-'}")
    print(f"  Confidence: {gap['confidence']:.2f}")
    print(f"  Scope: {gap['recommended_scope']}")
    print(f"  Status: {gap['status']}")
    print(f"  Detected: {gap['detected_at']}")
    print()
    print("  -- Desired Capability --")
    print(f"  {gap['desired_capability']}")
    print()
    print("  -- Evidence --")
    print(f"  {gap['evidence_summary'] or 'No evidence recorded'}")
    print()

    return 0


def cmd_proposals(args):
    """List pending proposals."""
    try:
        proposals = db_execute(
            """SELECT p.id, p.capability_type, p.capability_name, p.confidence,
                      p.scope, g.gap_type, substr(g.desired_capability, 1, 30) as gap_desc
               FROM proposals p
               JOIN gaps g ON p.gap_id = g.id
               WHERE p.status = 'pending'
               ORDER BY p.confidence DESC"""
        )
    except Exception as e:
        print(f"Error: {e}")
        return 1

    if not proposals:
        print()
        print("No pending proposals.")
        print()
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
    try:
        caps = db_execute(
            """SELECT c.id, c.name, c.capability_type, c.scope, c.installed_at,
                      COUNT(u.id) as usage_count
               FROM capabilities c
               LEFT JOIN capability_usage u ON c.id = u.capability_id
               WHERE c.status = 'active'
               GROUP BY c.id
               ORDER BY c.installed_at DESC"""
        )
    except Exception as e:
        print(f"Error: {e}")
        return 1

    if not caps:
        print()
        print("No installed capabilities.")
        print()
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
    print()
    print("Running gap detection...")

    try:
        # Import detector module
        from detector import run_detection
        gaps = run_detection()

        if gaps:
            print(f"\nDetected {len(gaps)} gap(s):")
            for gap in gaps:
                print(f"  - [{gap.gap_type}] {gap.desired_capability[:50]}... (conf: {gap.confidence:.2f})")
        else:
            print("\nNo new gaps detected.")

    except ImportError:
        print("Gap detection not yet implemented.")
        print("This will be added in Phase 2.")
    except Exception as e:
        print(f"Error during detection: {e}")
        return 1

    print()
    return 0


def cmd_synthesize(args):
    """Manually trigger synthesis."""
    print()
    print("Synthesis not yet implemented.")
    print("This will be added in Phase 3.")
    print()
    return 0


def cmd_review(args):
    """Review a proposal."""
    print()
    print("Review not yet implemented.")
    print("This will be added in Phase 4.")
    print()
    return 0


def cmd_approve(args):
    """Approve a proposal."""
    print()
    print("Approval not yet implemented.")
    print("This will be added in Phase 4.")
    print()
    return 0


def cmd_reject(args):
    """Reject a proposal."""
    print()
    print("Rejection not yet implemented.")
    print("This will be added in Phase 4.")
    print()
    return 0


def cmd_rollback(args):
    """Rollback a capability."""
    print()
    print("Rollback not yet implemented.")
    print("This will be added in Phase 4.")
    print()
    return 0


def cmd_dismiss_gap(args):
    """Dismiss a gap permanently."""
    gap_id = args.gap_id

    try:
        from utils import get_db_connection, get_timestamp

        with get_db_connection() as conn:
            cursor = conn.execute(
                "UPDATE gaps SET status = 'dismissed', dismissed_at = ?, dismissed_reason = ? WHERE id = ? OR id LIKE ?",
                (get_timestamp(), args.reason or "User dismissed", gap_id, f"{gap_id}%")
            )
            conn.commit()

            if cursor.rowcount > 0:
                print(f"\nGap dismissed: {gap_id}")
            else:
                print(f"\nGap not found: {gap_id}")
                return 1

    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


def cmd_meta_status(args):
    """Show meta-evolution status."""
    print()
    print("META-EVOLUTION STATUS")
    print("-" * 40)
    print()
    print("Meta-evolution not yet implemented.")
    print("This will be added in Phase 5.")
    print()
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

    # gap (detail)
    gap_parser = subparsers.add_parser("gap", help="Show gap details")
    gap_parser.add_argument("gap_id", help="Gap ID")

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

    # dismiss-gap
    dismiss_parser = subparsers.add_parser("dismiss-gap", help="Permanently ignore a gap")
    dismiss_parser.add_argument("gap_id", help="Gap ID to dismiss")
    dismiss_parser.add_argument("--reason", help="Dismissal reason")

    # meta-status
    subparsers.add_parser("meta-status", help="Show meta-evolution status")

    args = parser.parse_args()

    # Default to status if no command
    if not args.command:
        args.command = "status"

    # Dispatch to command handler
    commands = {
        "init": cmd_init,
        "status": cmd_status,
        "gaps": cmd_gaps,
        "gap": cmd_gap,
        "proposals": cmd_proposals,
        "capabilities": cmd_capabilities,
        "config": cmd_config,
        "detect": cmd_detect,
        "synthesize": cmd_synthesize,
        "review": cmd_review,
        "approve": cmd_approve,
        "reject": cmd_reject,
        "rollback": cmd_rollback,
        "dismiss-gap": cmd_dismiss_gap,
        "meta-status": cmd_meta_status,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
