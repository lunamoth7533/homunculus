#!/usr/bin/env python3
"""
Gap detection engine for Homunculus.
"""

import re
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

import sys
sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    HOMUNCULUS_ROOT, DB_PATH, generate_id, get_timestamp, db_execute,
    read_jsonl, load_yaml_file, get_db_connection
)
from typing import Union
from gap_types import get_gap_info, get_default_scope, get_all_gap_types


@dataclass
class DetectorRule:
    """A gap detection rule."""
    id: str
    version: int
    gap_type: str
    priority: str
    enabled: bool
    triggers: List[Dict[str, Any]]
    min_confidence: float = 0.3
    scope_inference: List[Dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, data: Dict[str, Any]) -> 'DetectorRule':
        return cls(
            id=data.get('id', ''),
            version=data.get('version', 1),
            gap_type=data.get('gap_type', ''),
            priority=data.get('priority', 'medium'),
            enabled=data.get('enabled', True),
            triggers=data.get('triggers', []),
            min_confidence=data.get('min_confidence', 0.3),
            scope_inference=data.get('scope_inference', [])
        )


@dataclass
class DetectedGap:
    """A detected capability gap."""
    id: str
    gap_type: str
    domain: Optional[str]
    confidence: float
    recommended_scope: str
    desired_capability: str
    evidence_summary: str
    detector_rule_id: str
    detector_rule_version: int
    observation_ids: List[str]
    project_path: Optional[str] = None
    example_invocation: Optional[str] = None


