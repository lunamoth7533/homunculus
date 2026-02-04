# Later Ideas

These recommendations were deferred for future consideration.

## Deferred Items

### 11. Web Dashboard
**Impact:** Low | **Effort:** High

View status, gaps, proposals in browser. Nice but CLI works fine for now.

**Implementation notes:**
- Could use Flask/FastAPI + simple HTML
- Or generate static HTML reports
- Consider TUI (terminal UI) as lighter alternative

### 12. Integration Tests
**Impact:** Medium | **Effort:** Medium

Current tests are unit tests. Add end-to-end tests for the full workflow.

**Implementation notes:**
- Test full gap detection → synthesis → approval → installation flow
- Test rollback scenarios
- Test meta-evolution cycle
- Use temporary databases for isolation

### 19. Capability Marketplace
**Impact:** Low | **Effort:** High

Share capabilities between users publicly.

**Implementation notes:**
- Would need hosting infrastructure
- Versioning and compatibility concerns
- Security review process for shared capabilities
- Could integrate with GitHub as storage backend

---

*Last updated: 2026-02-03*
