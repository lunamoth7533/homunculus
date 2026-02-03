---
name: homunculus
description: Self-evolution system management - detect gaps, review proposals, manage capabilities
command: true
---

# Homunculus Command

Self-evolution system for Claude Code.

## Usage

Run the homunculus CLI with the provided arguments:

```bash
python3 ~/homunculus/scripts/cli.py {subcommand} {args}
```

## Available Subcommands

| Command | Description |
|---------|-------------|
| `status` | Show system health and statistics |
| `init` | Initialize Homunculus (first run) |
| `gaps` | List detected capability gaps |
| `gap <id>` | View details of a specific gap |
| `proposals` | List pending proposals for review |
| `review <id>` | View details of a specific proposal |
| `approve <id>` | Approve a proposal for installation |
| `reject <id>` | Reject a proposal |
| `capabilities` | List installed capabilities |
| `rollback <name>` | Remove an installed capability |
| `dismiss-gap <id>` | Permanently ignore a gap |
| `detect` | Manually trigger gap detection |
| `synthesize` | Manually trigger capability synthesis |
| `config` | View configuration |
| `meta-status` | View meta-evolution status |

## Examples

```bash
# Show status (default if no subcommand)
python3 ~/homunculus/scripts/cli.py status

# List pending proposals
python3 ~/homunculus/scripts/cli.py proposals

# Approve a proposal
python3 ~/homunculus/scripts/cli.py approve prop-abc123

# Reject with reason
python3 ~/homunculus/scripts/cli.py reject prop-abc123 --reason "too_complex"
```

## Instructions

1. Parse the user's command to identify the subcommand and arguments
2. Run the CLI script with those arguments
3. Display the output to the user
4. If the user just says "/homunculus" with no arguments, run "status"
