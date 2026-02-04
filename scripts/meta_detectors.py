#!/usr/bin/env python3
"""
Meta-Detectors for Homunculus Layer 2.
Analyzes metrics to detect patterns requiring meta-evolution.

Loads rules from meta/meta-rules/*.yaml and applies them to collected metrics.
"""

import operator
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable

import sys
sys.path.insert(0, str(Path(__file__).parent))

from utils import HOMUNCULUS_ROOT, generate_id, get_timestamp, load_yaml_file
from meta_observer import (
    collect_detector_metrics, collect_template_metrics,
    collect_capability_usage_metrics, get_recent_rejections
)


@dataclass
class MetaObservation:
    """An observation about system performance requiring attention."""
    id: str
    timestamp: str
    observation_type: str  # 'detector_issue', 'template_issue', 'unused_capability', 'pattern'
    subject_type: str  # 'detector_rule', 'synthesis_template', 'capability', 'workflow'
    subject_id: str
    rule_id: str  # Which meta-rule triggered this
    metrics: Dict[str, Any]
    insight: str
    confidence: float
    recommended_action: Optional[str] = None


@dataclass
class MetaRule:
    """A rule for detecting meta-evolution opportunities."""
    id: str
    version: int
    target_type: str  # 'detector', 'template', 'capability'
    conditions: List[Dict[str, Any]]  # field, operator, value
    insight_template: str
    min_confidence: float
    proposal_type: str  # 'detector_patch', 'template_patch', 'deprecate', 'config_change'
    recommended_action: Optional[str] = None

    @classmethod
    def from_yaml(cls, data: Dict[str, Any]) -> 'MetaRule':
        return cls(
            id=data.get('id', ''),
            version=data.get('version', 1),
            target_type=data.get('target_type', ''),
            conditions=data.get('conditions', []),
            insight_template=data.get('insight_template', ''),
            min_confidence=data.get('min_confidence', 0.5),
            proposal_type=data.get('proposal_type', ''),
            recommended_action=data.get('recommended_action')
        )


# Operator mapping for condition evaluation
OPERATORS: Dict[str, Callable] = {
    '>': operator.gt,
    '>=': operator.ge,
    '<': operator.lt,
    '<=': operator.le,
    '==': operator.eq,
    '!=': operator.ne,
}


