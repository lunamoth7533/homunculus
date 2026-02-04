#!/usr/bin/env python3
"""
Tests for Phase 4: Review & Installation
"""

import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest import TestCase, main

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from installer import (
    InstallationResult, get_proposal, get_capability,
    install_proposal, reject_proposal, rollback_capability,
    format_proposal_review, _rollback_files
)
from synthesizer import CapabilitySynthesizer
from utils import HOMUNCULUS_ROOT, get_db_connection, db_execute, generate_id, get_timestamp


class TestInstallationResult(TestCase):
    """Test InstallationResult dataclass."""

    def test_success_result(self):
        result = InstallationResult(
            success=True,
            capability_id="cap-123",
            message="Installed successfully",
            files_created=["/path/to/file.md"]
        )
        self.assertTrue(result.success)
        self.assertEqual(result.capability_id, "cap-123")
        self.assertEqual(len(result.files_created), 1)

    def test_failure_result(self):
        result = InstallationResult(
            success=False,
            capability_id="",
            message="Installation failed",
            files_created=[]
        )
        self.assertFalse(result.success)
        self.assertEqual(result.capability_id, "")


class TestGetProposal(TestCase):
    """Test proposal retrieval."""

    def test_get_nonexistent_proposal(self):
        result = get_proposal("nonexistent-id-12345")
        self.assertIsNone(result)

    def test_get_proposal_partial_id(self):
        # First create a proposal in the database
        proposals = db_execute(
            "SELECT id FROM proposals WHERE status = 'pending' LIMIT 1"
        )
        if proposals:
            full_id = proposals[0]['id']
            partial_id = full_id[:8]
            result = get_proposal(partial_id)
            self.assertIsNotNone(result)
            self.assertEqual(result['id'], full_id)


class TestFormatProposalReview(TestCase):
    """Test proposal review formatting."""

    def test_format_includes_required_sections(self):
        proposal = {
            'id': 'prop-test-123',
            'capability_type': 'skill',
            'capability_name': 'test-skill',
            'capability_summary': 'Test summary',
            'scope': 'global',
            'confidence': 0.8,
            'status': 'pending',
            'gap_id': 'gap-123',
            'origin_gap_type': 'tool',
            'desired_capability': 'Test capability',
            'reasoning': 'Test reasoning',
            'files_json': json.dumps([{
                'path': 'test/path.md',
                'content': '# Test',
                'action': 'create'
            }])
        }

        output = format_proposal_review(proposal)

        self.assertIn('PROPOSAL REVIEW', output)
        self.assertIn('prop-test-123', output)
        self.assertIn('SKILL', output)
        self.assertIn('test-skill', output)
        self.assertIn('ORIGIN GAP', output)
        self.assertIn('REASONING', output)
        self.assertIn('FILES TO CREATE', output)
        self.assertIn('ACTIONS', output)


