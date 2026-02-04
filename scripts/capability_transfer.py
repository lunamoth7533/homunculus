#!/usr/bin/env python3
"""
Capability export/import for Homunculus.
Allows sharing evolved capabilities between users or projects.
"""

import json
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

import os
import stat
from utils import (
    HOMUNCULUS_ROOT, get_db_connection, db_execute, get_timestamp,
    generate_id
)
from installer import (
    validate_install_path, safe_path_join, validate_content
)

EXPORT_VERSION = "1.0"


def export_capability(capability_name: str) -> Optional[Dict[str, Any]]:
    """
    Export a capability to a portable dictionary format.

    Args:
        capability_name: Name or ID of capability to export

    Returns:
        Dictionary with capability data, or None if not found
    """
    # Get capability from database
    caps = db_execute(
        """SELECT c.*, p.files_json, p.reasoning, g.gap_type, g.domain,
                  g.desired_capability, g.evidence_summary
           FROM capabilities c
           LEFT JOIN proposals p ON c.source_proposal_id = p.id
           LEFT JOIN gaps g ON c.source_gap_id = g.id
           WHERE c.name = ? OR c.id = ? OR c.id LIKE ?""",
        (capability_name, capability_name, f"{capability_name}%")
    )

    if not caps:
        return None

    cap = caps[0]

    # Parse files
    try:
        files = json.loads(cap.get('files_json') or '[]')
    except json.JSONDecodeError:
        files = []

    # Read actual file contents from disk
    for f in files:
        rel_path = f.get('path', '')
        full_path = HOMUNCULUS_ROOT / rel_path
        if full_path.exists():
            try:
                f['content'] = full_path.read_text()
            except Exception:
                pass

    export_data = {
        "export_version": EXPORT_VERSION,
        "exported_at": get_timestamp(),
        "capability": {
            "name": cap['name'],
            "type": cap['capability_type'],
            "scope": cap['scope'],
            "installed_at": cap['installed_at'],
        },
        "origin": {
            "gap_type": cap.get('gap_type'),
            "domain": cap.get('domain'),
            "desired_capability": cap.get('desired_capability'),
            "reasoning": cap.get('reasoning'),
        },
        "files": files
    }

    return export_data


def export_to_file(capability_name: str, output_path: Optional[str] = None) -> Optional[str]:
    """
    Export capability to a JSON file.

    Args:
        capability_name: Name of capability to export
        output_path: Output file path (default: capability-{name}.json)

    Returns:
        Path to exported file, or None if failed
    """
    data = export_capability(capability_name)
    if not data:
        return None

    if output_path is None:
        safe_name = data['capability']['name'].replace('/', '-').replace('\\', '-')
        output_path = f"capability-{safe_name}.json"

    try:
        Path(output_path).write_text(json.dumps(data, indent=2))
        return output_path
    except Exception as e:
        print(f"Error writing export: {e}", file=sys.stderr)
        return None


