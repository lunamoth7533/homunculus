# Homunculus

> **Self-evolving capabilities for Claude Code** — Automatically detects what Claude can't do and proposes solutions.

Homunculus observes your Claude Code sessions, identifies capability gaps (like "I can't read PDFs"), and generates new skills, hooks, and tools to fix them. All changes require your approval.

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/homunculus.git ~/homunculus

# 2. Initialize
cd ~/homunculus && python3 scripts/cli.py init

# 3. Check status
python3 scripts/cli.py status
```

Then in Claude Code:
```
/homunculus status      # View system status
/homunculus proposals   # See pending proposals
/homunculus approve <id> # Install a capability
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Gap Detection** | Identifies 16 types of capability gaps (tool, knowledge, workflow, etc.) |
| **Auto-Synthesis** | Generates skills, hooks, agents, commands, and MCP servers |
| **Human Approval** | All changes require your explicit approval before installation |
| **Safe Rollback** | Every installed capability can be instantly rolled back |
| **Meta-Evolution** | The system improves its own detection over time (Layer 2) |
| **Project Scoping** | Capabilities can be session, project, or global scoped |
| **Zero API Costs** | No external API calls required for core functionality |

---

## Prerequisites

- **Python 3.8+** with standard library
- **Claude Code** CLI installed
- **~50MB disk space** for database and logs

---

## Installation

### Option A: As a Claude Code Plugin (Recommended)

```bash
# 1. Clone to home directory
git clone https://github.com/yourusername/homunculus.git ~/homunculus

# 2. Initialize the database
cd ~/homunculus
python3 scripts/cli.py init

# 3. In Claude Code, add the plugin
/plugin marketplace add ~/homunculus
/plugin install homunculus@homunculus

# 4. Restart Claude Code to activate hooks
```

### Option B: Manual Setup

```bash
# 1. Clone and initialize
git clone https://github.com/yourusername/homunculus.git ~/homunculus
cd ~/homunculus
python3 scripts/cli.py init

# 2. Add hooks manually to ~/.claude/settings.json
# (See docs/hook-setup.md for details)
```

### Verify Installation

```bash
python3 ~/homunculus/scripts/cli.py status
```

You should see:
```
============================================================
  HOMUNCULUS STATUS
============================================================
  Observations: 0
  Gaps detected: 0
  Proposals: 0
  Installed capabilities: 0
============================================================
```

---

## Usage

### In Claude Code (Recommended)

Use the `/homunculus` command directly in your Claude Code sessions:

| Command | Description |
|---------|-------------|
| `/homunculus` | Show system status |
| `/homunculus gaps` | List detected capability gaps |
| `/homunculus proposals` | List pending proposals |
| `/homunculus review <id>` | Preview a proposal |
| `/homunculus approve <id>` | Install a proposal |
| `/homunculus reject <id>` | Reject a proposal |
| `/homunculus capabilities` | List installed capabilities |
| `/homunculus rollback <name>` | Remove an installed capability |

### From Terminal

You can also run commands directly:

```bash
# Status and monitoring
python3 ~/homunculus/scripts/cli.py status
python3 ~/homunculus/scripts/cli.py gaps
python3 ~/homunculus/scripts/cli.py proposals

# Manual triggers
python3 ~/homunculus/scripts/cli.py detect      # Run gap detection
python3 ~/homunculus/scripts/cli.py synthesize  # Generate proposals

# Manage proposals
python3 ~/homunculus/scripts/cli.py review <id>
python3 ~/homunculus/scripts/cli.py approve <id>
python3 ~/homunculus/scripts/cli.py reject <id> --reason "Not needed"

# Manage capabilities
python3 ~/homunculus/scripts/cli.py capabilities
python3 ~/homunculus/scripts/cli.py rollback <name>

# Advanced
python3 ~/homunculus/scripts/cli.py meta-status    # Layer 2 status
python3 ~/homunculus/scripts/cli.py config         # View config
python3 ~/homunculus/scripts/cli.py dismiss-gap <id>  # Ignore a gap
```

---

## How It Works

```
You use Claude Code normally
         │
         ▼
┌─────────────────────────────────────┐
│  1. OBSERVE                         │
│  Hooks capture tool usage,          │
│  errors, and "I can't..." moments   │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  2. DETECT                          │
│  16 rules analyze patterns to       │
│  identify capability gaps           │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  3. SYNTHESIZE                      │
│  Generate proposals for new         │
│  skills, hooks, agents, etc.        │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  4. REVIEW (You)                    │
│  Approve, reject, or edit           │
│  each proposal                      │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  5. INSTALL                         │
│  Approved capabilities are          │
│  installed (with rollback option)   │
└─────────────────────────────────────┘
```

### What Gets Generated

| Type | Description | Example |
|------|-------------|---------|
| **Skill** | Instructions for Claude | "How to handle PDF files" |
| **Hook** | Automated triggers | "Run tests before commits" |
| **Agent** | Specialized subagent | "Database optimization expert" |
| **Command** | Slash command | `/format-sql` |
| **MCP Server** | External integration | Slack, Jira, custom APIs |

---

## Project Structure