class TestRollbackFiles(TestCase):
    """Test file rollback functionality."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_rollback_created_file(self):
        # Create a test file
        test_file = Path(self.test_dir) / "test.txt"
        test_file.write_text("test content")

        rollback_info = {
            'files': [{'path': str(test_file), 'action': 'created'}],
            'backups': []
        }

        affected = _rollback_files(rollback_info)

        self.assertFalse(test_file.exists())
        self.assertEqual(len(affected), 1)

    def test_rollback_restores_backup(self):
        # Create original and backup files
        test_file = Path(self.test_dir) / "test.txt"
        backup_file = Path(self.test_dir) / "test.txt.backup"

        test_file.write_text("new content")
        backup_file.write_text("original content")

        rollback_info = {
            'files': [{'path': str(test_file), 'action': 'modified'}],
            'backups': [{'original': str(test_file), 'backup': str(backup_file)}]
        }

        _rollback_files(rollback_info)

        # Original should be restored
        self.assertTrue(test_file.exists())
        self.assertEqual(test_file.read_text(), "original content")
        # Backup should be removed
        self.assertFalse(backup_file.exists())


class TestRejectProposal(TestCase):
    """Test proposal rejection."""

    def test_reject_nonexistent_proposal(self):
        result = reject_proposal("nonexistent-id-12345", "Test reason")
        self.assertFalse(result)


class TestInstallerModule(TestCase):
    """Test installer module components."""

    def test_module_imports(self):
        # Just verify all exports work
        from installer import (
            InstallationResult, get_proposal, get_capability,
            install_proposal, reject_proposal, rollback_capability,
            format_proposal_review
        )
        self.assertTrue(callable(get_proposal))
        self.assertTrue(callable(install_proposal))


class TestCLIReview(TestCase):
    """Test CLI review command integration."""

    def test_review_command_runs(self):
        import subprocess
        result = subprocess.run(
            ["python3", str(HOMUNCULUS_ROOT / "scripts" / "cli.py"), "review", "nonexistent"],
            capture_output=True,
            text=True
        )
        # Should fail gracefully for nonexistent proposal
        self.assertIn("not found", result.stdout.lower())


class TestCLIReject(TestCase):
    """Test CLI reject command integration."""

    def test_reject_command_runs(self):
        import subprocess
        result = subprocess.run(
            ["python3", str(HOMUNCULUS_ROOT / "scripts" / "cli.py"), "reject", "nonexistent", "--reason", "test"],
            capture_output=True,
            text=True
        )
        # Should fail gracefully for nonexistent proposal
        self.assertIn("not found", result.stdout.lower())


class TestCLIRollback(TestCase):
    """Test CLI rollback command integration."""

    def test_rollback_command_runs(self):
        import subprocess
        result = subprocess.run(
            ["python3", str(HOMUNCULUS_ROOT / "scripts" / "cli.py"), "rollback", "nonexistent"],
            capture_output=True,
            text=True
        )
        # Should fail gracefully for nonexistent capability
        self.assertIn("not found", result.stdout.lower())


class TestInstallWorkflow(TestCase):
    """Test the complete install/rollback workflow."""

    def setUp(self):
        """Create a test proposal for workflow testing."""
        self.test_gap_id = generate_id("gap")
        self.test_proposal_id = generate_id("prop")
        timestamp = get_timestamp()

        # Create test gap
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO gaps (
                    id, detected_at, gap_type, domain, confidence,
                    recommended_scope, desired_capability, detector_rule_id, status
                ) VALUES (?, ?, 'tool', 'test', 0.8, 'global', 'Test capability', 'test-detector', 'pending')
            """, (self.test_gap_id, timestamp))

            # Create test proposal (must use allowed path in evolved/skills/)
            files = [{"path": "evolved/skills/test-workflow-skill.md", "content": "# Test", "action": "create"}]
            conn.execute("""
                INSERT INTO proposals (
                    id, created_at, gap_id, capability_type, capability_name,
                    capability_summary, scope, confidence, reasoning,
                    template_id, template_version, synthesis_model, status, files_json
                ) VALUES (?, ?, ?, 'skill', 'test-workflow-skill', 'Test summary', 'global', 0.8,
                          'Test reasoning', 'test-template', 1, 'test', 'pending', ?)
            """, (self.test_proposal_id, timestamp, self.test_gap_id, json.dumps(files)))
            conn.commit()

        self.cleanup_files = []

    def tearDown(self):
        """Clean up test data."""
        for f in self.cleanup_files:
            if Path(f).exists():
                Path(f).unlink()

        # Clean up test files
        test_file = HOMUNCULUS_ROOT / "evolved" / "skills" / "test-workflow-skill.md"
        if test_file.exists():
            test_file.unlink()

        # Clean up database entries
        with get_db_connection() as conn:
            conn.execute("DELETE FROM capabilities WHERE name = 'test-workflow-skill'")
            conn.execute("DELETE FROM proposals WHERE id = ?", (self.test_proposal_id,))
            conn.execute("DELETE FROM gaps WHERE id = ?", (self.test_gap_id,))
            conn.commit()

    def test_install_creates_file(self):
        result = install_proposal(self.test_proposal_id)

        self.assertTrue(result.success)
        self.assertGreater(len(result.files_created), 0)
        self.cleanup_files.extend(result.files_created)

        # Verify file was created
        created_file = Path(result.files_created[0])
        self.assertTrue(created_file.exists())

    def test_install_updates_database(self):
        result = install_proposal(self.test_proposal_id)
        self.cleanup_files.extend(result.files_created)

        self.assertTrue(result.success)

        # Check proposal status was updated
        proposal = get_proposal(self.test_proposal_id)
        self.assertEqual(proposal['status'], 'installed')

        # Check capability was created
        capability = get_capability('test-workflow-skill')
        self.assertIsNotNone(capability)
        self.assertEqual(capability['status'], 'active')

    def test_rollback_removes_file(self):
        # First install
        install_result = install_proposal(self.test_proposal_id)
        self.assertTrue(install_result.success)

        # Then rollback
        rollback_result = rollback_capability(install_result.capability_id)
        self.assertTrue(rollback_result.success)

        # Verify file was removed
        for f in install_result.files_created:
            self.assertFalse(Path(f).exists())


if __name__ == "__main__":
    main()
