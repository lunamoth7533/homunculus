# Homunculus

**Self-Evolution System for Claude Code**

Homunculus is a Claude Code plugin that enables automatic detection of capability gaps and self-synthesis of new abilities. It observes Claude's interactions, identifies patterns where capabilities are missing, and proposes new skills, hooks, agents, and commands to address those gaps.

## Features

- **16 Gap Types**: Detects tool, knowledge, workflow, integration, context, permission, quality, speed, communication, recovery, reasoning, verification, discovery, learning, evolution, and self-awareness gaps
- **5 Capability Types**: Generates skills, hooks, agents, commands, and MCP servers
- **Human-in-the-Loop**: All proposed capabilities require human approval before installation
- **Rollback Support**: Every installed capability can be rolled back
- **Layer 2 Meta-Evolution**: The system monitors and improves its own detection and synthesis performance
- **Project-Aware Scoping**: Capabilities can be scoped to session, project, or global
- **Free to Run**: No external API calls required for core functionality

## Installation

### 1. Clone or Copy to Home Directory

```bash
# The plugin should be at ~/homunculus
cd ~
git clone <repository-url> homunculus
# OR if you already have it:
# mv /path/to/homunculus ~/homunculus
```

### 2. Initialize the Database

```bash
cd ~/homunculus
python3 scripts/cli.py init
```

### 3. Configure Claude Code Hooks

Add the following to your `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "~/homunculus/scripts/observe.sh post_tool \"$CLAUDE_TOOL_NAME\" \"$CLAUDE_TOOL_INPUT\""
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "~/homunculus/scripts/observe.sh stop"
          }
        ]
      }
    ]
  }
}
```

### 4. Restart Claude Code

Restart Claude Code to activate the hooks.

## Usage

### Check System Status

```bash
python3 ~/homunculus/scripts/cli.py status
```

### View Detected Gaps

```bash
# List all pending gaps
python3 ~/homunculus/scripts/cli.py gaps

# View details for a specific gap
python3 ~/homunculus/scripts/cli.py gap <gap-id>
```

### Run Gap Detection Manually

```bash
python3 ~/homunculus/scripts/cli.py detect
```

### Generate Capability Proposals

```bash
# Synthesize proposals for pending gaps
python3 ~/homunculus/scripts/cli.py synthesize

# Synthesize for a specific gap
python3 ~/homunculus/scripts/cli.py synthesize <gap-id>
```

### Review and Approve Proposals

```bash
# List pending proposals
python3 ~/homunculus/scripts/cli.py proposals

# Review a specific proposal (shows full details and file previews)
python3 ~/homunculus/scripts/cli.py review <proposal-id>

# Approve and install a proposal
python3 ~/homunculus/scripts/cli.py approve <proposal-id>

# Reject a proposal
python3 ~/homunculus/scripts/cli.py reject <proposal-id> --reason "Not needed"
```

### Manage Installed Capabilities

```bash
# List installed capabilities
python3 ~/homunculus/scripts/cli.py capabilities

# Rollback an installed capability
python3 ~/homunculus/scripts/cli.py rollback <capability-name>
```

### Meta-Evolution (Layer 2)

```bash
# Check meta-evolution status
python3 ~/homunculus/scripts/cli.py meta-status

# Run meta-analysis to identify system improvements
python3 ~/homunculus/scripts/cli.py meta-status --analyze
```

### Other Commands

```bash
# View configuration
python3 ~/homunculus/scripts/cli.py config

# Dismiss a gap permanently
python3 ~/homunculus/scripts/cli.py dismiss-gap <gap-id> --reason "Not relevant"

# Re-initialize (use with caution)
python3 ~/homunculus/scripts/cli.py init --force
```

## How It Works

### 1. Observation

Claude Code hooks capture tool usage events and store them in `~/homunculus/observations/current.jsonl`. Events include:
- Tool name and input
- Success/failure status
- Error messages
- Timing information

### 2. Gap Detection

The detection engine analyzes observations using 16 detector rules defined in `~/homunculus/meta/detector-rules/`. Each rule looks for patterns like:
- Explicit statements: "I can't...", "I don't have access to..."
- Tool failures with specific error patterns
- Repeated clarification requests
- Permission denials

### 3. Synthesis

When gaps are detected, the synthesis engine uses templates from `~/homunculus/meta/synthesis-templates/` to generate capability proposals. Templates exist for:
- **Skills**: Markdown instructions for Claude
- **Hooks**: Claude Code hooks for automation
- **Agents**: Specialized subagents for complex tasks
- **Commands**: User-invokable slash commands
- **MCP Servers**: Model Context Protocol servers

### 4. Human Review

All proposals require human approval. The review process shows:
- Full proposal details
- Generated file contents
- Reasoning for the proposal
- Approval/rejection options

### 5. Installation & Rollback

Approved proposals are installed to `~/homunculus/evolved/`. Every installation:
- Creates backup of any existing files
- Tracks rollback information
- Can be reversed with the `rollback` command

### 6. Meta-Evolution (Layer 2)

The system monitors its own performance:
- Tracks detector approval/rejection rates
- Identifies patterns in rejected proposals
- Proposes improvements to detection rules and templates

## Directory Structure

