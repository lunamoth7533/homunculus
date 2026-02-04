#!/usr/bin/env python3
"""
Capability installation engine for Homunculus.
Handles installing, tracking, and rolling back capabilities.
"""

import json
import os
import re
import stat
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

import sys
sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    HOMUNCULUS_ROOT, DB_PATH, generate_id, get_timestamp,
    get_db_connection, db_execute
)
from pathlib import Path
from typing import Union


# Allowed directories for file installation (relative to HOMUNCULUS_ROOT)
ALLOWED_INSTALL_DIRS = frozenset([
    'evolved/skills',
    'evolved/hooks',
    'evolved/agents',
    'evolved/commands',
    'evolved/mcp-servers',
])

# Suspicious content patterns that should be flagged
DANGEROUS_PATTERNS = [
    (r'eval\s*\([^)]*\)', 'eval() call'),
    (r'exec\s*\([^)]*\)', 'exec() call'),
    (r'os\.system\s*\([^)]*\)', 'os.system() call'),
    (r'subprocess\.(call|run|Popen)\s*\([^)]*shell\s*=\s*True', 'shell=True subprocess'),
    (r'__import__\s*\([^)]*\)', '__import__() call'),
    (r'curl[^|]*\|\s*(ba)?sh', 'curl pipe to shell'),
    (r'wget[^|]*\|\s*(ba)?sh', 'wget pipe to shell'),
    (r'rm\s+-rf\s+[/~]', 'dangerous rm -rf'),
]


def safe_path_join(base_path: Path, rel_path: str) -> Path:
    """
    Safely join paths, preventing path traversal attacks.

    Raises ValueError if the resulting path would escape base_path.
    """
    # Normalize and resolve the path
    # First, reject obviously malicious patterns
    if '..' in rel_path or rel_path.startswith('/') or rel_path.startswith('~'):
        raise ValueError(f"Invalid path (traversal attempt): {rel_path}")

    # Resolve the full path
    full_path = (base_path / rel_path).resolve()
    base_resolved = base_path.resolve()

    # Ensure it's within the base directory
    try:
        full_path.relative_to(base_resolved)
    except ValueError:
        raise ValueError(f"Path traversal detected: {rel_path} resolves outside {base_path}")

    return full_path


def validate_install_path(rel_path: str) -> bool:
    """
    Validate that the installation path is within allowed directories.
    """
    # Check if path starts with an allowed directory
    for allowed_dir in ALLOWED_INSTALL_DIRS:
        if rel_path.startswith(allowed_dir + '/') or rel_path.startswith(allowed_dir + '\\'):
            return True
    return False


def validate_content(content: str, file_path: str) -> List[str]:
    """
    Validate content for suspicious patterns.
    Returns list of warnings (empty if content is safe).
    """
    warnings = []

    for pattern, description in DANGEROUS_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
            warnings.append(f"Suspicious pattern detected: {description}")

    return warnings


@dataclass
class InstallationResult:
    """Result of an installation operation."""
    success: bool
    capability_id: str
    message: str
    files_created: List[str]
    rollback_info: Optional[Dict[str, Any]] = None


def get_proposal(proposal_id: str, db_path: Union[str, Path] = None) -> Optional[Dict[str, Any]]:
    """Get a proposal by ID (full or partial)."""
    if db_path is None:
        db_path = DB_PATH
    proposals = db_execute(
        """SELECT p.*, g.desired_capability, g.gap_type as origin_gap_type
           FROM proposals p
           JOIN gaps g ON p.gap_id = g.id
           WHERE p.id = ? OR p.id LIKE ?""",
        (proposal_id, f"{proposal_id}%"),
        db_path=db_path
    )
    return proposals[0] if proposals else None


