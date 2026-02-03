# Hook Setup for Homunculus

To enable automatic observation of Claude Code activity, add these hooks to your settings.

## Installation

Add the following to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "~/homunculus/scripts/observe.sh pre"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "~/homunculus/scripts/observe.sh post"
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

## Verification

After adding hooks, restart Claude Code and run a few commands. Then check:

```bash
cat ~/homunculus/observations/current.jsonl
```

You should see JSON lines for each tool use.

## Troubleshooting

### Hooks not firing
- Ensure the observe.sh script is executable: `chmod +x ~/homunculus/scripts/observe.sh`
- Check Claude Code logs for hook errors

### No observations recorded
- Verify the observations directory exists: `ls ~/homunculus/observations/`
- Check script permissions

### JSON parse errors
- The hook receives JSON on stdin; ensure no other processes interfere