class GapDetector:
    """Main gap detection engine."""

    def __init__(self, db_path: Union[str, Path] = None):
        self.rules: Dict[str, DetectorRule] = {}
        self.rules_dir = HOMUNCULUS_ROOT / "meta" / "detector-rules"
        self.db_path = db_path if db_path is not None else DB_PATH
        self._load_rules()

    def _load_rules(self):
        """Load all detector rules from YAML files."""
        if not self.rules_dir.exists():
            return

        for rule_file in self.rules_dir.glob("*.yaml"):
            try:
                data = load_yaml_file(rule_file)
                if data and data.get('id'):
                    rule = DetectorRule.from_yaml(data)
                    if rule.enabled:
                        self.rules[rule.id] = rule
            except Exception as e:
                print(f"Warning: Failed to load rule {rule_file}: {e}")

    def detect_from_observations(self, observations: List[Dict]) -> List[DetectedGap]:
        """Detect gaps from a list of observations."""
        gaps = []

        for rule in self.rules.values():
            rule_gaps = self._apply_rule(rule, observations)
            gaps.extend(rule_gaps)

        # Deduplicate similar gaps
        gaps = self._deduplicate_gaps(gaps)

        return gaps

    def _apply_rule(self, rule: DetectorRule, observations: List[Dict]) -> List[DetectedGap]:
        """Apply a detection rule to observations."""
        gaps = []

        for trigger in rule.triggers:
            condition = trigger.get('condition', '')
            confidence_boost = trigger.get('confidence_boost', 0.2)

            matching_obs = []
            for obs in observations:
                if self._check_condition(condition, obs):
                    matching_obs.append(obs)

            if matching_obs:
                # Calculate confidence based on number of matches
                base_confidence = min(0.3 + (len(matching_obs) * confidence_boost), 0.95)

                if base_confidence >= rule.min_confidence:
                    # Extract desired capability
                    extract_rules = trigger.get('extract', {})
                    desired_cap = self._extract_capability(extract_rules, matching_obs)

                    if desired_cap:
                        gap = DetectedGap(
                            id=generate_id("gap"),
                            gap_type=rule.gap_type,
                            domain=self._infer_domain(matching_obs),
                            confidence=base_confidence,
                            recommended_scope=self._infer_scope(rule, matching_obs),
                            desired_capability=desired_cap,
                            evidence_summary=self._build_evidence_summary(matching_obs),
                            detector_rule_id=rule.id,
                            detector_rule_version=rule.version,
                            observation_ids=[obs.get('id', '') for obs in matching_obs],
                            project_path=matching_obs[0].get('project_path') if matching_obs else None
                        )
                        gaps.append(gap)

        return gaps

    def _check_condition(self, condition: str, obs: Dict) -> bool:
        """Check if an observation matches a condition."""
        if not condition:
            return False

        try:
            # Handle "contains" conditions
            if ' contains ' in condition:
                parts = condition.split(' contains ', 1)
                field_path = parts[0].strip()
                search_text = parts[1].strip().strip('"\'')
                value = self._get_nested_value(obs, field_path)
                if value:
                    return search_text.lower() in str(value).lower()
                return False

            # Handle "==" conditions
            if ' == ' in condition:
                parts = condition.split(' == ', 1)
                field_path = parts[0].strip()
                expected = parts[1].strip()
                value = self._get_nested_value(obs, field_path)

                # Handle boolean
                if expected.lower() == 'true':
                    return bool(value)
                elif expected.lower() == 'false':
                    return not bool(value)
                elif expected.isdigit():
                    return value == int(expected)

                return str(value) == expected

            # Handle ">" conditions (for numeric comparisons)
            if ' > ' in condition:
                parts = condition.split(' > ', 1)
                field_path = parts[0].strip()
                threshold = float(parts[1].strip())
                value = self._get_nested_value(obs, field_path)
                if value is not None:
                    try:
                        return float(value) > threshold
                    except (ValueError, TypeError):
                        return False
                return False

            # Handle "matches" conditions (regex)
            if ' matches ' in condition:
                parts = condition.split(' matches ', 1)
                field_path = parts[0].strip()
                pattern = parts[1].strip().strip('"\'')
                value = self._get_nested_value(obs, field_path)
                if value:
                    return bool(re.search(pattern, str(value), re.IGNORECASE))
                return False

            # Handle presence check (field exists and not empty)
            field_path = condition.replace('observation.', '')
            value = self._get_nested_value(obs, field_path)
            return value is not None and value != '' and value != 0

        except Exception:
            pass

        return False

    def _get_nested_value(self, obj: Dict, path: str) -> Any:
        """Get a nested value from a dict using dot notation."""
        path = path.replace('observation.', '')
        parts = path.split('.')
        current = obj
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _extract_capability(self, extract_rules: Dict, observations: List[Dict]) -> str:
        """Extract desired capability description from observations."""
        cap_rule = extract_rules.get('desired_capability', '')

        if not cap_rule:
            # Default: use tool error or failure message
            for obs in observations:
                error = obs.get('tool_error') or obs.get('failure_missing_capability')
                if error:
                    return str(error)[:200]

            # Fallback: describe based on tool names
            tools = set(obs.get('tool_name', '') for obs in observations if obs.get('tool_name'))
            if tools:
                return f"Issue with tools: {', '.join(tools)}"

            return "Detected capability gap"

        # Handle regex extraction
        if cap_rule.startswith('regex:'):
            pattern = cap_rule[6:].strip()
            for obs in observations:
                raw = obs.get('raw_json', '') or json.dumps(obs)
                match = re.search(pattern, raw, re.IGNORECASE)
                if match:
                    return match.group(1) if match.groups() else match.group(0)

        # Handle field reference
        if cap_rule.startswith('field:'):
            field = cap_rule[6:].strip()
            for obs in observations:
                value = self._get_nested_value(obs, field)
                if value:
                    return str(value)[:200]

        return cap_rule

    def _infer_domain(self, observations: List[Dict]) -> Optional[str]:
        """Infer the domain from observations."""
        domains = {
            'pdf': ['pdf', 'document', 'acrobat'],
            'git': ['git', 'commit', 'branch', 'merge', 'push', 'pull'],
            'testing': ['test', 'spec', 'jest', 'pytest', 'mocha', 'unittest'],
            'api': ['api', 'endpoint', 'request', 'response', 'http', 'rest'],
            'database': ['sql', 'database', 'query', 'migration', 'postgres', 'mysql', 'sqlite'],
            'frontend': ['react', 'component', 'css', 'html', 'vue', 'angular'],
            'docker': ['docker', 'container', 'kubernetes', 'k8s'],
            'ci_cd': ['ci', 'cd', 'pipeline', 'github actions', 'jenkins'],
            'security': ['auth', 'security', 'permission', 'token', 'jwt', 'oauth'],
            'file': ['file', 'read', 'write', 'directory', 'path'],
        }

        all_text = ' '.join(
            str(obs.get('raw_json', '')) + ' ' + str(obs.get('tool_name', ''))
            for obs in observations
        ).lower()

        for domain, keywords in domains.items():
            if any(kw in all_text for kw in keywords):
                return domain

        return None

    def _infer_scope(self, rule: DetectorRule, observations: List[Dict]) -> str:
        """Infer the recommended scope for a gap."""
        # Check scope inference rules from the detector
        for scope_rule in rule.scope_inference:
            condition = scope_rule.get('if', '')
            scope = scope_rule.get('then', '')

            if condition == 'default':
                return scope

            # Check if condition matches
            all_text = ' '.join(str(obs) for obs in observations).lower()
            if condition.lower() in all_text:
                return scope

        # Default based on gap type
        return get_default_scope(rule.gap_type)

    def _build_evidence_summary(self, observations: List[Dict]) -> str:
        """Build a summary of evidence for a gap."""
        summaries = []
        for obs in observations[:5]:  # Limit to 5
            event = obs.get('event_type', 'unknown')
            tool = obs.get('tool_name', '')
            error = obs.get('tool_error', '')
            timestamp = obs.get('timestamp', '')[:10]

            if error:
                summaries.append(f"[{timestamp}] {tool}: {error[:50]}")
            elif tool:
                summaries.append(f"[{timestamp}] {event}: {tool}")
            else:
                summaries.append(f"[{timestamp}] {event}")

        return "; ".join(summaries) if summaries else "No specific evidence"

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison - removes noise, lowercases, strips punctuation."""
        if not text:
            return ""
        # Lowercase and strip
        t = text.lower().strip()
        # Remove all punctuation and special characters (keep only alphanumeric and spaces)
        t = re.sub(r'[^a-z0-9\s]', ' ', t)
        # Remove timestamps like 2024-01-01 or similar numeric patterns
        t = re.sub(r'\b\d{4}[-/]\d{2}[-/]\d{2}\b', '', t)
        # Collapse whitespace
        t = re.sub(r'\s+', ' ', t).strip()
        return t

    def _compute_fingerprint(self, gap_type: str, desired_capability: str) -> str:
        """Compute a fingerprint for exact-match deduplication."""
        normalized = self._normalize_text(desired_capability)
        # Extract key words (alphabetically sorted for consistency)
        words = sorted(set(w for w in normalized.split() if len(w) > 2))
        key_text = f"{gap_type}:{' '.join(words[:10])}"  # Use first 10 sorted words
        return hashlib.md5(key_text.encode()).hexdigest()[:12]

    def _deduplicate_gaps(self, gaps: List[DetectedGap]) -> List[DetectedGap]:
        """Remove duplicate or very similar gaps using fingerprinting."""
        unique = {}
        for gap in gaps:
            # Use fingerprint for more robust deduplication
            fingerprint = self._compute_fingerprint(gap.gap_type, gap.desired_capability)
            if fingerprint not in unique or gap.confidence > unique[fingerprint].confidence:
                unique[fingerprint] = gap
        return list(unique.values())

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts (0-1)."""
        if not text1 or not text2:
            return 0.0

        # Normalize texts
        t1 = text1.lower().strip()
        t2 = text2.lower().strip()

        if t1 == t2:
            return 1.0

        # Word-based similarity
        words1 = set(t1.split())
        words2 = set(t2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union)

    def _find_similar_gap(self, gap: DetectedGap, threshold: float = 0.5):
        """
        Find a similar existing gap for deduplication.
        Returns (gap_id, similarity) or (None, 0).

        Checks against all non-resolved/non-dismissed gaps to prevent duplicates.
        Uses fingerprinting for exact matches and similarity for fuzzy matches.
        """
        try:
            # Compute fingerprint for exact matching
            new_fingerprint = self._compute_fingerprint(gap.gap_type, gap.desired_capability)

            # Get all active gaps of same type (not resolved or dismissed)
            existing_gaps = db_execute(
                """SELECT id, desired_capability, domain, confidence, evidence_summary
                   FROM gaps
                   WHERE gap_type = ? AND status NOT IN ('resolved', 'dismissed')""",
                (gap.gap_type,),
                db_path=self.db_path
            )

            best_match = None
            best_similarity = 0.0

            for existing in existing_gaps:
                # Check fingerprint first (exact match)
                existing_fingerprint = self._compute_fingerprint(
                    gap.gap_type,
                    existing['desired_capability']
                )
                if new_fingerprint == existing_fingerprint:
                    return existing['id'], 1.0

                # Calculate text similarity for fuzzy matching
                sim = self._calculate_similarity(
                    self._normalize_text(gap.desired_capability),
                    self._normalize_text(existing['desired_capability'])
                )

                # Boost similarity if domains match
                if gap.domain and existing['domain'] and gap.domain == existing['domain']:
                    sim = min(1.0, sim + 0.15)

                if sim > best_similarity and sim >= threshold:
                    best_match = existing['id']
                    best_similarity = sim

            return best_match, best_similarity

        except Exception as e:
            print(f"Error finding similar gap: {e}")
            return None, 0.0

    def save_gap(self, gap: DetectedGap) -> bool:
        """Save a detected gap to the database with cross-session deduplication."""
        try:
            with get_db_connection(self.db_path) as conn:
                # Check for similar existing gap (cross-session deduplication)
                similar_id, similarity = self._find_similar_gap(gap)

                if similar_id:
                    # Merge with existing gap
                    # Update confidence (take max), append evidence
                    existing = conn.execute(
                        "SELECT evidence_summary, confidence FROM gaps WHERE id = ?",
                        (similar_id,)
                    ).fetchone()

                    new_confidence = max(gap.confidence, existing[1] if existing else 0)

                    # Combine evidence summaries
                    old_evidence = existing[0] if existing and existing[0] else ""
                    if old_evidence and gap.evidence_summary:
                        combined_evidence = f"{old_evidence}; {gap.evidence_summary}"[:500]
                    else:
                        combined_evidence = gap.evidence_summary or old_evidence

                    conn.execute(
                        """UPDATE gaps
                           SET confidence = ?, evidence_summary = ?, updated_at = ?
                           WHERE id = ?""",
                        (new_confidence, combined_evidence, get_timestamp(), similar_id)
                    )

                    # Link new observations to existing gap
                    for obs_id in gap.observation_ids:
                        if obs_id:
                            conn.execute("""
                                INSERT OR IGNORE INTO gap_observations (gap_id, observation_id)
                                VALUES (?, ?)
                            """, (similar_id, obs_id))

                    conn.commit()
                    return False  # Not a new gap (merged with existing)

                # Insert new gap
                conn.execute("""
                    INSERT INTO gaps (
                        id, detected_at, gap_type, domain, confidence,
                        recommended_scope, project_path, desired_capability,
                        evidence_summary, detector_rule_id, detector_rule_version,
                        status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """, (
                    gap.id,
                    get_timestamp(),
                    gap.gap_type,
                    gap.domain,
                    gap.confidence,
                    gap.recommended_scope,
                    gap.project_path,
                    gap.desired_capability,
                    gap.evidence_summary,
                    gap.detector_rule_id,
                    gap.detector_rule_version
                ))

                # Link to observations
                for obs_id in gap.observation_ids:
                    if obs_id:
                        conn.execute("""
                            INSERT OR IGNORE INTO gap_observations (gap_id, observation_id)
                            VALUES (?, ?)
                        """, (gap.id, obs_id))

                conn.commit()
            return True
        except Exception as e:
            print(f"Error saving gap: {e}")
            return False


def run_detection(limit: int = 100, db_path: Union[str, Path] = None) -> List[DetectedGap]:
    """Run gap detection on recent observations."""
    if db_path is None:
        db_path = DB_PATH
    detector = GapDetector(db_path=db_path)

    if not detector.rules:
        print("No detector rules loaded. Add rules to ~/homunculus/meta/detector-rules/")
        return []

    # Load observations from current session
    obs_file = HOMUNCULUS_ROOT / "observations" / "current.jsonl"
    observations = read_jsonl(obs_file)

    if not observations:
        return []

    # Get unprocessed observations
    unprocessed = [o for o in observations if not o.get('processed')][:limit]

    if not unprocessed:
        return []

    # Detect gaps
    gaps = detector.detect_from_observations(unprocessed)

    # Save gaps
    saved_gaps = []
    for gap in gaps:
        if detector.save_gap(gap):
            saved_gaps.append(gap)

    return saved_gaps


if __name__ == "__main__":
    print("Running gap detection...")
    gaps = run_detection()
    print(f"\nDetected {len(gaps)} new gap(s)")
    for gap in gaps:
        print(f"  - [{gap.gap_type}] {gap.desired_capability[:50]}... (conf: {gap.confidence:.2f})")
