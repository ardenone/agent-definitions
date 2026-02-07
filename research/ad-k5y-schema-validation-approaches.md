# Research: Agent Config Schema Validation Approaches

**Date:** 2026-02-07
**Original Task:** ad-3hn - Validate agent config schema compatibility with runners
**Research Bead:** ad-k5y

## Context

The original task (ad-3hn) requires validating agent configuration JSON files against the botburrow-agents runner requirements. This is a **cross-repo task** involving:
- `agent-definitions` (this repo) - contains agent config JSON files
- `botburrow-agents` - contains runner implementation and schema expectations

The worker became stuck, leading to alternative approaches being proposed.

## Approaches Comparison

### Approach 1: Full Comprehensive Validation (Original ad-3hn Scope)

**Description:** Complete end-to-end validation of all agent configs against runner requirements.

**Steps:**
1. Review runner config parser in `botburrow-agents/src/runner/config.py`
2. Validate all agent JSONs against schema
3. Test runners can load each agent config from R2
4. Check required fields present in all configs
5. Verify tool definitions match MCP server capabilities
6. Test personality prompts don't exceed token limits
7. Validate budget limits are reasonable
8. Add schema validation to CI/CD

**Pros:**
- Comprehensive coverage
- Catches all potential issues
- CI/CD integration prevents future regressions
- Validates runtime behavior (R2 loading, token limits)

**Cons:**
- High complexity (cross-repo, R2 access, runtime testing)
- Time-consuming (requires multiple repos coordination)
- May require infrastructure setup (R2 access, CI/CD pipelines)
- Worker got stuck - indicates technical blockers

**Estimated Effort:** 6-10 hours

---

### Approach 2: Simplified Static Validation (Simplified Scope)

**Description:** Focus on static schema validation only, without runtime testing.

**Steps:**
1. Extract schema expectations from `botburrow-agents/src/runner/config.py`
2. Create JSON Schema definition
3. Validate all agent JSONs against schema locally
4. Report mismatches
5. Document findings

**Pros:**
- Faster completion
- No infrastructure dependencies
- Can be done entirely in this repo
- Clear deliverable (validation report)

**Cons:**
- Doesn't validate runtime behavior (R2 loading, token limits)
- Doesn't add CI/CD protection
- May miss runtime-only issues

**Estimated Effort:** 2-4 hours

---

### Approach 3: Documentation-First Approach

**Description:** Document the schema requirements and create a checklist, leaving validation to human reviewers.

**Steps:**
1. Review runner code to extract schema requirements
2. Create clear schema documentation
3. Create validation checklist for humans
4. Document each agent config's conformance status

**Pros:**
- Fastest to complete
- Creates reusable documentation
- Enables human review
- No code changes required

**Cons:**
- Relies on human execution
- No automated validation
- Doesn't prevent future issues
- Manual overhead for humans

**Estimated Effort:** 1-2 hours

---

### Approach 4: Incremental Validation (Hybrid)

**Description:** Start with static validation, add runtime testing incrementally.

**Steps:**
1. Phase 1: Static schema validation (Approach 2)
2. Document findings and create issues for runtime testing
3. Phase 2: Add CI/CD validation as separate follow-up tasks

**Pros:**
- Faster initial value delivery
- Breaks complex task into manageable pieces
- Creates clear follow-up work
- Progress visible early

**Cons:**
- Requires task breakdown and coordination
- Multiple phases need tracking
- Follow-up work may not get done

**Estimated Effort:** 2-4 hours (Phase 1), 4-6 hours (Phase 2)

---

## Recommendation Matrix

| Approach | Speed | Completeness | Automation | Risk | Recommended |
|----------|-------|--------------|------------|------|-------------|
| Full Comprehensive | Low | High | High | High (worker stuck) | No |
| Simplified Static | Medium | Medium | High | Low | **Yes** |
| Documentation-First | High | Low | None | Medium | Maybe |
| Incremental | Medium | High | Medium | Low | **Yes** |

## Technical Blockers Identified (from worker getting stuck)

1. **Cross-repo access** - Worker may not have access to `botburrow-agents` repo
2. **R2 infrastructure** - Testing config loading from R2 requires credentials/infrastructure
3. **CI/CD integration** - May require repo admin permissions
4. **Complex coordination** - Multiple repos and systems makes single-pass execution difficult

## Decision Framework

**Choose Approach 2 (Simplified Static) if:**
- You want quick validation results
- Runtime issues can be handled separately
- Infrastructure access is limited
- CI/CD can be added later

**Choose Approach 3 (Documentation-First) if:**
- Human review is preferred
- Automation is not critical
- Speed is the priority
- You want to enable manual validation processes

**Choose Approach 4 (Incremental) if:**
- You want both speed and completeness
- Follow-up work is acceptable
- Task coordination is manageable
- You value phased delivery

**Choose Approach 1 (Full) only if:**
- All blockers can be resolved
- Cross-repo access is available
- Infrastructure is ready
- Time is not a constraint

## Next Steps (for human decision)

1. Review this comparison document
2. Select preferred approach based on priorities and constraints
3. If Approach 2 or 4 is selected, create new implementation bead
4. Close this research bead (ad-k5y) and any obsolete alternative beads (ad-2fy, ad-2x2)
5. Proceed with implementation

---

**Generated by:** Worker claude-code-glm-47-bravo
**Research Bead:** ad-k5y
**Status:** Awaiting human decision
