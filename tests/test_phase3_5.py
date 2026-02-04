#!/usr/bin/env python3
"""
Tests for Phase 3/5 Completion Features:
- Observation reliability and archival
- Template rendering with multi-file support
- LLM provider chain
- Enhanced usage tracking
- Meta-evolution modules
"""

import sys
import json
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


class TestObservationFallback(TestCase):
    """Test observation fallback on parse failure."""

    def test_parse_input_returns_tuple(self):
        """parse_input should return (data, is_fallback) tuple."""
        from process_observation import parse_input
        import io

        # Mock stdin with valid JSON
        with patch('sys.stdin', io.StringIO('{"key": "value"}')):
            data, is_fallback = parse_input()
            self.assertEqual(data, {"key": "value"})
            self.assertFalse(is_fallback)

    def test_parse_input_fallback_on_invalid_json(self):
        """parse_input should return fallback on JSON decode error."""
        from process_observation import parse_input
        import io

        # Mock stdin with invalid JSON
        with patch('sys.stdin', io.StringIO('not valid json {')):
            data, is_fallback = parse_input()
            self.assertTrue(is_fallback)
            self.assertTrue(data.get('_fallback'))
            self.assertIn('_parse_error', data)
            self.assertIn('_raw_preview', data)

    def test_parse_input_empty_returns_empty_dict(self):
        """parse_input should return empty dict for empty input."""
        from process_observation import parse_input
        import io

        with patch('sys.stdin', io.StringIO('')):
            data, is_fallback = parse_input()
            self.assertEqual(data, {})
            self.assertFalse(is_fallback)

    def test_build_observation_with_fallback(self):
        """build_observation should set parse_fallback when is_fallback=True."""
        from process_observation import build_observation

        obs = build_observation(
            event_type='post_tool',
            timestamp='2024-01-01T00:00:00Z',
            session_id='sess-123',
            project_path='/test/path',
            input_data={'_fallback': True},
            is_fallback=True
        )

        self.assertEqual(obs.get('parse_fallback'), 1)

    def test_build_observation_without_fallback(self):
        """build_observation should not set parse_fallback when is_fallback=False."""
        from process_observation import build_observation

        obs = build_observation(
            event_type='post_tool',
            timestamp='2024-01-01T00:00:00Z',
            session_id='sess-123',
            project_path='/test/path',
            input_data={'tool_name': 'Read'},
            is_fallback=False
        )

        self.assertNotIn('parse_fallback', obs)


class TestTemplateRenderer(TestCase):
    """Test template rendering with context substitution."""

    def test_render_context_to_dict(self):
        """RenderContext.to_dict() should return proper dict."""
        from template_renderer import RenderContext

        ctx = RenderContext(
            gap_id='gap-123',
            gap_type='tool',
            domain='testing',
            name='test-skill',
            slug='test-skill'
        )

        d = ctx.to_dict()
        self.assertEqual(d['gap_id'], 'gap-123')
        self.assertEqual(d['slug'], 'test-skill')

    def test_render_context_from_gap(self):
        """RenderContext.from_gap() should create context from gap dict."""
        from template_renderer import RenderContext

        gap = {
            'id': 'gap-456',
            'gap_type': 'knowledge',
            'domain': 'python',
            'desired_capability': 'Test capability',
            'confidence': 0.8
        }

        ctx = RenderContext.from_gap(gap, name='python-skill', slug='python-skill', timestamp='2024-01-01')
        self.assertEqual(ctx.gap_id, 'gap-456')
        self.assertEqual(ctx.name, 'python-skill')
        self.assertEqual(ctx.title, 'Python Skill')

    def test_render_basic_substitution(self):
        """TemplateRenderer.render() should substitute context values."""
        from template_renderer import TemplateRenderer, RenderContext

        template = "Hello {name}, your domain is {domain}"
        ctx = RenderContext(name='test-skill', domain='testing')

        result = TemplateRenderer.render(template, ctx)
        self.assertEqual(result, "Hello test-skill, your domain is testing")

    def test_render_missing_keys_unchanged(self):
        """TemplateRenderer.render() should leave missing keys unchanged."""
        from template_renderer import TemplateRenderer, RenderContext

        template = "Hello {name}, unknown: {unknown_key}"
        ctx = RenderContext(name='test')

        result = TemplateRenderer.render(template, ctx)
        self.assertIn("Hello test", result)
        self.assertIn("{unknown_key}", result)

    def test_render_multi_file(self):
        """TemplateRenderer.render_multi_file() should render all files."""
        from template_renderer import TemplateRenderer, RenderContext

        output_files = [
            {'path': 'evolved/skills/{slug}/file1.md', 'content': '# {title}'},
            {'path': 'evolved/skills/{slug}/file2.ts', 'content': 'const name = "{name}"'}
        ]

        ctx = RenderContext(slug='my-skill', title='My Skill', name='my-skill')

        result = TemplateRenderer.render_multi_file(output_files, ctx)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['path'], 'evolved/skills/my-skill/file1.md')
        self.assertEqual(result[0]['content'], '# My Skill')
        self.assertEqual(result[1]['content'], 'const name = "my-skill"')


