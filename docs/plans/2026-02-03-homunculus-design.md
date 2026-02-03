# Homunculus: Self-Evolution System for Claude Code

**Version:** 1.0.0
**Date:** 2026-02-03
**Status:** Approved for Implementation

---

## Executive Summary

Homunculus is a self-evolution system that enables Claude Code to detect capability gaps, synthesize solutions, and improve its own improvement process over time. The system observes all Claude Code activity, identifies 16 types of gaps, generates capability proposals (skills, hooks, agents, commands, MCP servers), and requires human approval before installation.

**Key Principles:**
- Human-in-the-loop always (proposals require approval)
- Project-aware scoping (session, project, or global)
- Meta-evolution capability (system improves itself)
- Free to run (no external services required)
- Hybrid storage (Markdown for capabilities, SQLite for metadata)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Gap Taxonomy](#2-gap-taxonomy)
3. [Observation Layer](#3-observation-layer)
4. [Gap Detection Layer](#4-gap-detection-layer)
5. [Synthesis Layer](#5-synthesis-layer)
6. [Review & Installation Layer](#6-review--installation-layer)
7. [Meta-Evolution Layer](#7-meta-evolution-layer)
8. [CLI Commands](#8-cli-commands)
9. [Database Schema](#9-database-schema)
10. [Implementation Roadmap](#10-implementation-roadmap)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     CLAUDE CODE SESSION                          │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
    [PreToolUse]        [PostToolUse]         [Stop]
         │                    │                    │
         └────────────────────┴────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │      observations.jsonl       │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │       GAP DETECTION           │
              │      (16 gap types)           │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │    CAPABILITY SYNTHESIS       │
              │  (skills, hooks, agents...)   │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │      HUMAN APPROVAL           │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │      INSTALLATION             │
              └───────────────────────────────┘
                              │
         ┌────────────────────┴────────────────────┐
         │                                         │
         ▼                                         ▼
┌─────────────────┐                    ┌─────────────────────────┐
│  LAYER 2        │                    │   ACTIVE CAPABILITIES   │
│  META-EVOLUTION │◄───────────────────│   (skills, hooks, etc)  │
│  (self-improve) │    feedback        │                         │
└─────────────────┘                    └─────────────────────────┘
```

### Directory Structure

```
~/homunculus/
├── config.yaml                    # System configuration
├── homunculus.db                  # SQLite: relationships, metrics, history
│
├── observations/                  # Raw signal capture
│   ├── current.jsonl              # Active session observations
│   └── archive/                   # Processed observations by date
│
├── gaps/                          # Detected gaps (before synthesis)
│   ├── pending/                   # Awaiting synthesis
│   └── dismissed/                 # User dismissed
│
├── proposals/                     # Synthesized capabilities awaiting approval
│   ├── pending/                   # Ready for human review
│   ├── approved/                  # Approved, awaiting installation
│   └── rejected/                  # Rejected with reason (for meta-learning)
│
├── evolved/                       # Active capabilities (installed)
│   ├── skills/                    # .md skill files
│   ├── hooks/                     # Hook configurations
│   ├── agents/                    # Agent definitions
│   ├── commands/                  # User-invokable commands
│   └── mcp-servers/               # Generated MCP server code
│
├── meta/                          # Layer 2 (self-improvement)
│   ├── detector-rules/            # Gap detection rules (modifiable)
│   ├── synthesis-templates/       # Capability templates (modifiable)
│   ├── meta-rules/                # Meta-detection rules
│   ├── meta-templates/            # Meta-synthesis templates
│   └── feedback-log.jsonl         # Why proposals were accepted/rejected
│
├── scripts/                       # CLI and automation
│   ├── observe.sh                 # Hook script
│   ├── cli.py                     # Main CLI
│   ├── detect.py                  # Gap detection engine
│   ├── synthesize.py              # Capability synthesis
│   ├── install.py                 # Installation engine
│   ├── meta_observe.py            # Meta-observation
│   ├── meta_detect.py             # Meta-gap detection
│   └── meta_synthesize.py         # Meta-proposal synthesis
│
├── commands/                      # Skill files
│   └── homunculus.md              # Main command skill
│
└── docs/
    └── plans/
        └── 2026-02-03-homunculus-design.md  # This document
```

---

## 2. Gap Taxonomy

Homunculus detects 16 types of capability gaps:

### Core Gaps

| Gap Type | Description | Example |
|----------|-------------|---------|
| `tool` | Missing tool or integration | "I can't interact with Figma" |
| `knowledge` | Missing codebase/domain knowledge | "I don't understand this architecture" |
| `workflow` | Inefficient multi-step process | "I keep doing these 5 steps manually" |

### Extended Gaps

| Gap Type | Description | Example |
|----------|-------------|---------|
| `integration` | Two systems don't connect | "Can't sync GitHub issues to Notion" |
| `context` | Lost session/project context | "I forgot what we decided last time" |
| `permission` | Blocked by approval requirements | "I can't run this without approval" |
| `quality` | Repeated mistakes | "I keep introducing the same bug" |
| `speed` | Too slow/too many turns | "This simple task took 20 turns" |
| `communication` | Misunderstandings with user | "User keeps clarifying the same thing" |
| `recovery` | Can't recover from failures | "When X fails, I'm stuck" |
| `reasoning` | Struggles with problem type | "I struggle with concurrency bugs" |
| `verification` | Can't verify solutions work | "I can't tell if this fixed it" |
| `discovery` | Didn't know capability existed | "I didn't know that tool was available" |

### Meta Gaps

| Gap Type | Description | Example |
|----------|-------------|---------|
| `learning` | Not capturing useful patterns | "I'm not learning from corrections" |
| `evolution` | Evolution system lacking | "Gap detection is missing types" |
| `self_awareness` | Unknown unknowns | "I don't know what I don't know" |

---

## 3. Observation Layer

### 3.1 Hook Configuration

```yaml
# Added to ~/.claude/settings.json
hooks:
  PreToolUse:
    - matcher: "*"
      hooks:
        - type: command
          command: "~/homunculus/scripts/observe.sh pre"

  PostToolUse:
    - matcher: "*"
      hooks:
        - type: command
          command: "~/homunculus/scripts/observe.sh post"

  Notification:
    - matcher: "*"
      hooks:
        - type: command
          command: "~/homunculus/scripts/observe.sh notification"

  Stop:
    - matcher: "*"
      hooks:
        - type: command
          command: "~/homunculus/scripts/observe.sh stop"
```

### 3.2 Observation Schema

```typescript
interface Observation {
  id: string;                    // UUID
  timestamp: string;             // ISO 8601
  session_id: string;            // Current Claude session
  project_path: string | null;   // CWD if in a project

  event_type: "pre_tool" | "post_tool" | "notification" | "stop" | "user_signal";

  tool_name?: string;
  tool_input?: object;
  tool_result?: {
    success: boolean;
    error?: string;
    output_summary?: string;
  };

  friction_indicators?: {
    turn_count?: number;
    user_corrections?: number;
    clarifications?: number;
    explicit_frustration?: boolean;
  };

  failure_indicators?: {
    tool_error?: boolean;
    explicit_cant?: boolean;
    missing_capability?: string;
  };
}
```

### 3.3 Signal Extraction

| Signal Type | Detection Method | Priority |
|-------------|------------------|----------|
| Tool failure | `tool_result.success === false` | High |
| Explicit inability | Regex: `I can't\|I don't have\|not able to` | High |
| Missing tool | `tool not found` errors | High |
| Long session | `turn_count > 15` for single task | Medium |
| User correction | User contradicts Claude output | Medium |
| Repeated pattern | Same tool sequence 3+ times | Low |

---

## 4. Gap Detection Layer

### 4.1 Gap Schema

```typescript
interface Gap {
  id: string;
  detected_at: string;

  gap_type: GapType;           // One of 16 types
  domain: string;              // e.g., "pdf", "git", "testing"

  trigger_observations: string[];
  evidence_summary: string;
  confidence: number;          // 0.0 - 1.0

  recommended_scope: "session" | "project" | "global";
  project_path?: string;

  desired_capability: string;
  example_invocation?: string;

  detector_rule_id: string;    // For Layer 2 tracking

  status: "pending" | "synthesizing" | "proposed" | "rejected" | "resolved" | "dismissed";
}
```

### 4.2 Detection Rule Format

```yaml
# ~/homunculus/meta/detector-rules/tool-gap.yaml
---
id: tool-gap-detector
version: 1
gap_type: tool
priority: high
enabled: true

triggers:
  - condition: observation.failure_indicators.explicit_cant == true
    extract:
      desired_capability: "regex: can't (?:do|access|use) (.+)"
    confidence_boost: 0.3

  - condition: observation.tool_result.success == false
    confidence_boost: 0.2

min_confidence: 0.3
scope_inference:
  - if: "mentions project-specific tech"
    then: project
  - if: "general capability (pdf, slack)"
    then: global
  - default: session
```

### 4.3 Detection Triggers

| Trigger | Condition | Mode |
|---------|-----------|------|
| Immediate | Tool failure or explicit "can't" | Synchronous |
| Batch | Every 10 observations | Background |
| Session end | Stop hook fires | Background |
| Scheduled | Every 30 min if active | Background |
| Manual | `/homunculus detect` | Foreground |

---

## 5. Synthesis Layer

### 5.1 Template Format

```yaml
# ~/homunculus/meta/synthesis-templates/skill.yaml
---
id: skill-template
version: 1
output_type: skill
output_path: "evolved/skills/{slug}.md"

structure: |
  ---
  name: {name}
  description: {description}
  evolved_from:
    gap_id: {gap_id}
    gap_type: {gap_type}
  ---

  # {title}

  ## When to Use
  {trigger_description}

  ## Instructions
  {instructions}

  ## Examples
  {examples}

synthesis_prompt: |
  Generate a Claude Code skill to fill this capability gap:

  Gap: {gap.desired_capability}
  Evidence: {gap.evidence_summary}

  Generate a minimal skill that addresses the gap.
```

### 5.2 Capability Types

| Type | Output | Use Case |
|------|--------|----------|
| `skill` | Markdown file | Auto-triggered behaviors |
| `hook` | YAML + settings patch | Event-driven automation |
| `agent` | Markdown agent definition | Complex multi-step tasks |
| `command` | Markdown command file | User-invoked actions |
| `mcp_server` | TypeScript project | External tool integration |

### 5.3 Proposal Schema

```typescript
interface Proposal {
  id: string;
  created_at: string;

  gap_id: string;
  gap_type: GapType;

  capability_type: "skill" | "hook" | "agent" | "command" | "mcp_server";
  capability_name: string;
  capability_summary: string;

  files: {
    path: string;
    content: string;
    action: "create" | "modify";
  }[];

  settings_patch?: object;

  scope: "session" | "project" | "global";
  project_path?: string;

  confidence: number;
  reasoning: string;

  template_id: string;        // For Layer 2 tracking

  status: "pending" | "approved" | "rejected" | "installed" | "rolled_back";
  rejection_reason?: string;

  rollback_instructions: string;
}
```

---

## 6. Review & Installation Layer

### 6.1 Review Flow

```
/homunculus proposals          # List pending proposals
/homunculus review <id>        # View proposal details
/homunculus approve <id>       # Approve for installation
/homunculus reject <id>        # Reject with reason
```

### 6.2 Installation Process

1. Snapshot current state (for rollback)
2. Create files in `evolved/` directory
3. Apply settings.json patches if needed
4. For MCP servers: run npm install, update config
5. Update database with installation record
6. Move proposal to `approved/`

### 6.3 Scope-Aware Installation

| Scope | Location | Active When |
|-------|----------|-------------|
| session | `~/homunculus/evolved/session/` | Current session only |
| project | `<project>/.claude/evolved/` | In that project |
| global | `~/homunculus/evolved/` | All sessions |

### 6.4 Rollback

```
/homunculus rollback <name>    # Remove capability, restore state
```

All installations are reversible via stored pre-install state.

---

## 7. Meta-Evolution Layer

Layer 2 observes Layer 1 and improves it.

### 7.1 Meta-Observation

Tracks:
- Proposal acceptance rate by template
- Proposal acceptance rate by detector
- Rejection reasons (patterns)
- Capability usage after installation
- Recurring gaps (unsolved problems)

### 7.2 Meta-Detection

Detects:
- Low acceptance rate → template needs improvement
- Repeated "too_complex" rejections → simplify template
- Unused capabilities → bad detection
- Recurring gaps → synthesis didn't solve it

### 7.3 Meta-Synthesis

Generates:
- Improved detector rules
- Improved synthesis templates
- New gap type definitions
- Confidence threshold adjustments

### 7.4 Safety Constraints

- Max 3 meta-proposals per week
- All meta-changes require human approval
- 7-day rollback window
- No recursive meta (Layer 2 can't modify itself)

---

## 8. CLI Commands

```
/homunculus                     # Status dashboard
/homunculus status              # System health & statistics
/homunculus gaps                # List detected gaps
/homunculus gap <id>            # Gap details
/homunculus proposals           # List pending proposals
/homunculus review <id>         # Review proposal
/homunculus approve <id>        # Approve proposal
/homunculus reject <id>         # Reject proposal
/homunculus capabilities        # List installed capabilities
/homunculus rollback <name>     # Rollback capability
/homunculus dismiss-gap <id>    # Permanently ignore gap
/homunculus detect              # Manual gap detection
/homunculus synthesize [id]     # Manual synthesis
/homunculus meta-status         # Layer 2 status
/homunculus meta-proposals      # List meta-proposals
/homunculus meta-approve <id>   # Approve meta-proposal
/homunculus config              # View/edit configuration
/homunculus export              # Export for sharing
/homunculus import <file>       # Import capabilities
/homunculus init                # Initialize system
```

---

## 9. Database Schema

SQLite database (`~/homunculus/homunculus.db`) with tables:

**Core Tables:**
- `observations` - Raw captured observations
- `gaps` - Detected capability gaps
- `gap_observations` - Links gaps to evidence
- `proposals` - Synthesized capability proposals
- `capabilities` - Installed capabilities
- `capability_usage` - Usage tracking

**Meta Tables:**
- `detector_rules` - Versioned detection rules
- `synthesis_templates` - Versioned synthesis templates
- `meta_observations` - Layer 1 performance metrics
- `meta_proposals` - Layer 2 improvement proposals
- `feedback_log` - Approval/rejection history

**Support Tables:**
- `sessions` - Session tracking
- `metrics_daily` - Aggregated metrics

See full schema in `scripts/schema.sql`.

---

## 10. Implementation Roadmap

### Phase 1: Foundation (Week 1)
- Directory structure
- Database schema
- Observation hooks
- Basic CLI (`init`, `status`)

### Phase 2: Gap Detection (Week 2)
- All 16 detector rules
- Detection engine
- Detection triggers
- Gap management CLI

### Phase 3: Synthesis Engine (Week 3)
- All 5 synthesis templates
- Synthesis engine
- Proposal validation
- Scope inference

### Phase 4: Review & Installation (Week 4)
- Review interface
- Installation engine
- Rollback support
- Feedback capture

### Phase 5: Meta-Evolution (Week 5-6)
- Meta-observer
- Meta-detectors
- Meta-synthesizer
- Meta-proposal flow

### Phase 6: Polish (Week 7)
- Performance optimization
- Export/import
- Documentation
- Error handling

---

## Dependencies

**Required:**
- Python 3.8+
- SQLite3 (built into Python)
- Claude Code CLI

**Optional:**
- Node.js (for MCP server generation)
- npm (for MCP server installation)

**No external services required.**

---

## Approval

This design has been reviewed and approved for implementation.

- Design complete: 2026-02-03
- Implementation start: Ready

---

*Homunculus: Teaching Claude to teach itself.*
