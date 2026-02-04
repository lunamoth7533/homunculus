#!/usr/bin/env python3
"""
Template rendering engine for Homunculus capability synthesis.
Provides context-based template substitution with safe handling of missing keys.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional
import re


class SafeDict(dict):
    """
    A dict that returns the original placeholder for missing keys.
    This allows partial template substitution without errors.
    """
    def __missing__(self, key: str) -> str:
        return '{' + key + '}'


@dataclass
class RenderContext:
    """Context object for template rendering with gap and proposal data."""
    gap_id: str = ""
    gap_type: str = ""
    domain: str = ""
    desired_capability: str = ""
    evidence_summary: str = ""
    recommended_scope: str = "global"
    confidence: float = 0.5
    timestamp: str = ""
    name: str = ""
    slug: str = ""
    title: str = ""
    # Additional fields for flexibility
    extra: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for template substitution."""
        result = asdict(self)
        # Remove 'extra' key and merge its contents
        extra = result.pop('extra', None) or {}
        result.update(extra)
        return result

    @classmethod
    def from_gap(cls, gap: Dict[str, Any], name: str = "", slug: str = "",
                 timestamp: str = "") -> 'RenderContext':
        """Create a RenderContext from a gap dictionary."""
        # Generate title from name
        title = name.replace('-', ' ').title() if name else ""

        return cls(
            gap_id=gap.get('id', ''),
            gap_type=gap.get('gap_type', ''),
            domain=gap.get('domain', 'general'),
            desired_capability=gap.get('desired_capability', ''),
            evidence_summary=gap.get('evidence_summary', ''),
            recommended_scope=gap.get('recommended_scope', 'global'),
            confidence=gap.get('confidence', 0.5),
            timestamp=timestamp,
            name=name,
            slug=slug,
            title=title
        )


class TemplateRenderer:
    """
    Template renderer with support for multi-file output.
    Uses str.format_map with SafeDict for missing key handling.
    """

    @staticmethod
    def render(template: str, context: RenderContext) -> str:
        """
        Render a template string with the given context.

        Missing keys are left as-is (e.g., {unknown_key} stays as {unknown_key}).
        """
        context_dict = SafeDict(context.to_dict())
        try:
            return template.format_map(context_dict)
        except (KeyError, ValueError) as e:
            # Fallback: try basic replacement
            result = template
            for key, value in context.to_dict().items():
                result = result.replace('{' + key + '}', str(value))
            return result

    @staticmethod
    def render_multi_file(
        output_files: List[Dict[str, Any]],
        context: RenderContext
    ) -> List[Dict[str, str]]:
        """
        Render multiple file templates with the given context.

        Args:
            output_files: List of dicts with 'path' and 'content' keys
            context: RenderContext for substitution

        Returns:
            List of dicts with rendered 'path' and 'content'
        """
        rendered_files = []
        context_dict = SafeDict(context.to_dict())

        for file_spec in output_files:
            try:
                # Render both path and content
                rendered_path = file_spec.get('path', '').format_map(context_dict)
                rendered_content = file_spec.get('content', '').format_map(context_dict)

                rendered_files.append({
                    'path': rendered_path,
                    'content': rendered_content,
                    'action': file_spec.get('action', 'create')
                })
            except (KeyError, ValueError):
                # Fallback rendering
                rendered_path = file_spec.get('path', '')
                rendered_content = file_spec.get('content', '')

                for key, value in context.to_dict().items():
                    rendered_path = rendered_path.replace('{' + key + '}', str(value))
                    rendered_content = rendered_content.replace('{' + key + '}', str(value))

                rendered_files.append({
                    'path': rendered_path,
                    'content': rendered_content,
                    'action': file_spec.get('action', 'create')
                })

        return rendered_files

    @staticmethod
    def escape_for_json(text: str) -> str:
        """Escape text for safe embedding in JSON strings."""
        return text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    @staticmethod
    def escape_for_typescript(text: str) -> str:
        """Escape text for safe embedding in TypeScript strings."""
        return text.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')


def create_render_context(
    gap: Dict[str, Any],
    name: str,
    slug: str,
    timestamp: str,
    extra: Optional[Dict[str, Any]] = None
) -> RenderContext:
    """
    Convenience function to create a RenderContext from gap data.

    Args:
        gap: Gap dictionary from database
        name: Generated capability name
        slug: URL-safe slug
        timestamp: ISO timestamp
        extra: Additional context variables

    Returns:
        RenderContext ready for template rendering
    """
    ctx = RenderContext.from_gap(gap, name, slug, timestamp)
    if extra:
        ctx.extra = extra
    return ctx
