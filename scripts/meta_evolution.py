#!/usr/bin/env python3
"""
Meta-Evolution System for Homunculus (Layer 2).
Observes and improves the gap detection and synthesis systems.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import sys
sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    HOMUNCULUS_ROOT, generate_id, get_timestamp,
    get_db_connection, db_execute, load_config
)


@dataclass
class MetaObservation:
    """An observation about system performance."""
    id: str
    timestamp: str
    observation_type: str  # 'detector_performance', 'template_performance', 'pattern', 'anomaly'
    subject_type: str  # 'detector_rule', 'synthesis_template', 'gap_type', 'workflow'
    subject_id: str
    metrics: Dict[str, Any]
    insight: str
    confidence: float


@dataclass
class MetaProposal:
    """A proposed improvement to the system."""
    id: str
    observation_id: str
    proposal_type: str  # 'detector_patch', 'template_patch', 'new_gap_type', 'config_change'
    target_id: str
    target_version: int
    changes: Dict[str, Any]
    reasoning: str
    confidence: float


class MetaEvolutionEngine:
    """Engine for observing and improving the Homunculus system."""

    def __init__(self):
        self.config = load_config()
        self.meta_config = self.config.get('meta_evolution', {})
        self.enabled = self.meta_config.get('enabled', True)

    def collect_detector_metrics(self) -> List[Dict[str, Any]]:
        """Collect performance metrics for all detector rules."""
        return db_execute("""
            SELECT
                g.detector_rule_id,
                g.detector_rule_version,
                COUNT(DISTINCT g.id) as gaps_detected,
                COUNT(DISTINCT p.id) as proposals_generated,
                SUM(CASE WHEN p.status = 'installed' THEN 1 ELSE 0 END) as proposals_installed,
                SUM(CASE WHEN p.status = 'rejected' THEN 1 ELSE 0 END) as proposals_rejected,
                SUM(CASE WHEN g.status = 'dismissed' THEN 1 ELSE 0 END) as gaps_dismissed,
                SUM(CASE WHEN g.status = 'resolved' THEN 1 ELSE 0 END) as gaps_resolved,
                AVG(g.confidence) as avg_confidence,
                AVG(p.confidence) as avg_proposal_confidence
            FROM gaps g
            LEFT JOIN proposals p ON g.id = p.gap_id
            GROUP BY g.detector_rule_id, g.detector_rule_version
            HAVING COUNT(g.id) > 0
        """)

    def collect_template_metrics(self) -> List[Dict[str, Any]]:
        """Collect performance metrics for all synthesis templates."""
        return db_execute("""
            SELECT
                p.template_id,
                p.template_version,
                COUNT(DISTINCT p.id) as proposals_generated,
                SUM(CASE WHEN p.status = 'installed' THEN 1 ELSE 0 END) as installed,
                SUM(CASE WHEN p.status = 'rejected' THEN 1 ELSE 0 END) as rejected,
                SUM(CASE WHEN p.status = 'rolled_back' THEN 1 ELSE 0 END) as rolled_back,
                AVG(p.confidence) as avg_confidence,
                COUNT(DISTINCT c.id) as capabilities_active
            FROM proposals p
            LEFT JOIN capabilities c ON p.id = c.source_proposal_id AND c.status = 'active'
            GROUP BY p.template_id, p.template_version
            HAVING COUNT(p.id) > 0
        """)

    def analyze_detector_performance(self, metrics: Dict[str, Any]) -> Optional[MetaObservation]:
        """Analyze a detector's performance and generate observations."""
        detector_id = metrics['detector_rule_id']
        gaps_detected = metrics['gaps_detected'] or 0
        proposals_approved = metrics.get('proposals_installed') or metrics.get('proposals_approved') or 0
        proposals_rejected = metrics.get('proposals_rejected') or 0
        gaps_dismissed = metrics['gaps_dismissed'] or 0

        # Calculate rates
        total_outcomes = proposals_approved + proposals_rejected + gaps_dismissed
        if total_outcomes == 0:
            return None

        approval_rate = proposals_approved / total_outcomes if total_outcomes > 0 else 0
        dismissal_rate = gaps_dismissed / gaps_detected if gaps_detected > 0 else 0

        # Generate insights
        insight = None
        confidence = 0.0

        # High dismissal rate suggests detector is too aggressive
        if dismissal_rate > 0.5 and gaps_detected >= 3:
            insight = f"High dismissal rate ({dismissal_rate:.0%}): detector may be generating false positives"
            confidence = min(0.9, dismissal_rate)

        # Low approval rate suggests proposals aren't useful
        elif approval_rate < 0.3 and total_outcomes >= 3:
            insight = f"Low approval rate ({approval_rate:.0%}): detected gaps may not be actionable"
            confidence = min(0.8, 1 - approval_rate)

        # High approval rate is good - record it
        elif approval_rate > 0.7 and total_outcomes >= 3:
            insight = f"High approval rate ({approval_rate:.0%}): detector is working well"
            confidence = approval_rate * 0.8

        if not insight:
            return None

        return MetaObservation(
            id=generate_id("meta"),
            timestamp=get_timestamp(),
            observation_type='detector_performance',
            subject_type='detector_rule',
            subject_id=detector_id,
            metrics={
                'gaps_detected': gaps_detected,
                'proposals_approved': proposals_approved,
                'proposals_rejected': proposals_rejected,
                'gaps_dismissed': gaps_dismissed,
                'approval_rate': approval_rate,
                'dismissal_rate': dismissal_rate
            },
            insight=insight,
            confidence=confidence
        )

    def analyze_template_performance(self, metrics: Dict[str, Any]) -> Optional[MetaObservation]:
        """Analyze a template's performance and generate observations."""
        template_id = metrics['template_id']
        proposals_generated = metrics.get('proposals_generated') or 0
        approved = metrics.get('installed') or metrics.get('approved') or 0
        rejected = metrics.get('rejected') or 0
        rolled_back = metrics.get('rolled_back') or 0
        capabilities_active = metrics.get('capabilities_active') or 0

        total_outcomes = approved + rejected
        if total_outcomes == 0:
            return None

        approval_rate = approved / total_outcomes if total_outcomes > 0 else 0
        retention_rate = capabilities_active / approved if approved > 0 else 0
        rollback_rate = rolled_back / approved if approved > 0 else 0

        insight = None
        confidence = 0.0

        # High rollback rate suggests template output isn't working
        if rollback_rate > 0.3 and approved >= 2:
            insight = f"High rollback rate ({rollback_rate:.0%}): template output may have issues"
            confidence = min(0.85, rollback_rate)

        # Low approval rate
        elif approval_rate < 0.4 and total_outcomes >= 3:
            insight = f"Low approval rate ({approval_rate:.0%}): template may need improvement"
            confidence = min(0.8, 1 - approval_rate)

        # High approval and retention
        elif approval_rate > 0.6 and retention_rate > 0.8 and total_outcomes >= 3:
            insight = f"High approval ({approval_rate:.0%}) and retention ({retention_rate:.0%}): template is effective"
            confidence = approval_rate * retention_rate

        if not insight:
            return None

        return MetaObservation(
            id=generate_id("meta"),
            timestamp=get_timestamp(),
            observation_type='template_performance',
            subject_type='synthesis_template',
            subject_id=template_id,
            metrics={
                'proposals_generated': proposals_generated,
                'approved': approved,
                'rejected': rejected,
                'rolled_back': rolled_back,
                'capabilities_active': capabilities_active,
                'approval_rate': approval_rate,
                'retention_rate': retention_rate,
                'rollback_rate': rollback_rate
            },
            insight=insight,
            confidence=confidence
        )

    def analyze_rejection_patterns(self) -> List[MetaObservation]:
        """Analyze patterns in rejection reasons."""
        rejections = db_execute("""
            SELECT
                p.capability_type,
                p.template_id,
                p.rejection_reason,
                g.gap_type,
                g.detector_rule_id
            FROM proposals p
            JOIN gaps g ON p.gap_id = g.id
            WHERE p.status = 'rejected' AND p.rejection_reason IS NOT NULL
            ORDER BY p.reviewed_at DESC
            LIMIT 50
        """)

        if len(rejections) < 3:
            return []

        observations = []

        # Group by common rejection patterns
        reason_counts: Dict[str, int] = {}
        for r in rejections:
            reason = (r['rejection_reason'] or '').lower()
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

        total = len(rejections)
        for pattern, count in reason_counts.items():
            if count >= 2 and count / total >= 0.3:
                observations.append(MetaObservation(
                    id=generate_id("meta"),
                    timestamp=get_timestamp(),
                    observation_type='pattern',
                    subject_type='workflow',
                    subject_id='rejection_analysis',
                    metrics={
                        'pattern': pattern,
                        'count': count,
                        'total_rejections': total,
                        'rate': count / total
                    },
                    insight=f"Common rejection pattern: {pattern} ({count}/{total} = {count/total:.0%})",
                    confidence=min(0.8, count / total + 0.2)
                ))

        return observations

    def run_analysis(self) -> List[MetaObservation]:
        """Run full meta-analysis and return observations."""
        if not self.enabled:
            return []

        observations = []

        # Analyze detectors
        for metrics in self.collect_detector_metrics():
            obs = self.analyze_detector_performance(metrics)
            if obs:
                observations.append(obs)

        # Analyze templates
        for metrics in self.collect_template_metrics():
            obs = self.analyze_template_performance(metrics)
            if obs:
                observations.append(obs)

        # Analyze patterns
        observations.extend(self.analyze_rejection_patterns())

        # Save observations to database
        for obs in observations:
            self.save_observation(obs)

        return observations

    def save_observation(self, obs: MetaObservation) -> bool:
        """Save a meta-observation to the database."""
        try:
            with get_db_connection() as conn:
                conn.execute("""
                    INSERT INTO meta_observations (
                        id, timestamp, observation_type, subject_type, subject_id,
                        metrics_json, insight, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    obs.id, obs.timestamp, obs.observation_type,
                    obs.subject_type, obs.subject_id,
                    json.dumps(obs.metrics), obs.insight, obs.confidence
                ))
                conn.commit()
            return True
        except Exception as e:
            print(f"Error saving meta-observation: {e}")
            return False

    def generate_proposals(self, observations: List[MetaObservation]) -> List[MetaProposal]:
        """Generate improvement proposals from observations."""
        proposals = []

        for obs in observations:
            if obs.confidence < 0.5:
                continue

            if obs.observation_type == 'detector_performance':
                if 'false positives' in obs.insight.lower():
                    proposals.append(MetaProposal(
                        id=generate_id("mprop"),
                        observation_id=obs.id,
                        proposal_type='detector_patch',
                        target_id=obs.subject_id,
                        target_version=1,
                        changes={
                            'recommendation': 'Increase confidence threshold',
                            'suggested_min_confidence': 0.5
                        },
                        reasoning=obs.insight,
                        confidence=obs.confidence * 0.8
                    ))

            elif obs.observation_type == 'template_performance':
                if 'rollback' in obs.insight.lower():
                    proposals.append(MetaProposal(
                        id=generate_id("mprop"),
                        observation_id=obs.id,
                        proposal_type='template_patch',
                        target_id=obs.subject_id,
                        target_version=1,
                        changes={
                            'recommendation': 'Review template output quality',
                            'action': 'manual_review_needed'
                        },
                        reasoning=obs.insight,
                        confidence=obs.confidence * 0.7
                    ))

        # Save proposals
        for prop in proposals:
            self.save_proposal(prop)

        return proposals

    def save_proposal(self, prop: MetaProposal) -> bool:
        """Save a meta-proposal to the database."""
        try:
            with get_db_connection() as conn:
                conn.execute("""
                    INSERT INTO meta_proposals (
                        id, created_at, meta_observation_id, proposal_type,
                        target_id, target_version, proposed_changes_json,
                        reasoning, confidence, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """, (
                    prop.id, get_timestamp(), prop.observation_id,
                    prop.proposal_type, prop.target_id, prop.target_version,
                    json.dumps(prop.changes), prop.reasoning, prop.confidence
                ))
                conn.commit()
            return True
        except Exception as e:
            print(f"Error saving meta-proposal: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get meta-evolution system status."""
        status = {
            'enabled': self.enabled,
            'observations': {'total': 0, 'by_type': {}},
            'proposals': {'total': 0, 'pending': 0, 'applied': 0},
            'detector_health': [],
            'template_health': []
        }

        # Count observations
        obs_counts = db_execute("""
            SELECT observation_type, COUNT(*) as count
            FROM meta_observations
            GROUP BY observation_type
        """)
        for row in obs_counts:
            status['observations']['by_type'][row['observation_type']] = row['count']
            status['observations']['total'] += row['count']

        # Count proposals
        prop_counts = db_execute("""
            SELECT status, COUNT(*) as count
            FROM meta_proposals
            GROUP BY status
        """)
        for row in prop_counts:
            status['proposals']['total'] += row['count']
            if row['status'] == 'pending':
                status['proposals']['pending'] = row['count']
            elif row['status'] == 'applied':
                status['proposals']['applied'] = row['count']

        # Get detector health summary
        detector_metrics = self.collect_detector_metrics()
        for m in detector_metrics[:5]:  # Top 5
            installed = m.get('proposals_installed') or m.get('proposals_approved') or 0
            rejected = m.get('proposals_rejected') or 0
            dismissed = m.get('gaps_dismissed') or 0
            total = installed + rejected + dismissed
            if total > 0:
                rate = installed / total
                status['detector_health'].append({
                    'id': m['detector_rule_id'],
                    'gaps': m['gaps_detected'],
                    'approval_rate': f"{rate:.0%}"
                })

        # Get template health summary
        template_metrics = self.collect_template_metrics()
        for m in template_metrics[:5]:  # Top 5
            installed = m.get('installed') or m.get('approved') or 0
            rejected = m.get('rejected') or 0
            total = installed + rejected
            if total > 0:
                rate = installed / total
                status['template_health'].append({
                    'id': m['template_id'],
                    'proposals': m['proposals_generated'],
                    'approval_rate': f"{rate:.0%}"
                })

        return status


def run_meta_evolution() -> Dict[str, Any]:
    """Run the meta-evolution cycle."""
    engine = MetaEvolutionEngine()

    if not engine.enabled:
        return {'enabled': False, 'observations': 0, 'proposals': 0}

    observations = engine.run_analysis()
    proposals = engine.generate_proposals(observations)

    return {
        'enabled': True,
        'observations': len(observations),
        'proposals': len(proposals),
        'observation_details': [
            {'type': o.observation_type, 'insight': o.insight, 'confidence': o.confidence}
            for o in observations
        ],
        'proposal_details': [
            {'type': p.proposal_type, 'target': p.target_id, 'confidence': p.confidence}
            for p in proposals
        ]
    }


if __name__ == "__main__":
    print("Running meta-evolution analysis...")
    result = run_meta_evolution()
    print(f"\nResults:")
    print(f"  Enabled: {result['enabled']}")
    print(f"  Observations: {result['observations']}")
    print(f"  Proposals: {result['proposals']}")

    if result.get('observation_details'):
        print("\nObservations:")
        for obs in result['observation_details']:
            print(f"  - [{obs['type']}] {obs['insight'][:60]}... (conf: {obs['confidence']:.2f})")

    if result.get('proposal_details'):
        print("\nProposals:")
        for prop in result['proposal_details']:
            print(f"  - [{prop['type']}] Target: {prop['target']} (conf: {prop['confidence']:.2f})")
