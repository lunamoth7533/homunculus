#!/usr/bin/env python3
"""
Meta-Observer for Homunculus Layer 2.
Collects metrics about detector, template, and capability performance.
"""

from typing import Dict, List, Any
from datetime import datetime, timedelta, timezone

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from utils import db_execute, get_timestamp, load_config


def collect_detector_metrics(db_path=None) -> List[Dict[str, Any]]:
    """
    Collect performance metrics for all detector rules.

    Returns list of dicts with:
    - detector_rule_id, detector_rule_version
    - gaps_detected, proposals_generated
    - proposals_installed, proposals_rejected
    - gaps_dismissed, gaps_resolved
    - avg_confidence, dismissal_rate, approval_rate
    """
    query = """
        SELECT
            g.detector_rule_id,
            g.detector_rule_version,
            COUNT(DISTINCT g.id) as gaps_detected,
            COUNT(DISTINCT p.id) as proposals_generated,
            SUM(CASE WHEN p.status = 'installed' THEN 1 ELSE 0 END) as proposals_installed,
            SUM(CASE WHEN p.status = 'rejected' THEN 1 ELSE 0 END) as proposals_rejected,
            SUM(CASE WHEN g.status = 'dismissed' THEN 1 ELSE 0 END) as gaps_dismissed,
            SUM(CASE WHEN g.status = 'resolved' THEN 1 ELSE 0 END) as gaps_resolved,
            AVG(g.confidence) as avg_confidence
        FROM gaps g
        LEFT JOIN proposals p ON g.id = p.gap_id
        WHERE g.detector_rule_id IS NOT NULL
        GROUP BY g.detector_rule_id, g.detector_rule_version
        HAVING COUNT(g.id) >= 1
    """

    metrics = db_execute(query, db_path=db_path) if db_path else db_execute(query)

    # Calculate derived rates
    for m in metrics:
        gaps = m['gaps_detected'] or 0
        installed = m['proposals_installed'] or 0
        rejected = m['proposals_rejected'] or 0
        dismissed = m['gaps_dismissed'] or 0

        total_outcomes = installed + rejected + dismissed
        m['dismissal_rate'] = dismissed / gaps if gaps > 0 else 0
        m['approval_rate'] = installed / total_outcomes if total_outcomes > 0 else 0
        m['rejection_rate'] = rejected / total_outcomes if total_outcomes > 0 else 0

    return metrics


def collect_template_metrics(db_path=None) -> List[Dict[str, Any]]:
    """
    Collect performance metrics for all synthesis templates.

    Returns list of dicts with:
    - template_id, template_version
    - proposals_generated, installed, rejected, rolled_back
    - capabilities_active
    - approval_rate, retention_rate, rollback_rate
    """
    query = """
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
        WHERE p.template_id IS NOT NULL
        GROUP BY p.template_id, p.template_version
        HAVING COUNT(p.id) >= 1
    """

    metrics = db_execute(query, db_path=db_path) if db_path else db_execute(query)

    # Calculate derived rates
    for m in metrics:
        generated = m['proposals_generated'] or 0
        installed = m['installed'] or 0
        rejected = m['rejected'] or 0
        rolled_back = m['rolled_back'] or 0
        active = m['capabilities_active'] or 0

        total_outcomes = installed + rejected
        m['approval_rate'] = installed / total_outcomes if total_outcomes > 0 else 0
        m['retention_rate'] = active / installed if installed > 0 else 0
        m['rollback_rate'] = rolled_back / installed if installed > 0 else 0

    return metrics


