---
name: homunculus
description: Self-evolution system - detect gaps, synthesize capabilities, manage proposals
---

# Homunculus - Self-Evolution System

You have access to the Homunculus self-evolution system. Use this skill when the user wants to:
- Check system status
- View detected capability gaps
- Review and approve/reject capability proposals
- Manage installed capabilities
- Run gap detection or synthesis manually

## Commands

Run these commands using Bash:

### Check Status
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py status
```

### List Detected Gaps
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py gaps
```

### View Gap Details
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py gap <gap-id>
```

### Run Gap Detection
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py detect
```

### Generate Proposals
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py synthesize
```

### List Pending Proposals
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py proposals
```

### Review a Proposal
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py review <proposal-id>
```

### Approve a Proposal (requires user confirmation)
When the user wants to approve, show them the proposal first with `review`, then ask for confirmation before running:
```bash
echo "y" | python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py approve <proposal-id>
```

### Reject a Proposal
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py reject <proposal-id> --reason "<reason>"
```

### List Installed Capabilities
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py capabilities
```

### Rollback a Capability (requires user confirmation)
```bash
echo "y" | python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py rollback <capability-name>
```

### Meta-Evolution Status (Layer 2)
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py meta-status
```

### Run Meta-Analysis
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py meta-status --analyze
```

## Workflow

1. **Observation**: The system automatically observes tool usage via hooks
2. **Detection**: Run `detect` to analyze observations for capability gaps
3. **Synthesis**: Run `synthesize` to generate proposals for detected gaps
4. **Review**: Use `review <id>` to see full proposal details
5. **Approve/Reject**: User decides whether to install the capability
6. **Rollback**: If needed, capabilities can be rolled back

## Important Notes

- Always show proposal details before asking for approval
- Never approve proposals without explicit user confirmation
- The system requires human-in-the-loop for all installations
- Rollback is available for all installed capabilities
