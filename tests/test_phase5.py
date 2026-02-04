#!/usr/bin/env python3
"""
Tests for Phase 5: Meta-Evolution (Layer 2)
"""

import sys
import json
from pathlib import Path
from unittest import TestCase, main

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from meta_evolution import (
    MetaObservation, MetaProposal, MetaEvolutionEngine, run_meta_evolution
)
from utils import HOMUNCULUS_ROOT, db_execute


class TestMetaObservation(TestCase):
    """Test MetaObservation dataclass."""

    def test_create_observation(self):
        obs = MetaObservation(
            id="meta-test-123",
            timestamp="2024-01-01T00:00:00Z",
            observation_type="detector_performance",
            subject_type="detector_rule",
            subject_id="test-detector",
            metrics={"gaps_detected": 10, "approval_rate": 0.8},
            insight="Test insight",
            confidence=0.75
        )

        self.assertEqual(obs.id, "meta-test-123")
        self.assertEqual(obs.observation_type, "detector_performance")
        self.assertEqual(obs.metrics['gaps_detected'], 10)


class TestMetaProposal(TestCase):
    """Test MetaProposal dataclass."""

    def test_create_proposal(self):
        prop = MetaProposal(
            id="mprop-test-123",
            observation_id="meta-123",
            proposal_type="detector_patch",
            target_id="test-detector",
            target_version=1,
            changes={"min_confidence": 0.5},
            reasoning="Test reasoning",
            confidence=0.65
        )

        self.assertEqual(prop.id, "mprop-test-123")
        self.assertEqual(prop.proposal_type, "detector_patch")


class TestMetaEvolutionEngine(TestCase):
    """Test MetaEvolutionEngine."""

    def setUp(self):
        self.engine = MetaEvolutionEngine()

    def test_engine_initializes(self):
        self.assertIsNotNone(self.engine)
        self.assertTrue(hasattr(self.engine, 'enabled'))

    def test_collect_detector_metrics(self):
        metrics = self.engine.collect_detector_metrics()
        self.assertIsInstance(metrics, list)

    def test_collect_template_metrics(self):
        metrics = self.engine.collect_template_metrics()
        self.assertIsInstance(metrics, list)

    def test_analyze_detector_performance_high_dismissal(self):
        """Test that high dismissal rate is detected."""
        metrics = {
            'detector_rule_id': 'test-detector',
            'detector_rule_version': 1,
            'gaps_detected': 10,
            'proposals_approved': 1,
            'proposals_rejected': 1,
            'gaps_dismissed': 8,
        }

        obs = self.engine.analyze_detector_performance(metrics)

        self.assertIsNotNone(obs)
        self.assertIn('dismissal', obs.insight.lower())
        self.assertEqual(obs.subject_id, 'test-detector')

    def test_analyze_detector_performance_low_approval(self):
        """Test that low approval rate is detected."""
        metrics = {
            'detector_rule_id': 'test-detector-2',
            'detector_rule_version': 1,
            'gaps_detected': 10,
            'proposals_approved': 1,
            'proposals_rejected': 7,
            'gaps_dismissed': 2,
        }

        obs = self.engine.analyze_detector_performance(metrics)

        self.assertIsNotNone(obs)
        self.assertIn('approval', obs.insight.lower())

    def test_analyze_detector_performance_good(self):
        """Test that good performance is recognized."""
        metrics = {
            'detector_rule_id': 'test-detector-3',
            'detector_rule_version': 1,
            'gaps_detected': 10,
            'proposals_approved': 8,
            'proposals_rejected': 1,
            'gaps_dismissed': 1,
        }

        obs = self.engine.analyze_detector_performance(metrics)

        self.assertIsNotNone(obs)
        self.assertIn('working well', obs.insight.lower())

    def test_analyze_template_performance_high_rollback(self):
        """Test that high rollback rate is detected."""
        metrics = {
            'template_id': 'test-template',
            'template_version': 1,
            'proposals_generated': 10,
            'approved': 5,
            'rejected': 2,
            'rolled_back': 3,
            'capabilities_active': 2,
        }

        obs = self.engine.analyze_template_performance(metrics)

        self.assertIsNotNone(obs)
        self.assertIn('rollback', obs.insight.lower())

    def test_analyze_template_performance_good(self):
        """Test that good template performance is recognized."""
        metrics = {
            'template_id': 'test-template-2',
            'template_version': 1,
            'proposals_generated': 10,
            'approved': 7,
            'rejected': 3,
            'rolled_back': 0,
            'capabilities_active': 7,
        }

        obs = self.engine.analyze_template_performance(metrics)

        self.assertIsNotNone(obs)
        self.assertIn('effective', obs.insight.lower())

    def test_insufficient_data_returns_none(self):
        """Test that insufficient data doesn't generate observations."""
        metrics = {
            'detector_rule_id': 'test-detector-sparse',
            'detector_rule_version': 1,
            'gaps_detected': 1,
            'proposals_approved': 0,
            'proposals_rejected': 0,
            'gaps_dismissed': 0,
        }

        obs = self.engine.analyze_detector_performance(metrics)
        self.assertIsNone(obs)

    def test_get_status(self):
        status = self.engine.get_status()

        self.assertIn('enabled', status)
        self.assertIn('observations', status)
        self.assertIn('proposals', status)
        self.assertIsInstance(status['observations']['total'], int)

    def test_generate_proposals_from_observations(self):
        # Create a problematic observation
        obs = MetaObservation(
            id="meta-test-prop",
            timestamp="2024-01-01T00:00:00Z",
            observation_type="detector_performance",
            subject_type="detector_rule",
            subject_id="test-detector-prop",
            metrics={"dismissal_rate": 0.6},
            insight="High dismissal rate (60%): detector may be generating false positives",
            confidence=0.7
        )

        proposals = self.engine.generate_proposals([obs])

        # Should generate a proposal to fix the detector
        self.assertGreater(len(proposals), 0)
        self.assertEqual(proposals[0].proposal_type, "detector_patch")


class TestRunMetaEvolution(TestCase):
    """Test the main run_meta_evolution function."""

    def test_run_returns_dict(self):
        result = run_meta_evolution()

        self.assertIsInstance(result, dict)
        self.assertIn('enabled', result)
        self.assertIn('observations', result)
        self.assertIn('proposals', result)


class TestCLIMetaStatus(TestCase):
    """Test CLI meta-status command integration."""

    def test_meta_status_command_runs(self):
        import subprocess
        result = subprocess.run(
            ["python3", str(HOMUNCULUS_ROOT / "scripts" / "cli.py"), "meta-status"],
            capture_output=True,
            text=True
        )
        # Should run without error
        self.assertIn("META-EVOLUTION", result.stdout.upper())
        self.assertIn("enabled", result.stdout.lower())

    def test_meta_status_analyze_flag(self):
        import subprocess
        result = subprocess.run(
            ["python3", str(HOMUNCULUS_ROOT / "scripts" / "cli.py"), "meta-status", "--analyze"],
            capture_output=True,
            text=True
        )
        self.assertIn("meta-analysis", result.stdout.lower())


if __name__ == "__main__":
    main()