def get_capability(capability_id: str, db_path: Union[str, Path] = None) -> Optional[Dict[str, Any]]:
    """Get a capability by ID or name."""
    if db_path is None:
        db_path = DB_PATH
    caps = db_execute(
        """SELECT * FROM capabilities
           WHERE id = ? OR id LIKE ? OR name = ?""",
        (capability_id, f"{capability_id}%", capability_id),
        db_path=db_path
    )
    return caps[0] if caps else None


def install_proposal(proposal_id: str, db_path: Union[str, Path] = None) -> InstallationResult:
    """Install a proposal's capability files."""
    if db_path is None:
        db_path = DB_PATH
    proposal = get_proposal(proposal_id, db_path=db_path)
    if not proposal:
        return InstallationResult(
            success=False,
            capability_id="",
            message=f"Proposal not found: {proposal_id}",
            files_created=[]
        )

    if proposal['status'] != 'pending':
        return InstallationResult(
            success=False,
            capability_id="",
            message=f"Proposal is not pending (status: {proposal['status']})",
            files_created=[]
        )

    # Parse files to create
    try:
        files = json.loads(proposal['files_json'])
    except json.JSONDecodeError:
        return InstallationResult(
            success=False,
            capability_id="",
            message="Failed to parse proposal files",
            files_created=[]
        )

    # Install files
    created_files = []
    rollback_info = {"files": [], "backups": []}
    content_warnings = []

    try:
        for file_info in files:
            action = file_info.get('action', 'create')
            rel_path = file_info['path']
            content = file_info.get('content', '')

            # SECURITY: Validate path is in allowed directory
            if not validate_install_path(rel_path):
                raise ValueError(f"Installation path not allowed: {rel_path}. Must be in evolved/")

            # SECURITY: Prevent path traversal
            full_path = safe_path_join(HOMUNCULUS_ROOT, rel_path)

            # SECURITY: Validate content for suspicious patterns
            warnings = validate_content(content, rel_path)
            if warnings:
                content_warnings.extend(warnings)
                # Log warnings but don't block (user has already approved)

            # Create parent directory if needed
            full_path.parent.mkdir(parents=True, exist_ok=True)

            if action == 'create':
                # Backup existing file if present
                if full_path.exists():
                    backup_path = full_path.with_suffix(full_path.suffix + '.backup')
                    shutil.copy2(full_path, backup_path)
                    rollback_info['backups'].append({
                        'original': str(full_path),
                        'backup': str(backup_path)
                    })

                # Write the file with restricted permissions (owner read/write only)
                full_path.write_text(content)
                os.chmod(full_path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
                created_files.append(str(full_path))
                rollback_info['files'].append({
                    'path': str(full_path),
                    'action': 'created'
                })

            elif action == 'modify':
                # Backup existing file
                if full_path.exists():
                    backup_path = full_path.with_suffix(full_path.suffix + '.backup')
                    shutil.copy2(full_path, backup_path)
                    rollback_info['backups'].append({
                        'original': str(full_path),
                        'backup': str(backup_path)
                    })

                # Apply modification (for now, just overwrite)
                full_path.write_text(content)
                os.chmod(full_path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
                created_files.append(str(full_path))
                rollback_info['files'].append({
                    'path': str(full_path),
                    'action': 'modified'
                })

    except Exception as e:
        # Rollback on error
        _rollback_files(rollback_info)
        return InstallationResult(
            success=False,
            capability_id="",
            message=f"Installation failed: {e}",
            files_created=[]
        )

    # Create capability record
    capability_id = generate_id("cap")
    timestamp = get_timestamp()

    try:
        with get_db_connection(db_path) as conn:
            # Insert capability
            conn.execute("""
                INSERT INTO capabilities (
                    id, name, capability_type, scope, project_path,
                    source_proposal_id, source_gap_id, installed_files_json,
                    settings_changes_json, installed_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """, (
                capability_id,
                proposal['capability_name'],
                proposal['capability_type'],
                proposal['scope'],
                proposal.get('project_path'),
                proposal['id'],
                proposal['gap_id'],
                proposal['files_json'],
                json.dumps(rollback_info),  # Store rollback info in settings_changes_json
                timestamp
            ))

            # Update proposal status
            conn.execute(
                "UPDATE proposals SET status = 'approved', reviewed_at = ?, reviewer_action = 'approve' WHERE id = ?",
                (timestamp, proposal['id'])
            )

            # Update gap status
            conn.execute(
                "UPDATE gaps SET status = 'resolved', updated_at = ? WHERE id = ?",
                (timestamp, proposal['gap_id'])
            )

            conn.commit()

    except Exception as e:
        # Rollback files on database error
        _rollback_files(rollback_info)
        return InstallationResult(
            success=False,
            capability_id="",
            message=f"Database error: {e}",
            files_created=[]
        )

    return InstallationResult(
        success=True,
        capability_id=capability_id,
        message=f"Installed capability: {proposal['capability_name']}",
        files_created=created_files,
        rollback_info=rollback_info
    )


def reject_proposal(proposal_id: str, reason: str = "", db_path: Union[str, Path] = None) -> bool:
    """Reject a proposal."""
    if db_path is None:
        db_path = DB_PATH
    proposal = get_proposal(proposal_id, db_path=db_path)
    if not proposal:
        return False

    if proposal['status'] != 'pending':
        return False

    timestamp = get_timestamp()

    try:
        with get_db_connection(db_path) as conn:
            # Update proposal
            conn.execute(
                """UPDATE proposals
                   SET status = 'rejected', rejection_reason = ?, reviewed_at = ?, reviewer_action = 'reject'
                   WHERE id = ?""",
                (reason, timestamp, proposal['id'])
            )

            # Update gap - back to pending so it can be re-synthesized
            conn.execute(
                "UPDATE gaps SET status = 'pending', resolved_by_proposal_id = NULL WHERE id = ?",
                (proposal['gap_id'],)
            )

            conn.commit()
            return True

    except Exception:
        return False


def rollback_capability(capability_id: str, force: bool = False, db_path: Union[str, Path] = None) -> InstallationResult:
    """
    Rollback an installed capability.

    Args:
        capability_id: ID or name of capability to rollback
        force: If True, rollback even with optional dependents (still blocks on required)
        db_path: Optional database path for project-scoped operations
    """
    if db_path is None:
        db_path = DB_PATH
    capability = get_capability(capability_id, db_path=db_path)
    if not capability:
        return InstallationResult(
            success=False,
            capability_id="",
            message=f"Capability not found: {capability_id}",
            files_created=[]
        )

    if capability['status'] != 'active':
        return InstallationResult(
            success=False,
            capability_id="",
            message=f"Capability is not active (status: {capability['status']})",
            files_created=[]
        )

    # Check for dependents
    rollback_check = check_rollback_safe(capability['id'], db_path=db_path)
    if not rollback_check['safe']:
        return InstallationResult(
            success=False,
            capability_id=capability['id'],
            message=rollback_check['message'],
            files_created=[]
        )

    # Warn about optional dependents if not forcing
    if rollback_check['dependents'] and not force:
        optional_deps = [d for d in rollback_check['dependents']
                        if d['dependency_type'] in ('optional', 'suggested')]
        if optional_deps:
            cap_names = [d['capability_name'] for d in optional_deps]
            return InstallationResult(
                success=False,
                capability_id=capability['id'],
                message=f"Has optional dependents: {', '.join(cap_names)}. Use --force to rollback anyway.",
                files_created=[]
            )

    # Parse rollback info (stored in settings_changes_json)
    try:
        rollback_info = json.loads(capability['settings_changes_json'] or '{}')
    except json.JSONDecodeError:
        rollback_info = {}

    # Perform rollback
    removed_files = _rollback_files(rollback_info)

    # Update database
    timestamp = get_timestamp()
    try:
        with get_db_connection(db_path) as conn:
            # Mark capability as rolled back
            conn.execute(
                "UPDATE capabilities SET status = 'rolled_back', rolled_back_at = ? WHERE id = ?",
                (timestamp, capability['id'])
            )

            # Update proposal if exists
            if capability.get('source_proposal_id'):
                conn.execute(
                    "UPDATE proposals SET status = 'rolled_back' WHERE id = ?",
                    (capability['source_proposal_id'],)
                )

            conn.commit()

    except Exception as e:
        return InstallationResult(
            success=False,
            capability_id=capability['id'],
            message=f"Rollback partial - database error: {e}",
            files_created=removed_files
        )

    return InstallationResult(
        success=True,
        capability_id=capability['id'],
        message=f"Rolled back capability: {capability['name']}",
        files_created=removed_files
    )


def _rollback_files(rollback_info: Dict[str, Any]) -> List[str]:
    """Rollback file changes using rollback info."""
    affected_files = []

    # Restore backups first
    for backup in rollback_info.get('backups', []):
        original = Path(backup['original'])
        backup_path = Path(backup['backup'])
        if backup_path.exists():
            shutil.copy2(backup_path, original)
            backup_path.unlink()
            affected_files.append(str(original))

    # Remove created files (that weren't backups)
    backed_up_originals = {b['original'] for b in rollback_info.get('backups', [])}
    for file_info in rollback_info.get('files', []):
        if file_info['action'] == 'created' and file_info['path'] not in backed_up_originals:
            path = Path(file_info['path'])
            if path.exists():
                path.unlink()
                affected_files.append(str(path))

    return affected_files


# =============================================================================
# Capability Dependencies
# =============================================================================

def add_dependency(
    capability_id: str,
    depends_on_id: str,
    dependency_type: str = "required",
    notes: str = None,
    db_path: Union[str, Path] = None
) -> bool:
    """
    Add a dependency between two capabilities.

    Args:
        capability_id: The capability that has the dependency
        depends_on_id: The capability that is depended upon
        dependency_type: 'required', 'optional', or 'suggested'
        notes: Optional notes about the dependency
        db_path: Optional database path for project-scoped operations

    Returns:
        True if successful, False otherwise
    """
    if db_path is None:
        db_path = DB_PATH
    if dependency_type not in ('required', 'optional', 'suggested'):
        return False

    try:
        with get_db_connection(db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO capability_dependencies
                   (capability_id, depends_on_id, dependency_type, added_at, notes)
                   VALUES (?, ?, ?, ?, ?)""",
                (capability_id, depends_on_id, dependency_type, get_timestamp(), notes)
            )
            conn.commit()
            return True
    except Exception:
        return False


def remove_dependency(capability_id: str, depends_on_id: str, db_path: Union[str, Path] = None) -> bool:
    """Remove a dependency between two capabilities."""
    if db_path is None:
        db_path = DB_PATH
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM capability_dependencies WHERE capability_id = ? AND depends_on_id = ?",
                (capability_id, depends_on_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    except Exception:
        return False


def get_dependencies(capability_id: str, db_path: Union[str, Path] = None) -> List[Dict[str, Any]]:
    """
    Get all capabilities that a capability depends on.

    Returns list of dicts with: depends_on_id, depends_on_name, dependency_type, notes
    """
    if db_path is None:
        db_path = DB_PATH
    # First get the capability by ID or name
    cap = get_capability(capability_id, db_path=db_path)
    if not cap:
        return []

    return db_execute(
        """SELECT
               cd.depends_on_id,
               c.name as depends_on_name,
               cd.dependency_type,
               cd.notes
           FROM capability_dependencies cd
           JOIN capabilities c ON cd.depends_on_id = c.id
           WHERE cd.capability_id = ?
           AND c.status = 'active'""",
        (cap['id'],),
        db_path=db_path
    )


def get_dependents(capability_id: str, db_path: Union[str, Path] = None) -> List[Dict[str, Any]]:
    """
    Get all capabilities that depend on this capability.

    Returns list of dicts with: capability_id, capability_name, dependency_type
    """
    if db_path is None:
        db_path = DB_PATH
    # First get the capability by ID or name
    cap = get_capability(capability_id, db_path=db_path)
    if not cap:
        return []

    return db_execute(
        """SELECT
               cd.capability_id,
               c.name as capability_name,
               cd.dependency_type
           FROM capability_dependencies cd
           JOIN capabilities c ON cd.capability_id = c.id
           WHERE cd.depends_on_id = ?
           AND c.status = 'active'""",
        (cap['id'],),
        db_path=db_path
    )


def check_rollback_safe(capability_id: str, db_path: Union[str, Path] = None) -> Dict[str, Any]:
    """
    Check if a capability can be safely rolled back.

    Returns dict with:
        - safe: bool, True if safe to rollback
        - dependents: list of capabilities that depend on this one
        - message: explanation
    """
    if db_path is None:
        db_path = DB_PATH
    dependents = get_dependents(capability_id, db_path=db_path)

    if not dependents:
        return {
            'safe': True,
            'dependents': [],
            'message': 'No dependents found'
        }

    # Check for required dependencies
    required_deps = [d for d in dependents if d['dependency_type'] == 'required']
    optional_deps = [d for d in dependents if d['dependency_type'] in ('optional', 'suggested')]

    if required_deps:
        cap_names = [d['capability_name'] for d in required_deps]
        return {
            'safe': False,
            'dependents': dependents,
            'message': f"Cannot rollback: required by {', '.join(cap_names)}"
        }

    if optional_deps:
        cap_names = [d['capability_name'] for d in optional_deps]
        return {
            'safe': True,
            'dependents': dependents,
            'message': f"Warning: optional/suggested dependency for {', '.join(cap_names)}"
        }

    return {
        'safe': True,
        'dependents': dependents,
        'message': 'Safe to rollback'
    }


def format_proposal_review(proposal: Dict[str, Any]) -> str:
    """Format a proposal for human review."""
    files = json.loads(proposal.get('files_json', '[]'))

    output = []
    output.append("=" * 70)
    output.append(f"PROPOSAL REVIEW: {proposal['id']}")
    output.append("=" * 70)
    output.append("")
    output.append(f"Type: {proposal['capability_type'].upper()}")
    output.append(f"Name: {proposal['capability_name']}")
    output.append(f"Summary: {proposal['capability_summary']}")
    output.append(f"Scope: {proposal['scope']}")
    output.append(f"Confidence: {proposal['confidence']:.2f}")
    output.append(f"Status: {proposal['status']}")
    output.append("")
    output.append("-" * 50)
    output.append("ORIGIN GAP")
    output.append("-" * 50)
    output.append(f"Gap ID: {proposal['gap_id']}")
    output.append(f"Gap Type: {proposal.get('origin_gap_type', 'N/A')}")
    output.append(f"Desired: {proposal.get('desired_capability', 'N/A')}")
    output.append("")
    output.append("-" * 50)
    output.append("REASONING")
    output.append("-" * 50)
    output.append(proposal.get('reasoning', 'No reasoning provided'))
    output.append("")
    output.append("-" * 50)
    output.append("FILES TO CREATE")
    output.append("-" * 50)

    for i, file_info in enumerate(files, 1):
        output.append(f"\n[{i}] {file_info['action'].upper()}: {file_info['path']}")
        output.append("-" * 40)
        content = file_info.get('content', '')
        # Show first 50 lines
        lines = content.split('\n')
        preview = '\n'.join(lines[:50])
        if len(lines) > 50:
            preview += f"\n... ({len(lines) - 50} more lines)"
        output.append(preview)
        output.append("")

    output.append("=" * 70)
    output.append("ACTIONS")
    output.append("=" * 70)
    output.append(f"  Approve: homunculus approve {proposal['id'][:12]}")
    output.append(f"  Reject:  homunculus reject {proposal['id'][:12]} --reason \"...\"")
    output.append("")

    return '\n'.join(output)
