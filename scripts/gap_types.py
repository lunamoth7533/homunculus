#!/usr/bin/env python3
"""
Gap type definitions for Homunculus.
"""

from enum import Enum
from typing import Dict, Any


class GapType(str, Enum):
    """All supported gap types."""

    # Core gaps
    TOOL = "tool"
    KNOWLEDGE = "knowledge"
    WORKFLOW = "workflow"

    # Extended gaps
    INTEGRATION = "integration"
    CONTEXT = "context"
    PERMISSION = "permission"
    QUALITY = "quality"
    SPEED = "speed"
    COMMUNICATION = "communication"
    RECOVERY = "recovery"
    REASONING = "reasoning"
    VERIFICATION = "verification"
    DISCOVERY = "discovery"

    # Meta gaps
    LEARNING = "learning"
    EVOLUTION = "evolution"
    SELF_AWARENESS = "self_awareness"


GAP_TYPE_INFO: Dict[str, Dict[str, Any]] = {
    "tool": {
        "description": "Missing tool or integration capability",
        "examples": ["Can't read PDF files", "No Figma integration", "Can't access Slack"],
        "default_scope": "global",
        "priority": "high",
        "capability_types": ["skill", "mcp_server", "hook"]
    },
    "knowledge": {
        "description": "Missing codebase or domain knowledge",
        "examples": ["Don't understand this architecture", "Unfamiliar with this API"],
        "default_scope": "project",
        "priority": "medium",
        "capability_types": ["skill"]
    },
    "workflow": {
        "description": "Inefficient multi-step process",
        "examples": ["Keep repeating these steps", "Manual process should be automated"],
        "default_scope": "global",
        "priority": "medium",
        "capability_types": ["command", "skill", "agent"]
    },
    "integration": {
        "description": "Two systems don't connect properly",
        "examples": ["GitHub and Jira don't sync", "Can't connect API to database"],
        "default_scope": "project",
        "priority": "medium",
        "capability_types": ["mcp_server", "skill"]
    },
    "context": {
        "description": "Lost context between sessions or tasks",
        "examples": ["Forgot previous decisions", "Lost track of requirements"],
        "default_scope": "project",
        "priority": "medium",
        "capability_types": ["skill", "hook"]
    },
    "permission": {
        "description": "Blocked by approval or permission requirements",
        "examples": ["Need approval for this command", "Can't access without permission"],
        "default_scope": "global",
        "priority": "low",
        "capability_types": ["hook"]
    },
    "quality": {
        "description": "Repeated mistakes or quality issues",
        "examples": ["Keep introducing same bug", "Forgetting to add tests"],
        "default_scope": "global",
        "priority": "high",
        "capability_types": ["hook", "skill"]
    },
    "speed": {
        "description": "Task takes too long or too many turns",
        "examples": ["Simple task took 20 turns", "Slow response time"],
        "default_scope": "global",
        "priority": "medium",
        "capability_types": ["agent", "skill"]
    },
    "communication": {
        "description": "Misunderstandings or unclear communication",
        "examples": ["User keeps clarifying", "Misunderstood requirements"],
        "default_scope": "session",
        "priority": "low",
        "capability_types": ["skill"]
    },
    "recovery": {
        "description": "Can't recover from errors or failures",
        "examples": ["Stuck after error", "Don't know how to retry"],
        "default_scope": "global",
        "priority": "high",
        "capability_types": ["skill", "hook"]
    },
    "reasoning": {
        "description": "Struggles with specific problem types",
        "examples": ["Concurrency bugs are hard", "Complex algorithms"],
        "default_scope": "global",
        "priority": "medium",
        "capability_types": ["agent", "skill"]
    },
    "verification": {
        "description": "Can't verify if solution works",
        "examples": ["Can't test this", "No way to validate"],
        "default_scope": "project",
        "priority": "medium",
        "capability_types": ["skill", "hook"]
    },
    "discovery": {
        "description": "Didn't know a capability existed",
        "examples": ["Didn't know about this tool", "Missed available feature"],
        "default_scope": "global",
        "priority": "low",
        "capability_types": ["skill"]
    },
    "learning": {
        "description": "Not capturing useful patterns",
        "examples": ["Should remember this preference", "Pattern not being learned"],
        "default_scope": "global",
        "priority": "low",
        "capability_types": ["hook", "skill"]
    },
    "evolution": {
        "description": "Evolution system itself needs improvement",
        "examples": ["Detection missing gaps", "Templates producing bad output"],
        "default_scope": "global",
        "priority": "medium",
        "capability_types": ["skill"]
    },
    "self_awareness": {
        "description": "Unknown unknowns - gaps in self-knowledge",
        "examples": ["Don't know what I don't know", "Blind spots"],
        "default_scope": "global",
        "priority": "low",
        "capability_types": ["skill", "agent"]
    }
}


def get_gap_info(gap_type: str) -> Dict[str, Any]:
    """Get information about a gap type."""
    return GAP_TYPE_INFO.get(gap_type, {})


def get_all_gap_types() -> list:
    """Get list of all gap type values."""
    return [gt.value for gt in GapType]


def get_default_scope(gap_type: str) -> str:
    """Get default scope for a gap type."""
    info = get_gap_info(gap_type)
    return info.get("default_scope", "global")


def get_priority(gap_type: str) -> str:
    """Get priority for a gap type."""
    info = get_gap_info(gap_type)
    return info.get("priority", "medium")


def get_capability_types(gap_type: str) -> list:
    """Get recommended capability types for a gap type."""
    info = get_gap_info(gap_type)
    return info.get("capability_types", ["skill"])
