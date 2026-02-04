#!/usr/bin/env python3
"""
Meta-Synthesizer for Homunculus Layer 2.
Generates, saves, and applies meta-proposals based on meta-observations.
"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Any, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    HOMUNCULUS_ROOT, generate_id, get_timestamp,
    get_db_connection, db_execute, load_yaml_file, save_yaml_file
)
from meta_detectors import MetaObservation, MetaDetectorEngine


@dataclass
class MetaProposal:
    """A proposed improvement to the system based on meta-observation."""
    id: str
    observation_id: str
    proposal_type: str  # 'detector_patch', 'template_patch', 'deprecate', 'config_change'
    target_id: str
    target_type: str  # 'detector_rule', 'synthesis_template', 'capability', 'config'
    target_version: int
    changes: Dict[str, Any]
    reasoning: str
    confidence: float
    diff_preview: Optional[str] = None


class MetaSynthesizer:
    """Engine for generating meta-proposals from meta-observations."""

    def __init__(self, db_path=None):
        self.db_path = db_path

    def generate_proposal(self, observation: MetaObservation) -> Optional[MetaProposal]:
        """Generate a meta-proposal from an observation."""
        if observation.confidence < 0.5:
            return None

        proposal_type = self._determine_proposal_type(observation)
        if not proposal_type:
            return None

        changes = self._generate_changes(observation, proposal_type)
        if not changes:
            return None

        diff_preview = self._generate_diff_preview(observation, changes)

        return MetaProposal(
            id=generate_id("mprop"),
            observation_id=observation.id,
            proposal_type=proposal_type,
            target_id=observation.subject_id,
            target_type=observation.subject_type,
            target_version=1,  # Will be updated when we read actual version
            changes=changes,
            reasoning=observation.insight,
            confidence=observation.confidence * 0.8,  # Slightly lower than observation
            diff_preview=diff_preview
        )

    def _determine_proposal_type(self, observation: MetaObservation) -> Optional[str]:
        """Determine the proposal type based on observation."""
        obs_type = observation.observation_type
        metrics = observation.metrics

        if obs_type == 'detector_issue':
            if metrics.get('dismissal_rate', 0) > 0.5:
                return 'detector_patch'
            if metrics.get('approval_rate', 1) < 0.3:
                return 'detector_patch'

        elif obs_type == 'template_issue':
            if metrics.get('rollback_rate', 0) > 0.3:
                return 'template_patch'
            if metrics.get('approval_rate', 1) < 0.4:
                return 'template_patch'

        elif obs_type == 'unused_capability':
            if metrics.get('usage_count', 0) == 0 and metrics.get('days_installed', 0) >= 14:
                return 'deprecate'

        elif obs_type == 'pattern':
            return 'config_change'

        return None

    def _generate_changes(self, observation: MetaObservation, proposal_type: str) -> Dict[str, Any]:
        """Generate the specific changes to apply."""
        changes = {}
        metrics = observation.metrics

        if proposal_type == 'detector_patch':
            dismissal_rate = metrics.get('dismissal_rate', 0)
            approval_rate = metrics.get('approval_rate', 1)

            if dismissal_rate > 0.5:
                # Increase min_confidence threshold
                current_threshold = 0.3  # Default
                new_threshold = min(0.7, current_threshold + 0.2)
                changes['min_confidence'] = new_threshold
                changes['recommendation'] = 'Increase confidence threshold to reduce false positives'

            elif approval_rate < 0.3:
                changes['recommendation'] = 'Review detector criteria - low approval rate'
                changes['action'] = 'manual_review_needed'

        elif proposal_type == 'template_patch':
            rollback_rate = metrics.get('rollback_rate', 0)
            approval_rate = metrics.get('approval_rate', 1)

            if rollback_rate > 0.3:
                changes['recommendation'] = 'Review template output quality - high rollback rate'
                changes['action'] = 'manual_review_needed'

            elif approval_rate < 0.4:
                changes['recommendation'] = 'Improve template structure or synthesis prompt'
                changes['action'] = 'manual_review_needed'

        elif proposal_type == 'deprecate':
            changes['new_status'] = 'deprecated'
            changes['reason'] = f"No usage detected after {metrics.get('days_installed', 14)} days"

        elif proposal_type == 'config_change':
            pattern = metrics.get('pattern', 'unknown')
            changes['recommendation'] = f"Address '{pattern}' rejection pattern"
            changes['action'] = 'review_synthesis_settings'

        return changes

    def _generate_diff_preview(self, observation: MetaObservation, changes: Dict[str, Any]) -> Optional[str]:
        """Generate a preview of what would change."""
        lines = ["--- Proposed Changes ---"]

        target = observation.subject_id
        lines.append(f"Target: {target}")
        lines.append(f"Type: {observation.subject_type}")
        lines.append("")

        for key, value in changes.items():
            if key == 'recommendation':
                lines.append(f"Recommendation: {value}")
            elif key == 'action':
                lines.append(f"Action: {value}")
            elif key == 'new_status':
                lines.append(f"Status: current -> {value}")
            else:
                lines.append(f"Change {key}: -> {value}")

        return "\n".join(lines)

    def save_proposal(self, proposal: MetaProposal) -> bool:
        """Save a meta-proposal to the database."""
        try:
            with get_db_connection(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO meta_proposals (
                        id, created_at, meta_observation_id, proposal_type,
                        target_id, target_version, proposed_changes_json,
                        reasoning, confidence, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """, (
                    proposal.id,
                    get_timestamp(),
                    proposal.observation_id,
                    proposal.proposal_type,
                    proposal.target_id,
                    proposal.target_version,
                    json.dumps(proposal.changes),
                    proposal.reasoning,
                    proposal.confidence
                ))
                conn.commit()
            return True
        except Exception as e:
            print(f"Error saving meta-proposal: {e}")
            return False

    def apply_proposal(self, proposal_id: str) -> Dict[str, Any]:
        """
        Apply an approved meta-proposal.

        Returns dict with:
        - success: bool
        - message: str
        - changes_applied: list of changes made
        """
        # Get proposal
        proposals = db_execute(
            "SELECT * FROM meta_proposals WHERE id = ? OR id LIKE ?",
            (proposal_id, f"{proposal_id}%"),
            db_path=self.db_path
        ) if self.db_path else db_execute(
            "SELECT * FROM meta_proposals WHERE id = ? OR id LIKE ?",
            (proposal_id, f"{proposal_id}%")
        )

        if not proposals:
            return {'success': False, 'message': 'Proposal not found', 'changes_applied': []}

        proposal = proposals[0]

        if proposal['status'] != 'pending':
            return {'success': False, 'message': f"Proposal status is {proposal['status']}", 'changes_applied': []}

        try:
            changes = json.loads(proposal.get('proposed_changes_json', '{}'))
        except json.JSONDecodeError:
            changes = {}

        changes_applied = []
        proposal_type = proposal['proposal_type']
        target_id = proposal['target_id']

        # Apply based on proposal type
        if proposal_type == 'detector_patch':
            result = self._apply_detector_patch(target_id, changes)
            changes_applied = result.get('changes', [])

        elif proposal_type == 'template_patch':
            result = self._apply_template_patch(target_id, changes)
            changes_applied = result.get('changes', [])

        elif proposal_type == 'deprecate':
            result = self._apply_deprecation(target_id, changes)
            changes_applied = result.get('changes', [])

        elif proposal_type == 'config_change':
            # Config changes are informational - mark as applied
            changes_applied = ['Marked for manual review']

        # Update proposal status
        timestamp = get_timestamp()
        try:
            with get_db_connection(self.db_path) as conn:
                conn.execute(
                    "UPDATE meta_proposals SET status = 'applied', applied_at = ? WHERE id = ?",
                    (timestamp, proposal['id'])
                )
                conn.commit()
        except Exception as e:
            return {'success': False, 'message': f"Failed to update status: {e}", 'changes_applied': changes_applied}

        return {
            'success': True,
            'message': f"Applied {proposal_type} to {target_id}",
            'changes_applied': changes_applied
        }

    def _apply_detector_patch(self, detector_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Apply changes to a detector rule YAML."""
        detectors_dir = HOMUNCULUS_ROOT / "meta" / "detector-rules"
        result = {'changes': []}

        # Find the detector file
        for yaml_file in detectors_dir.glob("*.yaml"):
            data = load_yaml_file(yaml_file)
            if data.get('id') == detector_id:
                # Apply changes
                if 'min_confidence' in changes:
                    old_val = data.get('min_confidence', 0.3)
                    data['min_confidence'] = changes['min_confidence']
                    result['changes'].append(f"min_confidence: {old_val} -> {changes['min_confidence']}")

                # Bump version
                data['version'] = data.get('version', 1) + 1

                # Save
                save_yaml_file(yaml_file, data)
                result['changes'].append(f"version: {data['version']}")
                break

        return result

    def _apply_template_patch(self, template_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Apply changes to a synthesis template YAML."""
        templates_dir = HOMUNCULUS_ROOT / "meta" / "synthesis-templates"
        result = {'changes': []}

        for yaml_file in templates_dir.glob("*.yaml"):
            data = load_yaml_file(yaml_file)
            if data.get('id') == template_id:
                # Most template patches are informational
                # Bump version to track the review
                data['version'] = data.get('version', 1) + 1
                data['last_reviewed'] = get_timestamp()

                save_yaml_file(yaml_file, data)
                result['changes'].append(f"version: {data['version']}")
                result['changes'].append(f"last_reviewed: {data['last_reviewed']}")
                break

        return result

    def _apply_deprecation(self, capability_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Deprecate a capability."""
        result = {'changes': []}

        try:
            with get_db_connection(self.db_path) as conn:
                conn.execute(
                    "UPDATE capabilities SET status = 'deprecated' WHERE id = ? OR name = ?",
                    (capability_id, capability_id)
                )
                conn.commit()
            result['changes'].append(f"status: active -> deprecated")
        except Exception as e:
            print(f"Error deprecating capability: {e}")

        return result

    def reject_proposal(self, proposal_id: str, reason: str = "") -> bool:
        """Reject a meta-proposal."""
        try:
            with get_db_connection(self.db_path) as conn:
                conn.execute(
                    "UPDATE meta_proposals SET status = 'rejected', rejection_reason = ? WHERE id = ? OR id LIKE ?",
                    (reason, proposal_id, f"{proposal_id}%")
                )
                conn.commit()
            return True
        except Exception:
            return False


def get_pending_meta_proposals(db_path=None) -> List[Dict[str, Any]]:
    """Get all pending meta-proposals."""
    query = "SELECT * FROM meta_proposals WHERE status = 'pending' ORDER BY created_at DESC"
    return db_execute(query, db_path=db_path) if db_path else db_execute(query)


def get_meta_proposal(proposal_id: str, db_path=None) -> Optional[Dict[str, Any]]:
    """Get a specific meta-proposal."""
    proposals = db_execute(
        "SELECT * FROM meta_proposals WHERE id = ? OR id LIKE ?",
        (proposal_id, f"{proposal_id}%"),
        db_path=db_path
    ) if db_path else db_execute(
        "SELECT * FROM meta_proposals WHERE id = ? OR id LIKE ?",
        (proposal_id, f"{proposal_id}%")
    )
    return proposals[0] if proposals else None


def run_meta_synthesis(observations: List[MetaObservation] = None, db_path=None) -> Dict[str, Any]:
    """
    Run meta-synthesis on observations.

    If no observations provided, runs meta-detection first.
    """
    result = {
        'observations_analyzed': 0,
        'proposals_generated': 0,
        'proposals': []
    }

    if observations is None:
        engine = MetaDetectorEngine(db_path)
        observations = engine.run_analysis()

    result['observations_analyzed'] = len(observations)

    synthesizer = MetaSynthesizer(db_path)
    for obs in observations:
        proposal = synthesizer.generate_proposal(obs)
        if proposal:
            if synthesizer.save_proposal(proposal):
                result['proposals_generated'] += 1
                result['proposals'].append({
                    'id': proposal.id,
                    'type': proposal.proposal_type,
                    'target': proposal.target_id,
                    'confidence': proposal.confidence
                })

    return result


if __name__ == "__main__":
    print("Running meta-synthesis...")

    result = run_meta_synthesis()

    print(f"\nAnalyzed {result['observations_analyzed']} observations")
    print(f"Generated {result['proposals_generated']} proposals")

    if result['proposals']:
        print("\nProposals:")
        for p in result['proposals']:
            print(f"  [{p['type']}] {p['target']} (conf: {p['confidence']:.0%})")