def import_capability(
    import_data: Dict[str, Any],
    force: bool = False,
    skip_validation: bool = False
) -> Dict[str, Any]:
    """
    Import a capability from exported data.

    Args:
        import_data: Exported capability dictionary
        force: Overwrite if capability with same name exists
        skip_validation: Skip content validation (use with caution, for trusted sources only)

    Returns:
        Dict with import result (success, message, capability_id, warnings)
    """
    # Validate export format
    if import_data.get('export_version') != EXPORT_VERSION:
        return {
            'success': False,
            'message': f"Unsupported export version: {import_data.get('export_version')}"
        }

    cap_info = import_data.get('capability', {})
    files = import_data.get('files', [])

    if not cap_info.get('name') or not files:
        return {
            'success': False,
            'message': "Invalid import data: missing name or files"
        }

    # Check if capability already exists
    existing = db_execute(
        "SELECT id, name FROM capabilities WHERE name = ?",
        (cap_info['name'],)
    )

    if existing and not force:
        return {
            'success': False,
            'message': f"Capability '{cap_info['name']}' already exists. Use --force to overwrite."
        }

    # SECURITY: Validate paths and content before writing
    all_warnings = []
    if not skip_validation:
        for f in files:
            rel_path = f.get('path', '')
            content = f.get('content', '')

            if not rel_path:
                continue

            # Validate path is in allowed directory
            if not validate_install_path(rel_path):
                return {
                    'success': False,
                    'message': f"Import blocked: path not allowed: {rel_path}. Must be in evolved/"
                }

            # Validate content for suspicious patterns
            if content:
                warnings = validate_content(content, rel_path)
                if warnings:
                    all_warnings.extend([f"{rel_path}: {w}" for w in warnings])

    # If there are warnings, require explicit acknowledgment
    if all_warnings and not force:
        return {
            'success': False,
            'message': "Import blocked: suspicious content detected. Use --force to import anyway.",
            'warnings': all_warnings
        }

    # Write files with security measures
    files_created = []
    try:
        for f in files:
            rel_path = f.get('path', '')
            content = f.get('content', '')

            if not rel_path or not content:
                continue

            # SECURITY: Use safe_path_join to prevent path traversal
            try:
                full_path = safe_path_join(HOMUNCULUS_ROOT, rel_path)
            except ValueError as e:
                # Rollback and abort on path traversal attempt
                for created in files_created:
                    try:
                        Path(created).unlink()
                    except Exception:
                        pass
                return {
                    'success': False,
                    'message': f"Import blocked: {e}"
                }

            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)

            # SECURITY: Set restricted permissions (owner read/write only)
            os.chmod(full_path, stat.S_IRUSR | stat.S_IWUSR)  # 0600

            files_created.append(str(full_path))

    except Exception as e:
        # Rollback created files
        for f in files_created:
            try:
                Path(f).unlink()
            except Exception:
                pass
        return {
            'success': False,
            'message': f"Error writing files: {e}"
        }

    # Create capability record
    capability_id = generate_id("cap")
    timestamp = get_timestamp()

    try:
        with get_db_connection() as conn:
            # Delete existing if force
            if existing:
                conn.execute("DELETE FROM capabilities WHERE name = ?", (cap_info['name'],))

            conn.execute(
                """INSERT INTO capabilities (
                    id, name, capability_type, scope, source_proposal_id, source_gap_id,
                    installed_files_json, installed_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
                (
                    capability_id,
                    cap_info['name'],
                    cap_info.get('type', 'skill'),
                    cap_info.get('scope', 'global'),
                    'imported',  # Mark as imported
                    'imported',
                    json.dumps(files),
                    timestamp
                )
            )
            conn.commit()

    except Exception as e:
        # Rollback files
        for f in files_created:
            try:
                Path(f).unlink()
            except Exception:
                pass
        return {
            'success': False,
            'message': f"Database error: {e}"
        }

    result = {
        'success': True,
        'message': f"Imported capability: {cap_info['name']}",
        'capability_id': capability_id,
        'files_created': files_created
    }
    if all_warnings:
        result['warnings'] = all_warnings
    return result


def import_from_file(file_path: str, force: bool = False) -> Dict[str, Any]:
    """
    Import capability from a JSON file.

    Args:
        file_path: Path to import file
        force: Overwrite existing capability

    Returns:
        Import result dictionary
    """
    try:
        data = json.loads(Path(file_path).read_text())
        return import_capability(data, force)
    except json.JSONDecodeError as e:
        return {'success': False, 'message': f"Invalid JSON: {e}"}
    except FileNotFoundError:
        return {'success': False, 'message': f"File not found: {file_path}"}
    except Exception as e:
        return {'success': False, 'message': f"Error reading file: {e}"}


def list_exportable() -> List[Dict[str, Any]]:
    """List all capabilities that can be exported."""
    return db_execute(
        """SELECT name, capability_type, scope, installed_at
           FROM capabilities
           WHERE status = 'active'
           ORDER BY installed_at DESC"""
    )


def main():
    """CLI for capability transfer."""
    import argparse

    parser = argparse.ArgumentParser(description="Export/import capabilities")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # export
    export_parser = subparsers.add_parser("export", help="Export a capability")
    export_parser.add_argument("capability", help="Capability name or ID")
    export_parser.add_argument("-o", "--output", help="Output file path")

    # import
    import_parser = subparsers.add_parser("import", help="Import a capability")
    import_parser.add_argument("file", help="Import file path")
    import_parser.add_argument("--force", action="store_true", help="Overwrite existing")

    # list
    subparsers.add_parser("list", help="List exportable capabilities")

    args = parser.parse_args()

    if args.command == "export":
        result = export_to_file(args.capability, args.output)
        if result:
            print(f"Exported to: {result}")
        else:
            print("Export failed (capability not found?)")
            return 1

    elif args.command == "import":
        result = import_from_file(args.file, args.force)
        if result['success']:
            print(result['message'])
            if result.get('files_created'):
                print("Files created:")
                for f in result['files_created']:
                    print(f"  - {f}")
        else:
            print(f"Import failed: {result['message']}")
            return 1

    elif args.command == "list":
        caps = list_exportable()
        if not caps:
            print("No capabilities to export")
            return 0

        print(f"{'NAME':<30} {'TYPE':<10} {'SCOPE':<10} {'INSTALLED':<20}")
        print("-" * 70)
        for c in caps:
            installed = c['installed_at'][:10] if c['installed_at'] else '-'
            print(f"{c['name']:<30} {c['capability_type']:<10} {c['scope']:<10} {installed:<20}")

    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