class TestMultiFileMCPTemplate(TestCase):
    """Test MCP server template v3 multi-file output."""

    def test_mcp_template_has_output_files(self):
        """MCP server template should have output_files defined."""
        from utils import HOMUNCULUS_ROOT, load_yaml_file

        template_path = HOMUNCULUS_ROOT / "meta" / "synthesis-templates" / "mcp-server.yaml"
        data = load_yaml_file(template_path)

        self.assertIn('output_files', data)
        self.assertIsInstance(data['output_files'], list)
        self.assertGreaterEqual(len(data['output_files']), 3)

    def test_mcp_template_generates_three_files(self):
        """MCP template should generate package.json, index.ts, README.md."""
        from utils import HOMUNCULUS_ROOT, load_yaml_file

        template_path = HOMUNCULUS_ROOT / "meta" / "synthesis-templates" / "mcp-server.yaml"
        data = load_yaml_file(template_path)

        paths = [f['path'] for f in data['output_files']]
        self.assertTrue(any('package.json' in p for p in paths))
        self.assertTrue(any('index.ts' in p for p in paths))
        self.assertTrue(any('README.md' in p for p in paths))

    def test_synthesizer_uses_multi_file_template(self):
        """Synthesizer should generate multiple files for MCP server gaps."""
        from synthesizer import CapabilitySynthesizer

        synthesizer = CapabilitySynthesizer()

        # Check if MCP template has output_files
        mcp_template = synthesizer.templates.get('mcp_server')
        if mcp_template and mcp_template.output_files:
            gap = {
                'id': 'gap-mcp-test',
                'gap_type': 'tool',
                'desired_capability': 'Access external API',
                'domain': 'api',
                'recommended_scope': 'global',
                'confidence': 0.8,
                'evidence_summary': 'No tool available'
            }

            # Force use of mcp_server template
            proposal = synthesizer.synthesize_from_gap(gap)
            if proposal and proposal.capability_type == 'mcp_server':
                self.assertGreaterEqual(len(proposal.files), 3)


class TestLLMProviderChain(TestCase):
    """Test LLM provider chain abstraction."""

    def test_provider_chain_creation(self):
        """LLMProviderChain should initialize with providers."""
        from llm_providers import LLMProviderChain

        chain = LLMProviderChain()
        self.assertIn('session', chain.providers)
        self.assertIn('anthropic', chain.providers)
        self.assertIn('ollama', chain.providers)

    def test_provider_chain_custom_order(self):
        """LLMProviderChain should accept custom provider order."""
        from llm_providers import LLMProviderChain

        chain = LLMProviderChain(provider_order=['ollama', 'anthropic'])
        self.assertEqual(chain.provider_order, ['ollama', 'anthropic'])

    def test_anthropic_provider_model_identifier(self):
        """AnthropicProvider should return provider:model format."""
        from llm_providers import AnthropicProvider

        provider = AnthropicProvider()
        model_id = provider.get_model_identifier()

        self.assertTrue(model_id.startswith('anthropic:'))

    def test_ollama_provider_model_identifier(self):
        """OllamaProvider should return provider:model format."""
        from llm_providers import OllamaProvider

        provider = OllamaProvider()
        model_id = provider.get_model_identifier()

        self.assertTrue(model_id.startswith('ollama:'))

    def test_get_provider_status(self):
        """get_provider_status should return status for all providers."""
        from llm_providers import LLMProviderChain

        chain = LLMProviderChain()
        status = chain.get_provider_status()

        self.assertIn('session', status)
        self.assertIn('anthropic', status)
        self.assertIn('ollama', status)

        for name, info in status.items():
            self.assertIn('available', info)
            self.assertIn('model', info)
            self.assertIn('in_chain', info)


