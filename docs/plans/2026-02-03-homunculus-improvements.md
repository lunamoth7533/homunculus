# Homunculus Improvement Recommendations

**Date:** 2026-02-03
**Status:** Brainstormed

## Completed Fixes

1. ✅ Fixed hardcoded `~/homunculus` paths in `commands/homunculus.md` → now uses `${CLAUDE_PLUGIN_ROOT}`
2. ✅ Added `PreToolUse` hook to `hooks/hooks.json` for better observation coverage
3. ✅ Updated README directory structure to match actual database location
4. ✅ Updated README installation instructions to use plugin marketplace
5. ✅ Updated architecture diagram to show all three hooks

---

## Prioritized Recommendations

### Priority 1: Critical / High Impact

| # | Recommendation | Impact | Effort | Rationale |
|---|----------------|--------|--------|-----------|
| 1 | **Add Notification hook** | High | Low | The `observe.sh` handles notifications but `hooks.json` doesn't configure it. Add `"Notification"` hook to capture Claude's internal notifications (errors, warnings). |
| 2 | **Add error handling to process_observation.py** | High | Medium | If the Python script fails silently, observations are lost. Add logging and graceful degradation. |
| 3 | **Create mcp-server synthesis template** | High | Medium | The `mcp-server.yaml` template exists but is probably incomplete. MCP servers are powerful for integration gaps. |
| 4 | **Add observation archival cron/hook** | High | Medium | Config says `archive_after_days: 7` but no archival mechanism exists. Observations will grow unbounded. |
| 5 | **Add session start hook** | High | Low | Currently only observes Stop, PreToolUse, PostToolUse. Add a hook or mechanism to capture session start for proper session tracking. |

### Priority 2: Important / Medium Impact

| # | Recommendation | Impact | Effort | Rationale |
|---|----------------|--------|--------|-----------|
| 6 | **Add LLM-powered synthesis option** | Medium | High | Current synthesis uses templates only. Add optional Claude API integration for smarter capability generation (config already has `synthesis_model: sonnet`). |
| 7 | **Add periodic detection trigger** | Medium | Medium | Config has `periodic_minutes: 30` but no mechanism implements it. Add a background process or hook-triggered timer. |
| 8 | **Add capability usage tracking** | Medium | Medium | The `capability_usage` table exists but nothing populates it. Track when evolved skills are invoked. |
| 9 | **Add export/import for capabilities** | Medium | Medium | Allow sharing evolved capabilities between users or projects. |
| 10 | **Add dry-run mode for installations** | Medium | Low | Show what files would be created without actually creating them. |

### Priority 3: Nice to Have / Lower Impact

| # | Recommendation | Impact | Effort | Rationale |
|---|----------------|--------|--------|-----------|
| 11 | **Add web dashboard** | Low | High | View status, gaps, proposals in browser. Nice but CLI works fine. |
| 12 | **Add integration tests** | Medium | Medium | Current tests are unit tests. Add end-to-end tests for the full workflow. |
| 13 | **Add gap deduplication across sessions** | Low | Medium | Similar gaps from different sessions could be merged. |
| 14 | **Add confidence decay** | Low | Low | Old unaddressed gaps should have declining confidence. |
| 15 | **Add project-scoped databases** | Low | High | Currently global. Allow per-project homunculus instances. |

### Priority 4: Future Enhancements

| # | Recommendation | Impact | Effort | Rationale |
|---|----------------|--------|--------|-----------|
| 16 | **Add capability dependencies** | Low | High | Some capabilities might depend on others. Track and manage dependencies. |
| 17 | **Add A/B testing for templates** | Low | High | Test multiple template variations to find best performers. |
| 18 | **Add natural language gap reporting** | Medium | High | Let users describe gaps in plain English instead of waiting for detection. |
| 19 | **Add capability marketplace** | Low | High | Share capabilities between users publicly. |
| 20 | **Add Claude conversation context** | Medium | High | Currently only sees tool inputs. Richer context would improve detection. |

---

## Detailed Implementation Notes

### 1. Add Notification Hook

```json
// Add to hooks/hooks.json
"Notification": [
  {
    "matcher": "*",
    "hooks": [
      {
        "type": "command",
        "command": "${CLAUDE_PLUGIN_ROOT}/scripts/observe.sh notification"
      }
    ]
  }
]
```

### 4. Add Observation Archival

Create `scripts/archive_observations.py`:
- Move observations older than N days to `observations/archive/YYYY-MM-DD.jsonl`
- Update observation `processed` flag
- Run via cron or at session end

### 6. LLM-Powered Synthesis

The infrastructure exists:
- `config.yaml` has `synthesis_model: sonnet`
- Templates have `synthesis_prompt` field

Implementation:
- Add Claude API call in `synthesizer.py`
- Use template's `synthesis_prompt` as the prompt
- Parse structured output into capability files

### 8. Capability Usage Tracking

Add hook that:
- Detects when a skill in `evolved/skills/` is loaded
- Records to `capability_usage` table
- Enables meta-evolution to see which capabilities are actually used

---

## Metrics for Success

Track these to measure improvement effectiveness:

1. **Gap-to-Resolution Rate**: % of detected gaps that become approved capabilities
2. **Capability Retention Rate**: % of installed capabilities not rolled back
3. **Time-to-Resolution**: Days from gap detection to capability installation
4. **Meta-Evolution Impact**: Improvement in detector/template performance over time
5. **User Satisfaction**: Approval rate trending upward

---

## Next Steps

1. Implement Priority 1 items (estimated: 4-6 hours)
2. Add integration test suite
3. Dogfood the system for 1 week
4. Review meta-evolution insights
5. Prioritize remaining items based on real usage patterns
