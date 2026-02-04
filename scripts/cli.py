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
    generate_id, get_timestamp, get_effective_db_path,
    get_project_db_path, detect_project_root, ensure_project_db_initialized,
    list_project_databases
)
from init_db import init_database, check_database


def get_db_for_args(args) -> Path:
    """Get the appropriate database path based on CLI arguments."""
    scope = getattr(args, 'scope', None)
    project_path = getattr(args, 'project', None)

    if project_path:
        return get_project_db_path(Path(project_path))

    return get_effective_db_path(scope=scope, project_path=project_path)


def cmd_init(args):
    """Initialize Homunculus."""
    project_path = getattr(args, 'project', None)
    auto_project = getattr(args, 'auto_project', False)

    print()

    # Handle project-scoped initialization
    if project_path or auto_project:
        if auto_project:
            project_path = detect_project_root()
            if not project_path:
                print("Could not detect project root.")
                print("Use --project <path> to specify project directory.")
                return 1

        project_path = Path(project_path)
        db_path = get_project_db_path(project_path)

        print(f"Initializing project-scoped Homunculus...")
        print(f"  Project: {project_path}")
        print()

        # Check if already initialized
        db_info = check_database(db_path)
        if db_info.get("exists") and not args.force:
            print(f"Project database already exists at {db_path}")
            print("Use --force to reinitialize")
            return 1

        # Initialize project database
        if not ensure_project_db_initialized(project_path):
            print("Failed to initialize project database")
            return 1

        print(f"Project database initialized at {db_path}")
        print()
        print("This project now has its own:")
        print("  - Gap detection")
        print("  - Proposals")
        print("  - Capabilities")
        print()
        print("Use --scope project or --project <path> with commands to use project DB.")
        return 0

    # Global initialization
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
    print("For project-scoped databases, use:")
    print("  homunculus init --auto-project   (auto-detect project)")
    print("  homunculus init --project /path  (explicit path)")
    print()

    return 0