def collect_capability_usage_metrics(db_path=None, min_days_installed: int = 14) -> List[Dict[str, Any]]:
    """
    Collect usage metrics for installed capabilities.

    Args:
        min_days_installed: Only include capabilities installed at least this many days ago

    Returns list of dicts with:
    - capability_id, name, capability_type
    - days_installed, usage_count, last_used
    - usage_rate (uses per day)
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=min_days_installed)).strftime("%Y-%m-%dT%H:%M:%SZ")

    query = """
        SELECT
            c.id as capability_id,
            c.name,
            c.capability_type,
            c.installed_at,
            COUNT(u.id) as usage_count,
            MAX(u.used_at) as last_used
        FROM capabilities c
        LEFT JOIN capability_usage u ON c.id = u.capability_id
        WHERE c.status = 'active' AND c.installed_at <= ?
        GROUP BY c.id
    """

    metrics = db_execute(query, (cutoff,), db_path=db_path) if db_path else db_execute(query, (cutoff,))

    now = datetime.now(timezone.utc)
    for m in metrics:
        # Calculate days installed
        try:
            installed = datetime.fromisoformat(m['installed_at'].replace('Z', '+00:00'))
            m['days_installed'] = (now - installed).days
        except (ValueError, AttributeError):
            m['days_installed'] = min_days_installed

        # Calculate usage rate
        usage = m['usage_count'] or 0
        days = m['days_installed'] or 1
        m['usage_rate'] = usage / days

    return metrics


def get_recent_rejections(limit: int = 50, db_path=None) -> List[Dict[str, Any]]:
    """
    Get recent rejection data for pattern analysis.

    Returns list of dicts with:
    - proposal_id, capability_type, template_id
    - rejection_reason, gap_type, detector_rule_id
    """
    query = """
        SELECT
            p.id as proposal_id,
            p.capability_type,
            p.template_id,
            p.rejection_reason,
            g.gap_type,
            g.detector_rule_id
        FROM proposals p
        JOIN gaps g ON p.gap_id = g.id
        WHERE p.status = 'rejected' AND p.rejection_reason IS NOT NULL
        ORDER BY p.reviewed_at DESC
        LIMIT ?
    """

    return db_execute(query, (limit,), db_path=db_path) if db_path else db_execute(query, (limit,))


def get_rollback_data(limit: int = 50, db_path=None) -> List[Dict[str, Any]]:
    """
    Get rollback data for analysis.

    Returns list of dicts with capability and proposal info.
    """
    query = """
        SELECT
            c.id as capability_id,
            c.name,
            c.capability_type,
            c.installed_at,
            c.rolled_back_at,
            p.template_id,
            p.gap_id,
            g.gap_type,
            g.detector_rule_id
        FROM capabilities c
        LEFT JOIN proposals p ON c.source_proposal_id = p.id
        LEFT JOIN gaps g ON p.gap_id = g.id
        WHERE c.status = 'rolled_back'
        ORDER BY c.rolled_back_at DESC
        LIMIT ?
    """

    return db_execute(query, (limit,), db_path=db_path) if db_path else db_execute(query, (limit,))


def collect_all_metrics(db_path=None) -> Dict[str, Any]:
    """
    Collect all metrics in one call.

    Returns dict with:
    - detector_metrics: List of detector performance data
    - template_metrics: List of template performance data
    - usage_metrics: List of capability usage data
    - recent_rejections: List of recent rejections
    - rollback_data: List of recent rollbacks
    - collected_at: Timestamp
    """
    return {
        'detector_metrics': collect_detector_metrics(db_path),
        'template_metrics': collect_template_metrics(db_path),
        'usage_metrics': collect_capability_usage_metrics(db_path),
        'recent_rejections': get_recent_rejections(db_path=db_path),
        'rollback_data': get_rollback_data(db_path=db_path),
        'collected_at': get_timestamp()
    }


if __name__ == "__main__":
    import json

    print("Collecting meta-observer metrics...")
    metrics = collect_all_metrics()

    print(f"\nDetector metrics: {len(metrics['detector_metrics'])} rules")
    for m in metrics['detector_metrics'][:3]:
        print(f"  {m['detector_rule_id']}: {m['gaps_detected']} gaps, "
              f"{m['approval_rate']:.0%} approval, {m['dismissal_rate']:.0%} dismissal")

    print(f"\nTemplate metrics: {len(metrics['template_metrics'])} templates")
    for m in metrics['template_metrics'][:3]:
        print(f"  {m['template_id']}: {m['proposals_generated']} proposals, "
              f"{m['approval_rate']:.0%} approval, {m['rollback_rate']:.0%} rollback")

    print(f"\nUsage metrics: {len(metrics['usage_metrics'])} capabilities")
    for m in metrics['usage_metrics'][:3]:
        print(f"  {m['name']}: {m['usage_count']} uses in {m['days_installed']} days")