```
~/homunculus/
├── config.yaml              # System configuration
├── data/
│   └── homunculus.db        # SQLite database
├── observations/
│   └── current.jsonl        # Current session observations
├── evolved/                  # Installed capabilities
│   ├── skills/
│   ├── hooks/
│   ├── agents/
│   ├── commands/
│   └── mcp-servers/
├── meta/
│   ├── detector-rules/      # 16 gap detection rules
│   └── synthesis-templates/ # 5 capability templates
├── scripts/
│   ├── cli.py               # Main CLI
│   ├── utils.py             # Shared utilities
│   ├── detector.py          # Gap detection engine
│   ├── synthesizer.py       # Capability synthesis
│   ├── installer.py         # Install/rollback engine
│   ├── meta_evolution.py    # Layer 2 system
│   ├── gap_types.py         # Gap type definitions
│   ├── init_db.py           # Database initialization
│   ├── observe.sh           # Hook observation script
│   └── schema.sql           # Database schema
└── tests/                   # Test suite (107 tests)
```

## Configuration

Edit `~/homunculus/config.yaml` to customize:

```yaml
version: "1.0.0"

detection:
  min_confidence_threshold: 0.3    # Minimum confidence to detect a gap
  auto_synthesize_threshold: 0.7   # Auto-synthesize above this confidence
  triggers:
    on_failure: true               # Detect on tool failures
    on_friction: true              # Detect on repeated clarifications
    on_session_end: true           # Analyze at session end
    periodic_minutes: 30           # Periodic analysis interval

synthesis:
  synthesis_model: sonnet          # Model for complex synthesis
  detection_model: haiku           # Model for detection (faster)
  max_proposals_per_day: 10        # Rate limiting

meta_evolution:
  enabled: true                    # Enable Layer 2
  analysis_frequency: weekly       # How often to analyze
  max_meta_proposals_per_week: 3   # Rate limit meta-proposals

scoping:
  default_scope: global            # Default capability scope
  project_detection: auto          # Auto-detect project context

storage:
  observations_max_mb: 50          # Max observation storage
  archive_after_days: 7            # Archive old observations
```

## Gap Types

| Type | Description | Default Scope |
|------|-------------|---------------|
| tool | Missing tool or capability | global |
| knowledge | Missing domain knowledge | project |
| workflow | Inefficient multi-step process | project |
| integration | Can't connect to external service | global |
| context | Missing project/codebase context | project |
| permission | Blocked by permissions | global |
| quality | Output quality issues | global |
| speed | Performance too slow | project |
| communication | Misunderstanding user intent | session |
| recovery | Can't recover from errors | global |
| reasoning | Complex reasoning failures | global |
| verification | Can't verify correctness | project |
| discovery | Can't find information | project |
| learning | Repeating same mistakes | session |
| evolution | Can't improve own behavior | global |
| self_awareness | Unaware of own limitations | global |

## Running Tests

```bash
cd ~/homunculus
python3 -m unittest discover tests/ -v
```

All 107 tests should pass.

## Troubleshooting

### Hooks not triggering
- Verify `~/.claude/settings.json` is correctly configured
- Restart Claude Code after changing settings
- Check that `observe.sh` is executable: `chmod +x ~/homunculus/scripts/observe.sh`

### Database errors
- Re-initialize: `python3 scripts/cli.py init --force`
- Check permissions on `~/homunculus/data/`

### No gaps detected
- Ensure observations are being captured in `~/homunculus/observations/current.jsonl`
- Run detection manually: `python3 scripts/cli.py detect`

### Proposals not generating
- Check that synthesis templates exist in `~/homunculus/meta/synthesis-templates/`
- Run synthesis manually: `python3 scripts/cli.py synthesize`

## Contributing

Homunculus is designed to be extensible:

1. **Add new detector rules**: Create YAML files in `meta/detector-rules/`
2. **Add new synthesis templates**: Create YAML files in `meta/synthesis-templates/`
3. **Extend gap types**: Modify `scripts/gap_types.py`

## License

MIT License - See LICENSE file for details.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Claude Code                               │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │  PreToolUse │    │ PostToolUse │    │    Stop     │         │
│  │    Hook     │    │    Hook     │    │    Hook     │         │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘         │
└─────────┼──────────────────┼──────────────────┼─────────────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                     HOMUNCULUS (Layer 1)                        │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │  Observer   │───▶│  Detector   │───▶│ Synthesizer │         │
│  │             │    │ (16 rules)  │    │(5 templates)│         │
│  └─────────────┘    └─────────────┘    └──────┬──────┘         │
│                                               │                 │
│                     ┌─────────────┐    ┌──────▼──────┐         │
│                     │  Installer  │◀───│  Proposals  │         │
│                     │  +Rollback  │    │   (Human    │         │
│                     └──────┬──────┘    │   Review)   │         │
│                            │           └─────────────┘         │
│                            ▼                                    │
│                     ┌─────────────┐                             │
│                     │  Evolved    │                             │
│                     │Capabilities │                             │
│                     └─────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   META-EVOLUTION (Layer 2)                      │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │    Meta     │───▶│    Meta     │───▶│    Meta     │         │
│  │  Observer   │    │  Analyzer   │    │  Proposals  │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│         │                                      │                │
│         └──────────────────────────────────────┘                │
│              Improves detectors & templates                     │
└─────────────────────────────────────────────────────────────────┘
```