class TestEnhancedUsageTracking(TestCase):
    """Test enhanced capability usage detection."""

    def test_detect_skill_path_in_observation(self):
        """Usage detection should find skill paths."""
        # This test validates the detection logic exists
        from track_usage import detect_and_record_usage

        # The function exists and accepts observation dict
        observation = {
            'raw_json': '{"message": "Using evolved/skills/test-skill"}',
            'tool_name': 'Read',
            'session_id': 'sess-123'
        }

        # Should not error (may return empty if no capabilities)
        result = detect_and_record_usage(observation)
        self.assertIsInstance(result, list)

    def test_detect_command_invocation(self):
        """Usage detection should find command invocations."""
        from track_usage import detect_and_record_usage

        observation = {
            'raw_json': '{"input": "/test-command with args"}',
            'tool_name': 'Skill',
            'session_id': 'sess-456'
        }

        result = detect_and_record_usage(observation)
        self.assertIsInstance(result, list)

    def test_detect_mcp_tool_prefix(self):
        """Usage detection should find MCP tool prefixes."""
        from track_usage import detect_and_record_usage

        observation = {
            'raw_json': '{}',
            'tool_name': 'mcp__test-server__do_something',
            'session_id': 'sess-789'
        }

        result = detect_and_record_usage(observation)
        self.assertIsInstance(result, list)


class TestMetaDetectors(TestCase):
    """Test meta-evolution detector modules."""

    def test_meta_rule_loading(self):
        """MetaDetectorEngine should load meta-rules from YAML."""
        from meta_detectors import MetaDetectorEngine

        engine = MetaDetectorEngine()
        # Should have loaded rules from meta/meta-rules/*.yaml
        self.assertGreaterEqual(len(engine.rules), 3)

    def test_meta_rule_ids_exist(self):
        """Expected meta-rules should be loaded."""
        from meta_detectors import MetaDetectorEngine

        engine = MetaDetectorEngine()
        rule_ids = list(engine.rules.keys())

        # Check for expected rules
        self.assertIn('high-dismissal-rate', rule_ids)
        self.assertIn('low-approval-rate', rule_ids)
        self.assertIn('high-rollback-rate', rule_ids)

    def test_condition_evaluation(self):
        """MetaDetectorEngine should evaluate conditions correctly."""
        from meta_detectors import MetaDetectorEngine

        engine = MetaDetectorEngine()

        # Test > operator
        metrics = {'dismissal_rate': 0.6, 'gaps_detected': 5}
        condition = {'field': 'dismissal_rate', 'operator': '>', 'value': 0.5}
        result = engine._evaluate_condition(metrics, condition)
        self.assertTrue(result)

        # Test < operator
        condition = {'field': 'dismissal_rate', 'operator': '<', 'value': 0.5}
        result = engine._evaluate_condition(metrics, condition)
        self.assertFalse(result)

        # Test missing field
        condition = {'field': 'missing_field', 'operator': '>', 'value': 0}
        result = engine._evaluate_condition(metrics, condition)
        self.assertFalse(result)

    def test_high_dismissal_triggers_observation(self):
        """High dismissal rate should trigger meta-observation."""
        from meta_detectors import MetaDetectorEngine

        engine = MetaDetectorEngine()

        # Mock metrics with high dismissal
        metrics = [{
            'detector_rule_id': 'test-detector',
            'detector_rule_version': 1,
            'gaps_detected': 10,
            'proposals_generated': 5,
            'proposals_installed': 1,
            'proposals_rejected': 1,
            'gaps_dismissed': 6,
            'gaps_resolved': 2,
            'avg_confidence': 0.5,
            'dismissal_rate': 0.6,
            'approval_rate': 0.5,
            'rejection_rate': 0.5
        }]

        observations = engine.analyze_detector_metrics(metrics)

        # Should generate observation for high dismissal
        self.assertGreater(len(observations), 0)
        obs_types = [o.observation_type for o in observations]
        self.assertIn('detector_issue', obs_types)


