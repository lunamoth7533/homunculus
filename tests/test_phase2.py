#!/usr/bin/env python3
"""
Tests for Phase 2: Gap Detection
"""

import sys
from pathlib import Path
from unittest import TestCase, main

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from gap_types import (
    GapType, get_gap_info, get_all_gap_types,
    get_default_scope, get_priority, get_capability_types
)
from detector import GapDetector, DetectorRule, DetectedGap, run_detection
from utils import HOMUNCULUS_ROOT


class TestGapTypes(TestCase):
    """Test gap type definitions."""

    def test_all_16_types_defined(self):
        types = get_all_gap_types()
        self.assertEqual(len(types), 16)

    def test_gap_type_enum_values(self):
        self.assertEqual(GapType.TOOL.value, "tool")
        self.assertEqual(GapType.KNOWLEDGE.value, "knowledge")
        self.assertEqual(GapType.WORKFLOW.value, "workflow")
        self.assertEqual(GapType.SELF_AWARENESS.value, "self_awareness")

    def test_get_gap_info(self):
        info = get_gap_info("tool")
        self.assertIn("description", info)
        self.assertIn("examples", info)
        self.assertIn("default_scope", info)
        self.assertIn("priority", info)

    def test_get_default_scope(self):
        self.assertEqual(get_default_scope("tool"), "global")
        self.assertEqual(get_default_scope("knowledge"), "project")
        self.assertEqual(get_default_scope("communication"), "session")

    def test_get_priority(self):
        self.assertEqual(get_priority("tool"), "high")
        self.assertEqual(get_priority("knowledge"), "medium")
        self.assertEqual(get_priority("permission"), "low")

    def test_get_capability_types(self):
        types = get_capability_types("tool")
        self.assertIn("skill", types)


class TestDetectorRule(TestCase):
    """Test detector rule loading."""

    def test_from_yaml(self):
        data = {
            "id": "test-detector",
            "version": 1,
            "gap_type": "tool",
            "priority": "high",
            "enabled": True,
            "triggers": [{"condition": "test"}],
            "min_confidence": 0.3
        }
        rule = DetectorRule.from_yaml(data)
        self.assertEqual(rule.id, "test-detector")
        self.assertEqual(rule.gap_type, "tool")
        self.assertTrue(rule.enabled)


class TestGapDetector(TestCase):
    """Test gap detection engine."""

    def setUp(self):
        self.detector = GapDetector()

    def test_loads_rules(self):
        # Should load all 16 rules
        self.assertGreaterEqual(len(self.detector.rules), 16)

    def test_rule_ids(self):
        expected_ids = [
            "tool-gap-detector",
            "knowledge-gap-detector",
            "workflow-gap-detector",
            "integration-gap-detector",
            "context-gap-detector",
            "permission-gap-detector",
            "quality-gap-detector",
            "speed-gap-detector",
            "communication-gap-detector",
            "recovery-gap-detector",
            "reasoning-gap-detector",
            "verification-gap-detector",
            "discovery-gap-detector",
            "learning-gap-detector",
            "evolution-gap-detector",
            "self-awareness-gap-detector"
        ]
        for rule_id in expected_ids:
            self.assertIn(rule_id, self.detector.rules, f"Missing rule: {rule_id}")

    def test_check_condition_contains(self):
        obs = {"raw_json": "I can't do this"}
        result = self.detector._check_condition("raw_json contains 'can'", obs)
        self.assertTrue(result)

    def test_check_condition_equals(self):
        obs = {"tool_success": 0}
        result = self.detector._check_condition("tool_success == 0", obs)
        self.assertTrue(result)

    def test_check_condition_greater_than(self):
        obs = {"friction_turn_count": 20}
        result = self.detector._check_condition("friction_turn_count > 15", obs)
        self.assertTrue(result)

    def test_detect_tool_gap(self):
        observations = [
            {
                "id": "obs-1",
                "event_type": "post_tool",
                "tool_name": "Read",
                "raw_json": "I can't read PDF files directly",
                "tool_success": 0,
                "tool_error": "PDF parsing not supported"
            }
        ]
        gaps = self.detector.detect_from_observations(observations)
        # Should detect at least a tool gap
        tool_gaps = [g for g in gaps if g.gap_type == "tool"]
        self.assertGreater(len(tool_gaps), 0)

    def test_detect_knowledge_gap(self):
        observations = [
            {
                "id": "obs-1",
                "event_type": "post_tool",
                "raw_json": "I'm unfamiliar with this codebase structure"
            }
        ]
        gaps = self.detector.detect_from_observations(observations)
        knowledge_gaps = [g for g in gaps if g.gap_type == "knowledge"]
        self.assertGreater(len(knowledge_gaps), 0)

    def test_deduplication(self):
        observations = [
            {"id": "obs-1", "raw_json": "I can't do X"},
            {"id": "obs-2", "raw_json": "I can't do X"},
            {"id": "obs-3", "raw_json": "I can't do X"},
        ]
        gaps = self.detector.detect_from_observations(observations)
        # Should deduplicate similar gaps
        tool_gaps = [g for g in gaps if g.gap_type == "tool"]
        # Even with 3 observations, should only have 1 unique gap per capability
        self.assertLessEqual(len(tool_gaps), 2)

    def test_infer_domain(self):
        obs = [{"raw_json": "git commit failed", "tool_name": "Bash"}]
        domain = self.detector._infer_domain(obs)
        self.assertEqual(domain, "git")

    def test_infer_scope(self):
        rule = DetectorRule(
            id="test", version=1, gap_type="tool", priority="high",
            enabled=True, triggers=[],
            scope_inference=[{"if": "default", "then": "global"}]
        )
        scope = self.detector._infer_scope(rule, [])
        self.assertEqual(scope, "global")


class TestDetectorRuleFiles(TestCase):
    """Test that all detector rule files are valid."""

    def setUp(self):
        self.rules_dir = HOMUNCULUS_ROOT / "meta" / "detector-rules"

    def test_rules_dir_exists(self):
        self.assertTrue(self.rules_dir.exists())

    def test_all_16_rule_files_exist(self):
        expected_files = [
            "tool-gap.yaml",
            "knowledge-gap.yaml",
            "workflow-gap.yaml",
            "integration-gap.yaml",
            "context-gap.yaml",
            "permission-gap.yaml",
            "quality-gap.yaml",
            "speed-gap.yaml",
            "communication-gap.yaml",
            "recovery-gap.yaml",
            "reasoning-gap.yaml",
            "verification-gap.yaml",
            "discovery-gap.yaml",
            "learning-gap.yaml",
            "evolution-gap.yaml",
            "self-awareness-gap.yaml"
        ]
        for filename in expected_files:
            filepath = self.rules_dir / filename
            self.assertTrue(filepath.exists(), f"Missing rule file: {filename}")


class TestCLIDetect(TestCase):
    """Test CLI detect command integration."""

    def test_detect_command_runs(self):
        import subprocess
        result = subprocess.run(
            ["python3", str(HOMUNCULUS_ROOT / "scripts" / "cli.py"), "detect"],
            capture_output=True,
            text=True
        )
        # Should run without error (even if no gaps detected)
        self.assertIn("detection", result.stdout.lower())


if __name__ == "__main__":
    main()
