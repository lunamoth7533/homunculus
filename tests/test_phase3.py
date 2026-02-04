#!/usr/bin/env python3
"""
Tests for Phase 3: Capability Synthesis
"""

import sys
import json
import tempfile
from pathlib import Path
from unittest import TestCase, main

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from synthesizer import (
    SynthesisTemplate, Proposal, CapabilitySynthesizer,
    run_synthesis
)
from utils import HOMUNCULUS_ROOT, get_db_connection, db_execute


class TestSynthesisTemplate(TestCase):
    """Test synthesis template loading."""

    def test_from_yaml(self):
        data = {
            "id": "test-template",
            "version": 1,
            "output_type": "skill",
            "output_path": "evolved/skills/{slug}.md",
            "applicable_gap_types": ["tool", "knowledge"],
            "structure": "test structure",
            "synthesis_prompt": "test prompt"
        }
        template = SynthesisTemplate.from_yaml(data)
        self.assertEqual(template.id, "test-template")
        self.assertEqual(template.output_type, "skill")
        self.assertEqual(template.version, 1)
        self.assertIn("tool", template.applicable_gap_types)

    def test_defaults(self):
        data = {}
        template = SynthesisTemplate.from_yaml(data)
        self.assertEqual(template.id, "")
        self.assertEqual(template.version, 1)
        self.assertEqual(template.applicable_gap_types, [])


class TestCapabilitySynthesizer(TestCase):
    """Test the synthesis engine."""

    def setUp(self):
        self.synthesizer = CapabilitySynthesizer()

    def test_loads_templates(self):
        # Should load at least 5 templates
        self.assertGreaterEqual(len(self.synthesizer.templates), 5)

    def test_template_types(self):
        expected_types = ["skill", "hook", "agent", "command", "mcp_server"]
        for t in expected_types:
            self.assertIn(t, self.synthesizer.templates, f"Missing template: {t}")

    def test_select_template_for_tool_gap(self):
        template = self.synthesizer.select_template("tool")
        self.assertIsNotNone(template)
        # Tool gaps should get skill or mcp_server template
        self.assertIn(template.output_type, ["skill", "mcp_server"])

    def test_select_template_for_quality_gap(self):
        template = self.synthesizer.select_template("quality")
        self.assertIsNotNone(template)
        # Quality gaps should get hook template
        self.assertEqual(template.output_type, "hook")

    def test_select_template_for_workflow_gap(self):
        template = self.synthesizer.select_template("workflow")
        self.assertIsNotNone(template)
        # Workflow gaps could get agent or command
        self.assertIn(template.output_type, ["agent", "command", "skill"])

    def test_select_template_fallback(self):
        # Unknown gap type should fall back to skill
        template = self.synthesizer.select_template("unknown_type")
        self.assertIsNotNone(template)
        self.assertEqual(template.output_type, "skill")

    def test_generate_name(self):
        name = self.synthesizer._generate_name("Cannot read PDF files", "pdf")
        self.assertIn("pdf", name.lower())
        self.assertNotIn(" ", name)  # Should be slugified

    def test_generate_name_removes_prefix(self):
        name = self.synthesizer._generate_name("Can't do something special", None)
        self.assertNotIn("can't", name.lower())
        self.assertIn("something", name.lower())

    def test_slugify(self):
        slug = self.synthesizer._slugify("Test Name With Spaces!")
        self.assertEqual(slug, "test-name-with-spaces")
        # No special characters
        self.assertTrue(slug.replace("-", "").isalnum())

    def test_slugify_max_length(self):
        slug = self.synthesizer._slugify("a" * 100)
        self.assertLessEqual(len(slug), 50)

    def test_generate_summary(self):
        gap = {"desired_capability": "A" * 100}
        summary = self.synthesizer._generate_summary(gap)
        self.assertLessEqual(len(summary), 80)
        self.assertTrue(summary.endswith("..."))

    def test_synthesize_from_gap(self):
        gap = {
            "id": "gap-test-123",
            "gap_type": "tool",
            "desired_capability": "Cannot read PDF files directly",
            "domain": "pdf",
            "recommended_scope": "global",
            "confidence": 0.75,
            "evidence_summary": "Tool returned error"
        }
        proposal = self.synthesizer.synthesize_from_gap(gap)

        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.gap_id, "gap-test-123")
        self.assertEqual(proposal.gap_type, "tool")
        self.assertEqual(proposal.scope, "global")
        self.assertEqual(proposal.confidence, 0.75)
        self.assertGreater(len(proposal.files), 0)

    def test_synthesize_generates_content(self):
        gap = {
            "id": "gap-test-456",
            "gap_type": "tool",
            "desired_capability": "Cannot read PDF files",
            "domain": "pdf",
            "recommended_scope": "global",
            "confidence": 0.8,
            "evidence_summary": "Error occurred"
        }
        proposal = self.synthesizer.synthesize_from_gap(gap)

        # Check file content was generated
        self.assertEqual(len(proposal.files), 1)
        file_info = proposal.files[0]
        self.assertIn("path", file_info)
        self.assertIn("content", file_info)
        self.assertIn("action", file_info)
        self.assertEqual(file_info["action"], "create")

        # Content should have YAML frontmatter
        content = file_info["content"]
        self.assertTrue(content.startswith("---"))
        self.assertIn("name:", content)
        self.assertIn("evolved_from:", content)