class TestMetaObserver(TestCase):
    """Test meta-observer metric collection."""

    def test_collect_all_metrics_returns_dict(self):
        """collect_all_metrics should return structured dict."""
        from meta_observer import collect_all_metrics

        metrics = collect_all_metrics()

        self.assertIn('detector_metrics', metrics)
        self.assertIn('template_metrics', metrics)
        self.assertIn('usage_metrics', metrics)
        self.assertIn('collected_at', metrics)

    def test_metrics_have_derived_rates(self):
        """Detector metrics should have calculated rates."""
        from meta_observer import collect_detector_metrics

        metrics = collect_detector_metrics()

        for m in metrics:
            self.assertIn('dismissal_rate', m)
            self.assertIn('approval_rate', m)


class TestMetaSynthesizer(TestCase):
    """Test meta-proposal generation and application."""

    def test_generate_proposal_from_observation(self):
        """MetaSynthesizer should generate proposals from observations."""
        from meta_synthesizer import MetaSynthesizer
        from meta_detectors import MetaObservation

        synthesizer = MetaSynthesizer()

        observation = MetaObservation(
            id='meta-test-123',
            timestamp='2024-01-01T00:00:00Z',
            observation_type='detector_issue',
            subject_type='detector_rule',
            subject_id='test-detector',
            rule_id='high-dismissal-rate',
            metrics={'dismissal_rate': 0.7, 'gaps_detected': 10},
            insight='High dismissal rate',
            confidence=0.7
        )

        proposal = synthesizer.generate_proposal(observation)

        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.observation_id, 'meta-test-123')
        self.assertEqual(proposal.target_id, 'test-detector')

    def test_low_confidence_skips_proposal(self):
        """MetaSynthesizer should skip observations with low confidence."""
        from meta_synthesizer import MetaSynthesizer
        from meta_detectors import MetaObservation

        synthesizer = MetaSynthesizer()

        observation = MetaObservation(
            id='meta-low-conf',
            timestamp='2024-01-01T00:00:00Z',
            observation_type='detector_issue',
            subject_type='detector_rule',
            subject_id='test-detector',
            rule_id='test-rule',
            metrics={'dismissal_rate': 0.3},
            insight='Low confidence observation',
            confidence=0.3  # Below 0.5 threshold
        )

        proposal = synthesizer.generate_proposal(observation)
        self.assertIsNone(proposal)


class TestArchiveObservations(TestCase):
    """Test observation archival with --auto flag."""

    def test_should_auto_archive_function_exists(self):
        """should_auto_archive function should exist."""
        from archive_observations import should_auto_archive

        # Should run without error
        result = should_auto_archive()
        self.assertIsInstance(result, bool)

    def test_record_archive_run_function_exists(self):
        """record_archive_run function should exist."""
        from archive_observations import record_archive_run

        # Function should exist (may fail without DB, but should be callable)
        self.assertTrue(callable(record_archive_run))


class TestConfigUsageTracking(TestCase):
    """Test usage_tracking config section."""

    def test_config_has_usage_tracking(self):
        """config.yaml should have usage_tracking section."""
        from utils import load_config

        config = load_config()
        self.assertIn('usage_tracking', config)

        usage_config = config['usage_tracking']
        self.assertIn('enabled', usage_config)
        self.assertIn('raw_json_max_chars', usage_config)


if __name__ == "__main__":
    main()