```
~/homunculus/
├── config.yaml          # Configuration (edit this!)
├── homunculus.db        # SQLite database
├── observations/        # Captured session data
├── evolved/             # YOUR installed capabilities
│   ├── skills/
│   ├── hooks/
│   ├── agents/
│   ├── commands/
│   └── mcp-servers/
├── meta/
│   ├── detector-rules/  # Customize gap detection
│   └── synthesis-templates/
├── scripts/             # Core engine (don't edit)
└── tests/               # 107 tests
```

**Key files:**
- `config.yaml` — Adjust thresholds, enable/disable features
- `meta/detector-rules/*.yaml` — Customize what gaps to detect
- `evolved/*` — Your generated capabilities live here

---

## Configuration

Edit `~/homunculus/config.yaml`:

```yaml
detection:
  min_confidence_threshold: 0.3    # Lower = more sensitive (0.0-1.0)
  auto_synthesize_threshold: 0.7   # Auto-generate proposals above this
  triggers:
    on_failure: true               # Detect on tool failures
    on_friction: true              # Detect on repeated clarifications
    on_session_end: true           # Analyze at session end

synthesis:
  max_proposals_per_day: 10        # Avoid proposal overload

meta_evolution:
  enabled: true                    # Layer 2 self-improvement

storage:
  archive_after_days: 7            # Keep observations for 7 days
```

**Common tweaks:**
- Raise `min_confidence_threshold` to `0.5` if getting too many gaps
- Set `max_proposals_per_day: 5` to reduce noise
- Disable `meta_evolution` if you want a simpler system

---

## Gap Types

Homunculus detects **16 types** of capability gaps:

**Core Gaps**
- `tool` — Missing tool or integration (e.g., "can't read PDFs")
- `knowledge` — Missing domain expertise (e.g., "unfamiliar with this API")
- `workflow` — Inefficient repetitive process

**Integration Gaps**
- `integration` — Can't connect to external services
- `context` — Lost project/session context
- `permission` — Blocked by access controls

**Quality Gaps**
- `quality` — Repeated mistakes or poor output
- `speed` — Tasks taking too long
- `recovery` — Can't recover from errors

**Communication Gaps**
- `communication` — Misunderstanding user intent
- `reasoning` — Complex logic failures
- `verification` — Can't validate correctness

**Meta Gaps**
- `discovery` — Didn't know capability existed
- `learning` — Not retaining patterns
- `evolution` — System needs improvement
- `self_awareness` — Unknown limitations

## Running Tests

```bash
cd ~/homunculus && python3 -m pytest tests/ -v
# OR
python3 -m unittest discover tests/ -v
```

---

## Troubleshooting

### Hooks not triggering

```bash
# Check observe.sh is executable
chmod +x ~/homunculus/scripts/observe.sh

# Verify observations are being captured
cat ~/homunculus/observations/current.jsonl

# Restart Claude Code after any hook changes
```

### Database errors

```bash
# Re-initialize (preserves observations)
python3 ~/homunculus/scripts/cli.py init --force
```

### No gaps detected

```bash
# Check observations exist
cat ~/homunculus/observations/current.jsonl

# Run detection manually
python3 ~/homunculus/scripts/cli.py detect
```

### Proposals not generating

```bash
# Check for pending gaps first
python3 ~/homunculus/scripts/cli.py gaps

# Run synthesis manually
python3 ~/homunculus/scripts/cli.py synthesize
```

---

## FAQ

**Q: Does this cost money?**
A: No. Core functionality uses no external APIs. Optional LLM-enhanced synthesis can use Claude API if configured.

**Q: Is it safe?**
A: Yes. Nothing is installed without your explicit approval. Every change can be rolled back.

**Q: Will it slow down Claude Code?**
A: Minimal impact. Hooks are lightweight and run asynchronously.

**Q: Can I customize detection rules?**
A: Yes. Edit YAML files in `meta/detector-rules/` to adjust sensitivity or add new patterns.

**Q: What if a generated capability is bad?**
A: Reject it during review, or use `rollback <name>` after installation.

## Contributing

**Add custom detector rules:**
```bash
# Create a new YAML file in meta/detector-rules/
cp meta/detector-rules/tool-gap.yaml meta/detector-rules/my-custom-gap.yaml
# Edit to define your detection patterns
```

**Add synthesis templates:**
```bash
# Create templates in meta/synthesis-templates/
```

See existing files for format examples.

---

## License

MIT License — See [LICENSE](LICENSE) file.

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                      Claude Code                           │
│   PreToolUse ─────┬───── PostToolUse ─────┬───── Stop     │
└───────────────────┼───────────────────────┼────────────────┘
                    │                       │
                    ▼                       ▼
┌────────────────────────────────────────────────────────────┐
│                    LAYER 1: Evolution                      │
│                                                            │
│   Observe ──▶ Detect ──▶ Synthesize ──▶ Review ──▶ Install │
│                                           │                │
│                                      (You approve)         │
└────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌────────────────────────────────────────────────────────────┐
│                 LAYER 2: Meta-Evolution                    │
│                                                            │
│   Monitors Layer 1 performance and proposes improvements   │
│   to detection rules and synthesis templates               │
└────────────────────────────────────────────────────────────┘
```

---

<p align="center">
  <i>Built for Claude Code — Let your AI assistant evolve.</i>
</p>