class MetaDetectorEngine:
    """Engine for running meta-detection rules against metrics."""

    def __init__(self, db_path=None):
        self.db_path = db_path
        self.rules: Dict[str, MetaRule] = {}
        self.rules_dir = HOMUNCULUS_ROOT / "meta" / "meta-rules"
        self._load_rules()

    def _load_rules(self):
        """Load all meta-rules from YAML files."""
        if not self.rules_dir.exists():
            return

        for rule_file in self.rules_dir.glob("*.yaml"):
            try:
                data = load_yaml_file(rule_file)
                if data and data.get('id'):
                    rule = MetaRule.from_yaml(data)
                    self.rules[rule.id] = rule
            except Exception as e:
                print(f"Warning: Failed to load meta-rule {rule_file}: {e}")

    def _evaluate_condition(self, metrics: Dict[str, Any], condition: Dict[str, Any]) -> bool:
        """Evaluate a single condition against metrics."""
        field = condition.get('field', '')
        op_str = condition.get('operator', '>')
        value = condition.get('value', 0)

        if field not in metrics:
            return False

        op_func = OPERATORS.get(op_str)
        if not op_func:
            return False

        try:
            return op_func(metrics[field], value)
        except (TypeError, ValueError):
            return False

    def _evaluate_rule(self, rule: MetaRule, metrics: Dict[str, Any]) -> bool:
        """Evaluate all conditions of a rule against metrics."""
        if not rule.conditions:
            return False

        # All conditions must be true (AND logic)
        for condition in rule.conditions:
            if not self._evaluate_condition(metrics, condition):
                return False

        return True

    def _calculate_confidence(self, rule: MetaRule, metrics: Dict[str, Any]) -> float:
        """Calculate confidence score for a triggered rule."""
        # Base confidence from rule
        confidence = rule.min_confidence

        # Adjust based on sample size
        sample_size = metrics.get('gaps_detected', metrics.get('proposals_generated', 0))
        if sample_size >= 10:
            confidence = min(0.95, confidence + 0.2)
        elif sample_size >= 5:
            confidence = min(0.85, confidence + 0.1)

        return confidence

    def _format_insight(self, rule: MetaRule, metrics: Dict[str, Any], subject_id: str) -> str:
        """Format the insight message with metrics."""
        try:
            # Add subject_id to metrics for formatting
            format_dict = {**metrics, 'subject_id': subject_id}
            return rule.insight_template.format(**format_dict)
        except (KeyError, ValueError):
            return rule.insight_template

    def analyze_detector_metrics(self, metrics: List[Dict[str, Any]] = None) -> List[MetaObservation]:
        """Analyze detector performance metrics."""
        if metrics is None:
            metrics = collect_detector_metrics(self.db_path)

        observations = []
        detector_rules = {r.id: r for r in self.rules.values() if r.target_type == 'detector'}

        for m in metrics:
            detector_id = m.get('detector_rule_id', 'unknown')

            for rule in detector_rules.values():
                if self._evaluate_rule(rule, m):
                    confidence = self._calculate_confidence(rule, m)
                    insight = self._format_insight(rule, m, detector_id)

                    observations.append(MetaObservation(
                        id=generate_id("meta"),
                        timestamp=get_timestamp(),
                        observation_type='detector_issue',
                        subject_type='detector_rule',
                        subject_id=detector_id,
                        rule_id=rule.id,
                        metrics=m,
                        insight=insight,
                        confidence=confidence,
                        recommended_action=rule.recommended_action
                    ))

        return observations

    def analyze_template_metrics(self, metrics: List[Dict[str, Any]] = None) -> List[MetaObservation]:
        """Analyze template performance metrics."""
        if metrics is None:
            metrics = collect_template_metrics(self.db_path)

        observations = []
        template_rules = {r.id: r for r in self.rules.values() if r.target_type == 'template'}

        for m in metrics:
            template_id = m.get('template_id', 'unknown')

            for rule in template_rules.values():
                if self._evaluate_rule(rule, m):
                    confidence = self._calculate_confidence(rule, m)
                    insight = self._format_insight(rule, m, template_id)

                    observations.append(MetaObservation(
                        id=generate_id("meta"),
                        timestamp=get_timestamp(),
                        observation_type='template_issue',
                        subject_type='synthesis_template',
                        subject_id=template_id,
                        rule_id=rule.id,
                        metrics=m,
                        insight=insight,
                        confidence=confidence,
                        recommended_action=rule.recommended_action
                    ))

        return observations

    def analyze_unused_capabilities(self, metrics: List[Dict[str, Any]] = None) -> List[MetaObservation]:
        """Detect capabilities with zero usage after threshold days."""
        if metrics is None:
            metrics = collect_capability_usage_metrics(self.db_path)

        observations = []
        capability_rules = {r.id: r for r in self.rules.values() if r.target_type == 'capability'}

        for m in metrics:
            cap_id = m.get('capability_id', 'unknown')
            cap_name = m.get('name', cap_id)

            for rule in capability_rules.values():
                if self._evaluate_rule(rule, m):
                    confidence = self._calculate_confidence(rule, m)
                    insight = self._format_insight(rule, m, cap_name)

                    observations.append(MetaObservation(
                        id=generate_id("meta"),
                        timestamp=get_timestamp(),
                        observation_type='unused_capability',
                        subject_type='capability',
                        subject_id=cap_id,
                        rule_id=rule.id,
                        metrics=m,
                        insight=insight,
                        confidence=confidence,
                        recommended_action=rule.recommended_action
                    ))

        return observations

    def analyze_rejection_patterns(self) -> List[MetaObservation]:
        """Analyze patterns in rejection reasons."""
        rejections = get_recent_rejections(db_path=self.db_path)

        if len(rejections) < 3:
            return []

        observations = []

        # Group by common patterns
        reason_counts: Dict[str, int] = {}
        pattern_details: Dict[str, List[Dict]] = {}

        for r in rejections:
            reason = (r.get('rejection_reason') or '').lower()

            # Normalize common patterns
            if 'not needed' in reason or 'unnecessary' in reason:
                key = 'not_needed'
            elif 'wrong' in reason or 'incorrect' in reason:
                key = 'incorrect'
            elif 'duplicate' in reason or 'already' in reason:
                key = 'duplicate'
            elif 'too complex' in reason or 'overengineered' in reason:
                key = 'too_complex'
            else:
                key = 'other'

            reason_counts[key] = reason_counts.get(key, 0) + 1
            if key not in pattern_details:
                pattern_details[key] = []
            pattern_details[key].append(r)

        total = len(rejections)
        for pattern, count in reason_counts.items():
            rate = count / total
            if count >= 2 and rate >= 0.3:
                # Get most common detector/template for this pattern
                details = pattern_details[pattern]

                observations.append(MetaObservation(
                    id=generate_id("meta"),
                    timestamp=get_timestamp(),
                    observation_type='pattern',
                    subject_type='workflow',
                    subject_id='rejection_analysis',
                    rule_id='builtin:rejection_pattern',
                    metrics={
                        'pattern': pattern,
                        'count': count,
                        'total_rejections': total,
                        'rate': rate
                    },
                    insight=f"Common rejection pattern: {pattern} ({count}/{total} = {rate:.0%})",
                    confidence=min(0.8, rate + 0.2),
                    recommended_action=f"Review proposals to reduce '{pattern}' rejections"
                ))

        return observations

    def run_analysis(self) -> List[MetaObservation]:
        """Run all meta-detection analyses."""
        observations = []

        observations.extend(self.analyze_detector_metrics())
        observations.extend(self.analyze_template_metrics())
        observations.extend(self.analyze_unused_capabilities())
        observations.extend(self.analyze_rejection_patterns())

        return observations


def run_meta_detection(db_path=None) -> List[MetaObservation]:
    """Run meta-detection and return observations."""
    engine = MetaDetectorEngine(db_path)
    return engine.run_analysis()


if __name__ == "__main__":
    print("Running meta-detection analysis...")
    print(f"Rules directory: {HOMUNCULUS_ROOT / 'meta' / 'meta-rules'}")

    engine = MetaDetectorEngine()
    print(f"Loaded {len(engine.rules)} meta-rules")

    observations = engine.run_analysis()

    if not observations:
        print("\nNo issues detected.")
    else:
        print(f"\nDetected {len(observations)} issue(s):")
        for obs in observations:
            print(f"\n  [{obs.observation_type}] {obs.subject_id}")
            print(f"    Rule: {obs.rule_id}")
            print(f"    Insight: {obs.insight}")
            print(f"    Confidence: {obs.confidence:.0%}")
            if obs.recommended_action:
                print(f"    Action: {obs.recommended_action}")