class TestSynthesisTemplateFiles(TestCase):
    """Test that all synthesis template files exist and are valid."""

    def setUp(self):
        self.templates_dir = HOMUNCULUS_ROOT / "meta" / "synthesis-templates"

    def test_templates_dir_exists(self):
        self.assertTrue(self.templates_dir.exists())

    def test_skill_template_exists(self):
        self.assertTrue((self.templates_dir / "skill.yaml").exists())

    def test_hook_template_exists(self):
        self.assertTrue((self.templates_dir / "hook.yaml").exists())

    def test_agent_template_exists(self):
        self.assertTrue((self.templates_dir / "agent.yaml").exists())

    def test_command_template_exists(self):
        self.assertTrue((self.templates_dir / "command.yaml").exists())

    def test_mcp_server_template_exists(self):
        self.assertTrue((self.templates_dir / "mcp-server.yaml").exists())


class TestProposal(TestCase):
    """Test Proposal dataclass."""

    def test_proposal_fields(self):
        proposal = Proposal(
            id="prop-test-123",
            gap_id="gap-123",
            gap_type="tool",
            capability_type="skill",
            capability_name="test-skill",
            capability_summary="Test summary",
            scope="global",
            confidence=0.8,
            reasoning="Test reasoning",
            template_id="skill-template",
            template_version=1,
            files=[{"path": "test.md", "content": "test", "action": "create"}],
            rollback_instructions="rm test.md"
        )

        self.assertEqual(proposal.id, "prop-test-123")
        self.assertEqual(proposal.capability_type, "skill")
        self.assertEqual(proposal.project_path, None)  # Optional field


class TestGeneratedContent(TestCase):
    """Test generated capability content."""

    def setUp(self):
        self.synthesizer = CapabilitySynthesizer()

    def test_skill_content_structure(self):
        gap = {
            "id": "gap-skill-1",
            "gap_type": "tool",
            "desired_capability": "Read PDF files",
            "domain": "pdf",
            "recommended_scope": "global",
            "confidence": 0.8,
            "evidence_summary": "Error reading PDF"
        }
        content = self.synthesizer._generate_skill_content(
            gap, "pdf-reader", "pdf-reader", "2024-01-01T00:00:00Z"
        )

        # Check structure
        self.assertIn("---", content)
        self.assertIn("# Pdf Reader", content)  # Title case
        self.assertIn("## When to Use", content)
        self.assertIn("## What This Skill Does", content)
        self.assertIn("## Instructions", content)
        self.assertIn("## Examples", content)

    def test_hook_content_structure(self):
        gap = {
            "id": "gap-hook-1",
            "gap_type": "quality",
            "desired_capability": "Validate output",
            "domain": None,
            "recommended_scope": "global",
            "confidence": 0.7,
            "evidence_summary": "Quality issue"
        }
        content = self.synthesizer._generate_hook_content(
            gap, "validate-output", "validate-output", "2024-01-01T00:00:00Z"
        )

        self.assertIn("hook_type:", content)
        self.assertIn("PostToolUse", content)
        self.assertIn("~/.claude/settings.json", content)

    def test_agent_content_structure(self):
        gap = {
            "id": "gap-agent-1",
            "gap_type": "workflow",
            "desired_capability": "Complex task automation",
            "domain": "testing",
            "recommended_scope": "project",
            "confidence": 0.65,
            "evidence_summary": "Repetitive workflow"
        }
        content = self.synthesizer._generate_agent_content(
            gap, "task-automator", "task-automator", "2024-01-01T00:00:00Z"
        )

        self.assertIn("model:", content)
        self.assertIn("tools:", content)
        self.assertIn("## When to Dispatch", content)
        self.assertIn("Task(", content)

    def test_command_content_structure(self):
        gap = {
            "id": "gap-cmd-1",
            "gap_type": "workflow",
            "desired_capability": "Run test suite",
            "domain": "testing",
            "recommended_scope": "global",
            "confidence": 0.7,
            "evidence_summary": "Manual repetition"
        }
        content = self.synthesizer._generate_command_content(
            gap, "run-tests", "run-tests", "2024-01-01T00:00:00Z"
        )

        self.assertIn("command: true", content)
        self.assertIn("/run-tests", content)
        self.assertIn("## Usage", content)


class TestCLISynthesize(TestCase):
    """Test CLI synthesize command integration."""

    def test_synthesize_command_runs(self):
        import subprocess
        result = subprocess.run(
            ["python3", str(HOMUNCULUS_ROOT / "scripts" / "cli.py"), "synthesize"],
            capture_output=True,
            text=True
        )
        # Should run without error
        self.assertIn("SYNTHESIS", result.stdout.upper())
        self.assertIn("template", result.stdout.lower())


if __name__ == "__main__":
    main()
