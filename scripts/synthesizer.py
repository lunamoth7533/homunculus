#!/usr/bin/env python3
"""
Capability synthesis engine for Homunculus.
Generates proposals from detected gaps.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

import sys
sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    HOMUNCULUS_ROOT, generate_id, get_timestamp, db_execute,
    load_yaml_file, get_db_connection
)
from gap_types import get_gap_info, get_capability_types


@dataclass
class SynthesisTemplate:
    """A synthesis template for generating capabilities."""
    id: str
    version: int
    output_type: str
    output_path: str
    applicable_gap_types: List[str]
    structure: str
    synthesis_prompt: str

    @classmethod
    def from_yaml(cls, data: Dict[str, Any]) -> 'SynthesisTemplate':
        return cls(
            id=data.get('id', ''),
            version=data.get('version', 1),
            output_type=data.get('output_type', ''),
            output_path=data.get('output_path', ''),
            applicable_gap_types=data.get('applicable_gap_types', []),
            structure=data.get('structure', ''),
            synthesis_prompt=data.get('synthesis_prompt', '')
        )


@dataclass
class Proposal:
    """A synthesized capability proposal."""
    id: str
    gap_id: str
    gap_type: str
    capability_type: str
    capability_name: str
    capability_summary: str
    scope: str
    confidence: float
    reasoning: str
    template_id: str
    template_version: int
    files: List[Dict[str, str]]
    rollback_instructions: str
    project_path: Optional[str] = None


class CapabilitySynthesizer:
    """Main synthesis engine."""

    def __init__(self):
        self.templates: Dict[str, SynthesisTemplate] = {}
        self.templates_dir = HOMUNCULUS_ROOT / "meta" / "synthesis-templates"
        self._load_templates()

    def _load_templates(self):
        """Load all synthesis templates."""
        if not self.templates_dir.exists():
            return

        for template_file in self.templates_dir.glob("*.yaml"):
            try:
                data = load_yaml_file(template_file)
                if data and data.get('id'):
                    template = SynthesisTemplate.from_yaml(data)
                    self.templates[template.output_type] = template
            except Exception as e:
                print(f"Warning: Failed to load template {template_file}: {e}")

    def select_template(self, gap_type: str) -> Optional[SynthesisTemplate]:
        """Select the best template for a gap type."""
        # Get recommended capability types for this gap
        recommended = get_capability_types(gap_type)

        # Find first matching template
        for cap_type in recommended:
            if cap_type in self.templates:
                template = self.templates[cap_type]
                if gap_type in template.applicable_gap_types:
                    return template

        # Fallback to skill template (most versatile)
        if 'skill' in self.templates:
            return self.templates['skill']

        return None

    def synthesize_from_gap(self, gap: Dict[str, Any]) -> Optional[Proposal]:
        """Synthesize a proposal from a gap."""
        gap_type = gap.get('gap_type', '')
        template = self.select_template(gap_type)

        if not template:
            print(f"No template found for gap type: {gap_type}")
            return None

        # Generate capability name from desired capability
        name = self._generate_name(gap.get('desired_capability', ''), gap.get('domain', ''))
        slug = self._slugify(name)

        # Generate the capability content
        content = self._generate_content(template, gap, name, slug)

        # Create proposal
        proposal = Proposal(
            id=generate_id("prop"),
            gap_id=gap.get('id', ''),
            gap_type=gap_type,
            capability_type=template.output_type,
            capability_name=name,
            capability_summary=self._generate_summary(gap),
            scope=gap.get('recommended_scope', 'global'),
            confidence=gap.get('confidence', 0.5),
            reasoning=f"Generated to address: {gap.get('desired_capability', '')}",
            template_id=template.id,
            template_version=template.version,
            files=[{
                "path": template.output_path.format(slug=slug),
                "content": content,
                "action": "create"
            }],
            rollback_instructions=f"rm ~/homunculus/{template.output_path.format(slug=slug)}",
            project_path=gap.get('project_path')
        )

        return proposal

    def _generate_name(self, desired_capability: str, domain: Optional[str]) -> str:
        """Generate a capability name from the desired capability."""
        # Extract key words
        cap_lower = desired_capability.lower()

        # Remove common prefixes
        for prefix in ['cannot ', "can't ", 'unable to ', "don't have ", 'no way to ']:
            if cap_lower.startswith(prefix):
                cap_lower = cap_lower[len(prefix):]
                break

        # Take first few meaningful words
        words = cap_lower.split()[:4]
        words = [w for w in words if len(w) > 2 and w not in ('the', 'and', 'for', 'with')]

        if domain and domain not in ' '.join(words):
            words.insert(0, domain)

        name = '-'.join(words[:3]) if words else 'capability'
        return name.replace(' ', '-')

    def _slugify(self, name: str) -> str:
        """Convert name to a valid slug."""
        # First convert spaces to dashes
        slug = name.lower().replace(' ', '-')
        # Remove any non-alphanumeric characters except dashes
        slug = re.sub(r'[^a-z0-9-]', '', slug)
        # Collapse multiple dashes into one
        slug = re.sub(r'-+', '-', slug)
        return slug.strip('-')[:50]

    def _generate_summary(self, gap: Dict[str, Any]) -> str:
        """Generate a one-line summary."""
        cap = gap.get('desired_capability', 'Unknown capability')
        if len(cap) > 80:
            cap = cap[:77] + '...'
        return cap

    def _generate_content(self, template: SynthesisTemplate, gap: Dict[str, Any],
                          name: str, slug: str) -> str:
        """Generate the capability file content."""
        timestamp = get_timestamp()

        # For now, generate a structured template without LLM
        # This can be enhanced later to use Claude for generation

        if template.output_type == 'skill':
            return self._generate_skill_content(gap, name, slug, timestamp)
        elif template.output_type == 'hook':
            return self._generate_hook_content(gap, name, slug, timestamp)
        elif template.output_type == 'agent':
            return self._generate_agent_content(gap, name, slug, timestamp)
        elif template.output_type == 'command':
            return self._generate_command_content(gap, name, slug, timestamp)
        elif template.output_type == 'mcp_server':
            return self._generate_mcp_server_content(gap, name, slug, timestamp)
        else:
            return self._generate_skill_content(gap, name, slug, timestamp)

    def _generate_skill_content(self, gap: Dict, name: str, slug: str, timestamp: str) -> str:
        """Generate skill markdown content."""
        desired = gap.get('desired_capability', 'Unknown')
        domain = gap.get('domain', 'general')
        evidence = gap.get('evidence_summary', '')

        return f'''---
name: {slug}
description: {desired[:100]}
evolved_from:
  gap_id: {gap.get('id', '')}
  gap_type: {gap.get('gap_type', '')}
  created: {timestamp}
---

# {name.replace('-', ' ').title()}

## When to Use
Use this skill when you need to {desired.lower()}.

Domain: {domain}

## What This Skill Does
This skill was auto-generated to address a detected capability gap:
- Gap: {desired}
- Evidence: {evidence}

## Instructions
1. Identify when this capability is needed
2. Follow the steps below to address the gap
3. Verify the solution works

### Steps
<!-- TODO: Add specific steps for this capability -->
1. Analyze the situation
2. Apply the appropriate solution
3. Verify the result

## Examples
### Example 1
<!-- TODO: Add concrete example -->

### Example 2
<!-- TODO: Add concrete example -->

---
*Generated by Homunculus on {timestamp}*
'''

    def _generate_hook_content(self, gap: Dict, name: str, slug: str, timestamp: str) -> str:
        """Generate hook yaml/markdown content."""
        desired = gap.get('desired_capability', 'Unknown')

        return f'''---
name: {slug}
description: {desired[:100]}
hook_type: PostToolUse
matcher: "*"
evolved_from:
  gap_id: {gap.get('id', '')}
  gap_type: {gap.get('gap_type', '')}
  created: {timestamp}
---

# Hook: {name.replace('-', ' ').title()}

## Purpose
{desired}

## Configuration
Add to ~/.claude/settings.json:

```json
{{
  "hooks": {{
    "PostToolUse": [
      {{
        "matcher": "*",
        "hooks": [
          {{
            "type": "command",
            "command": "echo 'Hook {slug} triggered'"
          }}
        ]
      }}
    ]
  }}
}}
```

## Implementation Notes
<!-- TODO: Implement actual hook logic -->

---
*Generated by Homunculus on {timestamp}*
'''

    def _generate_agent_content(self, gap: Dict, name: str, slug: str, timestamp: str) -> str:
        """Generate agent markdown content."""
        desired = gap.get('desired_capability', 'Unknown')
        domain = gap.get('domain', 'general')

        return f'''---
name: {slug}
description: {desired[:100]}
model: haiku
tools:
  - Read
  - Grep
  - Glob
  - Bash
evolved_from:
  gap_id: {gap.get('id', '')}
  gap_type: {gap.get('gap_type', '')}
  created: {timestamp}
---

# {name.replace('-', ' ').title()} Agent

## Purpose
{desired}

## When to Dispatch
Use the Task tool to dispatch this agent when:
- Working in the {domain} domain
- The main task matches: {desired[:50]}

## Agent Instructions
You are a specialized agent for {domain} tasks.

Your goal: {desired}

Steps:
1. Analyze the current situation
2. Gather necessary context
3. Execute the required actions
4. Report results

## Expected Outputs
- Summary of actions taken
- Any errors encountered
- Recommendations for follow-up

## Example Usage
```
Task(
  subagent_type="{slug}",
  prompt="Help with {domain} task"
)
```

---
*Generated by Homunculus on {timestamp}*
'''

    def _generate_command_content(self, gap: Dict, name: str, slug: str, timestamp: str) -> str:
        """Generate command markdown content."""
        desired = gap.get('desired_capability', 'Unknown')

        return f'''---
name: {slug}
description: {desired[:100]}
command: true
evolved_from:
  gap_id: {gap.get('id', '')}
  gap_type: {gap.get('gap_type', '')}
  created: {timestamp}
---

# /{slug} Command

## Usage
```
/{slug} [options]
```

## Description
{desired}

## Steps
When invoked:
1. Parse any provided arguments
2. Execute the required actions
3. Report results to the user

## Examples
### Basic usage
```
/{slug}
```

### With options
```
/{slug} --verbose
```

---
*Generated by Homunculus on {timestamp}*
'''

    def _generate_mcp_server_content(self, gap: Dict, name: str, slug: str, timestamp: str) -> str:
        """Generate MCP server content as a README with embedded code."""
        desired = gap.get('desired_capability', 'Unknown')
        domain = gap.get('domain', 'general')

        # Generate a tool name from the capability
        tool_name = slug.replace('-', '_')

        return f'''# {name.replace('-', ' ').title()} MCP Server

> Generated by Homunculus on {timestamp}

## Purpose

{desired}

## Quick Setup

1. Create the server directory and files:

```bash
mkdir -p ~/homunculus/evolved/mcp-servers/{slug}
cd ~/homunculus/evolved/mcp-servers/{slug}
```

2. Create `package.json`:

```json
{{
  "name": "{slug}-mcp-server",
  "version": "1.0.0",
  "type": "module",
  "main": "index.ts",
  "scripts": {{
    "start": "npx tsx index.ts"
  }},
  "dependencies": {{
    "@modelcontextprotocol/sdk": "^1.0.0"
  }},
  "devDependencies": {{
    "tsx": "^4.0.0",
    "typescript": "^5.0.0"
  }}
}}
```

3. Create `index.ts`:

```typescript
import {{ Server }} from "@modelcontextprotocol/sdk/server/index.js";
import {{ StdioServerTransport }} from "@modelcontextprotocol/sdk/server/stdio.js";
import {{
  CallToolRequestSchema,
  ListToolsRequestSchema,
}} from "@modelcontextprotocol/sdk/types.js";

const server = new Server(
  {{ name: "{slug}", version: "1.0.0" }},
  {{ capabilities: {{ tools: {{}} }} }}
);

// Define available tools
server.setRequestHandler(ListToolsRequestSchema, async () => ({{
  tools: [
    {{
      name: "{tool_name}",
      description: "{desired[:100].replace('"', '\\"')}",
      inputSchema: {{
        type: "object",
        properties: {{
          input: {{
            type: "string",
            description: "Input for the {domain} operation"
          }}
        }},
        required: ["input"]
      }}
    }}
  ]
}}));

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {{
  const {{ name, arguments: args }} = request.params;

  if (name === "{tool_name}") {{
    // TODO: Implement the actual functionality
    const input = args?.input as string || "";

    try {{
      // Placeholder implementation
      const result = `Processed: ${{input}}`;

      return {{
        content: [{{ type: "text", text: result }}]
      }};
    }} catch (error) {{
      return {{
        content: [{{ type: "text", text: `Error: ${{error}}` }}],
        isError: true
      }};
    }}
  }}

  return {{
    content: [{{ type: "text", text: `Unknown tool: ${{name}}` }}],
    isError: true
  }};
}});

// Start the server
const transport = new StdioServerTransport();
server.connect(transport);
console.error("{slug} MCP server started");
```

4. Install dependencies and test:

```bash
npm install
npm start
```

## Configure Claude Code

Add to `~/.claude/settings.json`:

```json
{{
  "mcpServers": {{
    "{slug}": {{
      "command": "npx",
      "args": ["tsx", "~/homunculus/evolved/mcp-servers/{slug}/index.ts"]
    }}
  }}
}}
```

## Evolved From

- **Gap ID**: {gap.get('id', 'unknown')}
- **Gap Type**: {gap.get('gap_type', 'unknown')}
- **Domain**: {domain}
- **Created**: {timestamp}

## TODO

- [ ] Implement actual tool functionality
- [ ] Add input validation
- [ ] Add error handling for edge cases
- [ ] Add additional tools if needed
'''

    def save_proposal(self, proposal: Proposal) -> bool:
        """Save a proposal to the database."""
        try:
            with get_db_connection() as conn:
                conn.execute("""
                    INSERT INTO proposals (
                        id, created_at, gap_id, capability_type, capability_name,
                        capability_summary, scope, project_path, confidence, reasoning,
                        template_id, template_version, synthesis_model, status,
                        files_json, rollback_instructions
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """, (
                    proposal.id,
                    get_timestamp(),
                    proposal.gap_id,
                    proposal.capability_type,
                    proposal.capability_name,
                    proposal.capability_summary,
                    proposal.scope,
                    proposal.project_path,
                    proposal.confidence,
                    proposal.reasoning,
                    proposal.template_id,
                    proposal.template_version,
                    "template-based",  # synthesis_model
                    json.dumps(proposal.files),
                    proposal.rollback_instructions
                ))

                # Update gap status
                conn.execute(
                    "UPDATE gaps SET status = 'proposed', resolved_by_proposal_id = ? WHERE id = ?",
                    (proposal.id, proposal.gap_id)
                )

                conn.commit()
            return True
        except Exception as e:
            print(f"Error saving proposal: {e}")
            return False


def run_synthesis(gap_id: Optional[str] = None, limit: int = 5) -> List[Proposal]:
    """Run synthesis on pending gaps."""
    synthesizer = CapabilitySynthesizer()

    if not synthesizer.templates:
        print("No synthesis templates loaded.")
        return []

    # Get pending gaps
    if gap_id:
        gaps = db_execute(
            "SELECT * FROM gaps WHERE id = ? OR id LIKE ?",
            (gap_id, f"{gap_id}%")
        )
    else:
        gaps = db_execute(
            """SELECT * FROM gaps
               WHERE status = 'pending'
               ORDER BY confidence DESC
               LIMIT ?""",
            (limit,)
        )

    if not gaps:
        return []

    proposals = []
    for gap in gaps:
        proposal = synthesizer.synthesize_from_gap(gap)
        if proposal and synthesizer.save_proposal(proposal):
            proposals.append(proposal)

    return proposals


if __name__ == "__main__":
    import sys
    gap_id = sys.argv[1] if len(sys.argv) > 1 else None
    print("Running synthesis...")
    proposals = run_synthesis(gap_id)
    print(f"\nGenerated {len(proposals)} proposal(s)")
    for p in proposals:
        print(f"  - [{p.capability_type}] {p.capability_name} (conf: {p.confidence:.2f})")