def cmd_status(args):
    """Show system status."""
    # Determine which database to use
    db_path = get_db_for_args(args)
    scope = "project" if db_path != DB_PATH else "global"

    print()
    print("=" * 60)
    print("  HOMUNCULUS STATUS")
    print("=" * 60)
    print()
    print(f"  Scope: {scope.upper()}")
    if scope == "project":
        print(f"  Database: {db_path}")
    print()

    # Check database
    db_info = check_database(db_path)
    if not db_info.get("exists"):
        print("  Status: NOT INITIALIZED")
        print()
        if scope == "project":
            print("  Run 'homunculus init --project <path>' to initialize")
        else:
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
            "SELECT COUNT(*) as count FROM gaps WHERE status = 'pending'",
            db_path=db_path
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
            "SELECT COUNT(*) as count FROM proposals WHERE status = 'pending'",
            db_path=db_path
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
                "SELECT capability_type, COUNT(*) as count FROM capabilities WHERE status = 'active' GROUP BY capability_type",
                db_path=db_path
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
    db_path = get_db_for_args(args)

    try:
        gaps = db_execute(
            """SELECT id, gap_type, domain, confidence, recommended_scope, status,
                      substr(desired_capability, 1, 40) as capability
               FROM gaps
               WHERE status IN ('pending', 'synthesizing')
               ORDER BY confidence DESC
               LIMIT 20""",
            db_path=db_path
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
    db_path = get_db_for_args(args)
    gap_id = args.gap_id

    try:
        gaps = db_execute(
            "SELECT * FROM gaps WHERE id = ? OR id LIKE ?",
            (gap_id, f"{gap_id}%"),
            db_path=db_path
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
    db_path = get_db_for_args(args)

    try:
        proposals = db_execute(
            """SELECT p.id, p.capability_type, p.capability_name, p.confidence,
                      p.scope, g.gap_type, substr(g.desired_capability, 1, 30) as gap_desc
               FROM proposals p
               JOIN gaps g ON p.gap_id = g.id
               WHERE p.status = 'pending'
               ORDER BY p.confidence DESC""",
            db_path=db_path
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
    db_path = get_db_for_args(args)

    try:
        caps = db_execute(
            """SELECT c.id, c.name, c.capability_type, c.scope, c.installed_at,
                      COUNT(u.id) as usage_count
               FROM capabilities c
               LEFT JOIN capability_usage u ON c.id = u.capability_id
               WHERE c.status = 'active'
               GROUP BY c.id
               ORDER BY c.installed_at DESC""",
            db_path=db_path
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
    from synthesizer import run_synthesis, CapabilitySynthesizer

    print()
    print("=" * 60)
    print("CAPABILITY SYNTHESIS")
    print("=" * 60)

    # Check for templates
    synthesizer = CapabilitySynthesizer()
    if not synthesizer.templates:
        print("\nNo synthesis templates found.")
        print("Templates should be in: ~/homunculus/meta/synthesis-templates/")
        return 1

    print(f"\nLoaded {len(synthesizer.templates)} synthesis template(s):")
    for template_type, template in synthesizer.templates.items():
        print(f"  - {template_type}: {template.id} (v{template.version})")

    # Run synthesis
    gap_id = getattr(args, 'gap_id', None)
    limit = getattr(args, 'limit', 5)

    print(f"\nSynthesizing proposals (limit: {limit})...")
    proposals = run_synthesis(gap_id=gap_id, limit=limit)

    if not proposals:
        print("\nNo proposals generated.")
        if not gap_id:
            print("(No pending gaps found, or no matching templates)")
        return 0

    print(f"\nGenerated {len(proposals)} proposal(s):\n")
    for p in proposals:
        print(f"  [{p.id[:12]}] {p.capability_type.upper()}")
        print(f"    Name: {p.capability_name}")
        print(f"    Summary: {p.capability_summary[:60]}...")
        print(f"    Confidence: {p.confidence:.2f}")
        print(f"    Scope: {p.scope}")
        print(f"    Files: {len(p.files)}")
        for f in p.files:
            print(f"      - {f['action']}: {f['path']}")
        print()

    print("Use 'homunculus review <proposal-id>' to review a proposal.")
    print("=" * 60)
    print()
    return 0


def cmd_review(args):
    """Review a proposal."""
    from installer import get_proposal, format_proposal_review

    proposal_id = args.proposal_id

    proposal = get_proposal(proposal_id)
    if not proposal:
        print(f"\nProposal not found: {proposal_id}")
        return 1

    print()
    print(format_proposal_review(proposal))
    return 0


def cmd_approve(args):
    """Approve a proposal."""
    from installer import install_proposal, get_proposal
    from utils import HOMUNCULUS_ROOT

    proposal_id = args.proposal_id
    dry_run = getattr(args, 'dry_run', False)

    # First verify proposal exists
    proposal = get_proposal(proposal_id)
    if not proposal:
        print(f"\nProposal not found: {proposal_id}")
        return 1

    if proposal['status'] != 'pending':
        print(f"\nProposal is not pending (status: {proposal['status']})")
        return 1

    # Parse files
    try:
        files = json.loads(proposal.get('files_json', '[]'))
    except json.JSONDecodeError:
        files = []

    print()
    if dry_run:
        print("=" * 60)
        print("DRY RUN - No changes will be made")
        print("=" * 60)
    else:
        print("=" * 60)
        print("INSTALLING CAPABILITY")
        print("=" * 60)
    print()
    print(f"  Proposal: {proposal['id'][:12]}")
    print(f"  Type: {proposal['capability_type']}")
    print(f"  Name: {proposal['capability_name']}")
    print(f"  Scope: {proposal['scope']}")
    print()

    if dry_run:
        # Show what would be created
        print("Files that would be created:")
        for f in files:
            rel_path = f.get('path', '')
            action = f.get('action', 'create')
            full_path = HOMUNCULUS_ROOT / rel_path
            exists = full_path.exists()
            status = "(exists - would overwrite)" if exists else "(new)"
            print(f"  [{action.upper()}] {rel_path} {status}")

            # Show content preview
            content = f.get('content', '')
            if content:
                lines = content.split('\n')
                print(f"    Preview ({len(lines)} lines):")
                for line in lines[:5]:
                    print(f"      {line[:70]}")
                if len(lines) > 5:
                    print(f"      ... ({len(lines) - 5} more lines)")
            print()

        print("-" * 60)
        print("To install: homunculus approve", proposal['id'][:12])
        print()
        return 0

    # Confirm installation
    confirm = input("Proceed with installation? [y/N]: ").strip().lower()
    if confirm not in ('y', 'yes'):
        print("\nInstallation cancelled.")
        return 0

    # Install
    result = install_proposal(proposal['id'])

    if result.success:
        print()
        print("Installation successful!")
        print(f"  Capability ID: {result.capability_id}")
        print(f"  Files created:")
        for f in result.files_created:
            print(f"    - {f}")
        print()
        print(f"To rollback: homunculus rollback {proposal['capability_name']}")
    else:
        print()
        print(f"Installation failed: {result.message}")
        return 1

    print()
    return 0


def cmd_reject(args):
    """Reject a proposal."""
    from installer import reject_proposal, get_proposal

    proposal_id = args.proposal_id
    reason = getattr(args, 'reason', '') or "User rejected"

    # Verify proposal exists
    proposal = get_proposal(proposal_id)
    if not proposal:
        print(f"\nProposal not found: {proposal_id}")
        return 1

    if proposal['status'] != 'pending':
        print(f"\nProposal is not pending (status: {proposal['status']})")
        return 1

    print()
    print(f"Rejecting proposal: {proposal['id'][:12]}")
    print(f"  Name: {proposal['capability_name']}")
    print(f"  Reason: {reason}")

    if reject_proposal(proposal['id'], reason):
        print("\nProposal rejected.")
        print("The gap has been returned to pending status.")
    else:
        print("\nFailed to reject proposal.")
        return 1

    print()
    return 0


def cmd_rollback(args):
    """Rollback a capability."""
    from installer import rollback_capability, get_capability, check_rollback_safe, get_dependents

    capability_name = args.capability_name
    force = getattr(args, 'force', False)

    # Verify capability exists
    capability = get_capability(capability_name)
    if not capability:
        print(f"\nCapability not found: {capability_name}")
        return 1

    if capability['status'] != 'active':
        print(f"\nCapability is not active (status: {capability['status']})")
        return 1

    print()
    print("=" * 60)
    print("ROLLBACK CAPABILITY")
    print("=" * 60)
    print()
    print(f"  Capability: {capability['name']}")
    print(f"  Type: {capability['capability_type']}")
    print(f"  Installed: {capability['installed_at']}")
    print()

    # Check for dependents
    dependents = get_dependents(capability['id'])
    if dependents:
        print("  -- Dependencies --")
        print(f"  The following capabilities depend on this one:")
        for dep in dependents:
            dep_type = dep['dependency_type']
            print(f"    - {dep['capability_name']} ({dep_type})")
        print()

        required_deps = [d for d in dependents if d['dependency_type'] == 'required']
        if required_deps:
            print("  ERROR: Cannot rollback - has required dependents.")
            print("  First rollback the dependent capabilities.")
            return 1

        if not force:
            print("  Use --force to rollback anyway (will affect optional dependents).")
            return 1

    # Confirm rollback
    confirm = input("Proceed with rollback? [y/N]: ").strip().lower()
    if confirm not in ('y', 'yes'):
        print("\nRollback cancelled.")
        return 0

    # Rollback
    result = rollback_capability(capability['id'], force=force)

    if result.success:
        print()
        print("Rollback successful!")
        print("  Files affected:")
        for f in result.files_created:
            print(f"    - {f}")
    else:
        print()
        print(f"Rollback failed: {result.message}")
        return 1

    print()
    return 0


def cmd_dependencies(args):
    """Show or manage capability dependencies."""
    from installer import (
        get_capability, get_dependencies, get_dependents,
        add_dependency, remove_dependency
    )

    db_path = get_db_for_args(args)
    action = getattr(args, 'action', 'show')
    capability_name = getattr(args, 'capability', None)

    if action == 'list':
        # List all dependencies
        deps = db_execute(
            """SELECT cd.*, c1.name as cap_name, c2.name as dep_name
               FROM capability_dependencies cd
               JOIN capabilities c1 ON cd.capability_id = c1.id
               JOIN capabilities c2 ON cd.depends_on_id = c2.id
               WHERE c1.status = 'active' AND c2.status = 'active'
               ORDER BY c1.name""",
            db_path=db_path
        )

        print()
        print("CAPABILITY DEPENDENCIES")
        print("-" * 60)

        if not deps:
            print("\nNo dependencies defined.")
            print()
            return 0

        current_cap = None
        for d in deps:
            if d['cap_name'] != current_cap:
                current_cap = d['cap_name']
                print(f"\n  {current_cap}:")
            print(f"    -> {d['dep_name']} ({d['dependency_type']})")
            if d.get('notes'):
                print(f"       Note: {d['notes']}")

        print()
        return 0

    if not capability_name:
        print("Error: capability name required")
        return 1

    capability = get_capability(capability_name)
    if not capability:
        print(f"\nCapability not found: {capability_name}")
        return 1

    if action == 'show':
        print()
        print(f"DEPENDENCIES FOR: {capability['name']}")
        print("-" * 60)

        # Show what this capability depends on
        deps = get_dependencies(capability['id'])
        print("\n  Depends on:")
        if deps:
            for d in deps:
                print(f"    - {d['depends_on_name']} ({d['dependency_type']})")
                if d.get('notes'):
                    print(f"      Note: {d['notes']}")
        else:
            print("    (none)")

        # Show what depends on this capability
        dependents = get_dependents(capability['id'])
        print("\n  Depended on by:")
        if dependents:
            for d in dependents:
                print(f"    - {d['capability_name']} ({d['dependency_type']})")
        else:
            print("    (none)")

        print()
        return 0

    elif action == 'add':
        depends_on = getattr(args, 'depends_on', None)
        dep_type = getattr(args, 'type', 'required')
        notes = getattr(args, 'notes', None)

        if not depends_on:
            print("Error: --depends-on required")
            return 1

        target = get_capability(depends_on)
        if not target:
            print(f"\nDependency target not found: {depends_on}")
            return 1

        if add_dependency(capability['id'], target['id'], dep_type, notes):
            print(f"\nAdded dependency: {capability['name']} -> {target['name']} ({dep_type})")
        else:
            print("\nFailed to add dependency")
            return 1

        return 0

    elif action == 'remove':
        depends_on = getattr(args, 'depends_on', None)

        if not depends_on:
            print("Error: --depends-on required")
            return 1

        target = get_capability(depends_on)
        if not target:
            print(f"\nDependency target not found: {depends_on}")
            return 1

        if remove_dependency(capability['id'], target['id']):
            print(f"\nRemoved dependency: {capability['name']} -> {target['name']}")
        else:
            print("\nDependency not found or failed to remove")
            return 1

        return 0

    print(f"Unknown action: {action}")
    return 1


def cmd_variants(args):
    """View and manage template variants for A/B testing."""
    db_path = get_db_for_args(args)
    action = getattr(args, 'action', 'list')

    if action == 'list':
        # List all variants
        try:
            variants = db_execute(
                """SELECT * FROM template_variants ORDER BY template_id, variant_name""",
                db_path=db_path
            )
        except Exception:
            variants = []

        print()
        print("TEMPLATE VARIANTS (A/B Testing)")
        print("-" * 60)

        if not variants:
            print("\nNo variants defined.")
            print("\nTo create a variant:")
            print("  homunculus variants add <template_id> <variant_name> --patches '{...}'")
            print()
            return 0

        current_template = None
        for v in variants:
            if v['template_id'] != current_template:
                current_template = v['template_id']
                print(f"\n  Template: {current_template}")
            status = "enabled" if v['enabled'] else "disabled"
            print(f"    - {v['variant_name']} (weight: {v['weight']}, {status})")
            if v.get('variant_description'):
                print(f"      {v['variant_description']}")

        print()
        return 0

    elif action == 'results':
        # Show A/B test results
        try:
            results = db_execute(
                """SELECT template_id, template_variant,
                          COUNT(*) as total,
                          SUM(CASE WHEN status IN ('approved', 'installed') THEN 1 ELSE 0 END) as approved,
                          SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected,
                          ROUND(AVG(confidence), 3) as avg_conf
                   FROM proposals
                   WHERE template_variant IS NOT NULL
                   GROUP BY template_id, template_variant
                   ORDER BY template_id, template_variant""",
                db_path=db_path
            )
        except Exception as e:
            print(f"Error: {e}")
            return 1

        print()
        print("A/B TEST RESULTS")
        print("-" * 60)

        if not results:
            print("\nNo A/B test data yet.")
            print("Variants will be tracked once proposals are generated.")
            print()
            return 0

        headers = ["TEMPLATE", "VARIANT", "TOTAL", "APPROVED", "REJECTED", "RATE", "AVG CONF"]
        rows = []
        for r in results:
            total = r['total']
            approved = r['approved'] or 0
            rate = f"{(approved/total*100):.1f}%" if total > 0 else "-"
            rows.append([
                r['template_id'][:15],
                r['template_variant'] or 'base',
                str(total),
                str(approved),
                str(r['rejected'] or 0),
                rate,
                f"{r['avg_conf']:.2f}" if r['avg_conf'] else '-'
            ])

        print()
        print(format_table(headers, rows))
        print()
        return 0

    elif action == 'add':
        template_id = getattr(args, 'template_id', None)
        variant_name = getattr(args, 'variant_name', None)
        patches = getattr(args, 'patches', '{}')
        weight = getattr(args, 'weight', 1.0)
        description = getattr(args, 'description', '')

        if not template_id or not variant_name:
            print("Error: template_id and variant_name required")
            return 1

        try:
            # Validate patches JSON
            json.loads(patches)
        except json.JSONDecodeError:
            print("Error: patches must be valid JSON")
            return 1

        variant_id = generate_id("var")
        try:
            with get_db_connection(db_path) as conn:
                conn.execute(
                    """INSERT INTO template_variants
                       (id, template_id, variant_name, variant_description, weight, patches_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (variant_id, template_id, variant_name, description, weight, patches, get_timestamp())
                )
                conn.commit()
            print(f"\nCreated variant: {variant_name} for template {template_id}")
        except Exception as e:
            print(f"Error: {e}")
            return 1

        return 0

    elif action == 'toggle':
        variant_name = getattr(args, 'variant_name', None)
        if not variant_name:
            print("Error: variant_name required")
            return 1

        try:
            with get_db_connection(db_path) as conn:
                cursor = conn.execute(
                    "UPDATE template_variants SET enabled = 1 - enabled WHERE variant_name = ?",
                    (variant_name,)
                )
                conn.commit()
                if cursor.rowcount > 0:
                    print(f"\nToggled variant: {variant_name}")
                else:
                    print(f"\nVariant not found: {variant_name}")
                    return 1
        except Exception as e:
            print(f"Error: {e}")
            return 1

        return 0

    print(f"Unknown action: {action}")
    return 1


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
    from meta_evolution import MetaEvolutionEngine, run_meta_evolution

    print()
    print("=" * 60)
    print("META-EVOLUTION STATUS (LAYER 2)")
    print("=" * 60)
    print()

    engine = MetaEvolutionEngine()
    status = engine.get_status()

    print(f"  Enabled: {'Yes' if status['enabled'] else 'No'}")
    print()

    print("  -- Observations --")
    print(f"  Total: {status['observations']['total']}")
    for obs_type, count in status['observations']['by_type'].items():
        print(f"    {obs_type}: {count}")
    print()

    print("  -- Meta-Proposals --")
    print(f"  Total: {status['proposals']['total']}")
    print(f"  Pending: {status['proposals']['pending']}")
    print(f"  Applied: {status['proposals']['applied']}")
    print()

    if status['detector_health']:
        print("  -- Detector Health --")
        for d in status['detector_health']:
            print(f"    {d['id'][:25]}: {d['gaps']} gaps, {d['approval_rate']} approval")
        print()

    if status['template_health']:
        print("  -- Template Health --")
        for t in status['template_health']:
            print(f"    {t['id'][:25]}: {t['proposals']} proposals, {t['approval_rate']} approval")
        print()

    # Offer to run analysis
    if getattr(args, 'analyze', False):
        print("Running meta-analysis...")
        result = run_meta_evolution()
        print(f"\n  Generated {result['observations']} observations")
        print(f"  Generated {result['proposals']} proposals")

        if result.get('observation_details'):
            print("\n  Recent Observations:")
            for obs in result['observation_details'][:3]:
                print(f"    [{obs['type']}] {obs['insight'][:50]}...")

    print("=" * 60)
    print()
    return 0


def cmd_projects(args):
    """List project-scoped databases."""
    print()
    print("=" * 60)
    print("PROJECT-SCOPED DATABASES")
    print("=" * 60)
    print()

    project_dbs = list_project_databases()

    if not project_dbs:
        print("  No project databases found.")
        print()
        print("  To create a project database:")
        print("    homunculus init --auto-project   (in a project directory)")
        print("    homunculus init --project /path")
        print()
        return 0

    print(f"  Found {len(project_dbs)} project database(s):")
    print()

    headers = ["PROJECT", "GAPS", "CAPS"]
    rows = []
    for pdb in project_dbs:
        project_name = Path(pdb['project_path']).name
        rows.append([
            project_name[:30],
            str(pdb['pending_gaps']),
            str(pdb['capabilities'])
        ])

    print(format_table(headers, rows))
    print()

    # Show detail for each
    for pdb in project_dbs:
        print(f"  {pdb['project_path']}")
        print(f"    Database: {pdb['db_path']}")
        print(f"    Pending gaps: {pdb['pending_gaps']}")
        print(f"    Active capabilities: {pdb['capabilities']}")
        print()

    print("  Use --project <path> with commands to operate on a specific project.")
    print()
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Homunculus - Self-evolution system for Claude Code",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Global options for database scope
    parser.add_argument("--scope", choices=["global", "project"],
                        help="Use global or project-scoped database")
    parser.add_argument("--project", type=Path,
                        help="Path to project for project-scoped operations")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # init
    init_parser = subparsers.add_parser("init", help="Initialize Homunculus")
    init_parser.add_argument("--force", action="store_true", help="Force reinitialization")
    init_parser.add_argument("--project", type=Path, dest="project",
                             help="Initialize project-scoped database at path")
    init_parser.add_argument("--auto-project", action="store_true",
                             help="Auto-detect project and initialize project database")

    # projects
    subparsers.add_parser("projects", help="List project-scoped databases")

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
    synth_parser.add_argument("--limit", type=int, default=5, help="Max gaps to process (default: 5)")

    # review
    review_parser = subparsers.add_parser("review", help="Review a proposal")
    review_parser.add_argument("proposal_id", help="Proposal ID to review")

    # approve
    approve_parser = subparsers.add_parser("approve", help="Approve a proposal")
    approve_parser.add_argument("proposal_id", help="Proposal ID to approve")
    approve_parser.add_argument("--dry-run", action="store_true", help="Show what would be installed without installing")

    # reject
    reject_parser = subparsers.add_parser("reject", help="Reject a proposal")
    reject_parser.add_argument("proposal_id", help="Proposal ID to reject")
    reject_parser.add_argument("--reason", help="Rejection reason")

    # rollback
    rollback_parser = subparsers.add_parser("rollback", help="Rollback a capability")
    rollback_parser.add_argument("capability_name", help="Capability name to rollback")
    rollback_parser.add_argument("--force", action="store_true",
                                  help="Force rollback even with optional dependents")

    # dependencies
    deps_parser = subparsers.add_parser("dependencies", help="Show or manage capability dependencies")
    deps_parser.add_argument("action", nargs="?", default="list",
                             choices=["list", "show", "add", "remove"],
                             help="Action to perform (default: list)")
    deps_parser.add_argument("capability", nargs="?", help="Capability name (for show/add/remove)")
    deps_parser.add_argument("--depends-on", help="Target capability for dependency")
    deps_parser.add_argument("--type", choices=["required", "optional", "suggested"],
                             default="required", help="Dependency type (default: required)")
    deps_parser.add_argument("--notes", help="Notes about the dependency")

    # dismiss-gap
    dismiss_parser = subparsers.add_parser("dismiss-gap", help="Permanently ignore a gap")
    dismiss_parser.add_argument("gap_id", help="Gap ID to dismiss")
    dismiss_parser.add_argument("--reason", help="Dismissal reason")

    # meta-status
    meta_parser = subparsers.add_parser("meta-status", help="Show meta-evolution status")
    meta_parser.add_argument("--analyze", action="store_true", help="Run meta-analysis")

    # variants (A/B testing)
    variants_parser = subparsers.add_parser("variants", help="Manage template variants for A/B testing")
    variants_parser.add_argument("action", nargs="?", default="list",
                                  choices=["list", "results", "add", "toggle"],
                                  help="Action: list, results, add, toggle")
    variants_parser.add_argument("template_id", nargs="?", help="Template ID (for add)")
    variants_parser.add_argument("variant_name", nargs="?", help="Variant name (for add/toggle)")
    variants_parser.add_argument("--patches", default="{}",
                                  help="JSON patches to apply to template (for add)")
    variants_parser.add_argument("--weight", type=float, default=1.0,
                                  help="Selection weight (higher = more likely)")
    variants_parser.add_argument("--description", help="Variant description")

    args = parser.parse_args()

    # Default to status if no command
    if not args.command:
        args.command = "status"

    # Dispatch to command handler
    commands = {
        "init": cmd_init,
        "status": cmd_status,
        "projects": cmd_projects,
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
        "dependencies": cmd_dependencies,
        "dismiss-gap": cmd_dismiss_gap,
        "meta-status": cmd_meta_status,
        "variants": cmd_variants,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
