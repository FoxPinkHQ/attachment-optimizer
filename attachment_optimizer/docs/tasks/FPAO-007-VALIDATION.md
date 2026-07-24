# FPAO-007 — Validation

## Status: PROPOSAL (not frozen, not implemented)

---

## Objective

Final integration validation before release. **Zero new features, zero
architecture changes, zero pipeline changes**. This phase produces a
verification report documenting that all frozen requirements are met.

---

## Scope

### 1. Integration Verification

Verify end-to-end flow across all 6 FPAO components using a single
realistic scenario:

```
1. Create attachment with binary data
2. Run analyze_candidates() → confirms candidate
3. Create migration operation → state = queued
4. Process queue → upload → verify → finalize
5. Read attachment via _get_stream_for() → serves from S3
6. Check store_fname unchanged
7. Check audit log contains all events
```

**Expected deliverables**: A single integration test (`test_integration.py`)
that exercises all 6 components without mocking S3 (use moto).

### 2. Cross-Version Compilation

Verify Python syntax compatibility for Odoo 17 by confirming:

- No walrus operator (`:=`)
- No `match`/`case` statements
- No `except*` syntax
- `from __future__ import annotations` not present (or tested)

**Expected deliverables**: Syntax scan report. Fix any incompatibility in
a separate R1 (if found).

### 3. Security Verification

Verify each security boundary with a dedicated test:

| Test | What it proves |
|------|----------------|
| Non-manager cannot read storage mapping | Group isolation |
| Non-manager cannot read migration operation | Group isolation |
| Non-manager cannot read audit log | Group isolation |
| Non-manager cannot see any FoxPink menu | Menu ACL works |
| Audit record cannot be written or deleted | Model-level immutability |
| `_get_stream_for` respects attachment ACL | Read flow security |
| S3 credentials not exposed in logs | No credential leak |

**Expected deliverables**: Extended `test_security.py`.

### 4. Clean Uninstall Verification

Verify that uninstalling the module does not:

- Delete `ir.attachment` records (ondelete cascade on mapping)
- Leave orphan `ir.config_parameter` entries
- Leave dangling SQL tables
- Break existing attachment access (filestore should still work)

**Note**: `foxpink.storage.mapping` has `ondelete='cascade'` on
`attachment_id`, so mappings are auto-cleaned when attachment is deleted.
But uninstall should not delete attachments themselves.

**Expected deliverables**: `test_uninstall.py`.

### 5. Full Regression Run

Run all existing tests under a single suite and report:

| Component | Test file | Count |
|-----------|-----------|-------|
| Storage Mapping | `test_storage_mapping.py` | 15 |
| S3 Bridge | `test_s3_bridge.py` | 11 |
| Migration Pipeline | `test_migration_service.py` | 13 |
| Read Flow | `test_read_flow.py` | 11 |
| Dashboard | `test_dashboard.py` | 8 |
| Audit Log | `test_audit_log.py` | 10 |
| Integration | `test_integration.py` | 1 |
| Security | `test_security.py` | 7 |
| Uninstall | `test_uninstall.py` | 4 |
| **Total** | | **80** |

**Expected deliverables**: Test run log + summary.

### 6. Release Checklist

Document the release gate:

| Item | Requirement |
|------|-------------|
| Module version | `__manifest__.py` version bumped to `18.0.1.0.0` |
| All tests pass | 80/80 green |
| Python compiles | All `.py` files pass `py_compile` |
| No hardcoded secrets | `foxpink_s3.*` params are config parameters, not code |
| Uninstall safe | No data loss |
| Odoo 17 compatible | No syntax incompatibility |
| LICENSE file | LGPL-3 in root (if publishing separately) |
| README | Module documentation updated |

---

## Out of Scope (explicitly excluded)

| Feature | Reason |
|---------|--------|
| Odoo 14/15/16/19 compatibility | Not in scope — see IMPLEMENTATION_PLAN.md |
| Odoo 17 runtime testing | Syntax check only (no Odoo 17 env) |
| Performance benchmarks | Not in MVP spec |
| Load testing | Not in MVP spec |
| Browser/UI testing | Not in MVP spec |
| i18n / translation check | Not in MVP spec |
| Security penetration test | Out of scope for this phase |
| Documentation generation | README update only if needed |

---

## Files to Create

```
tests/test_integration.py
tests/test_security.py
tests/test_uninstall.py
```

## Files to Run (no changes)

```
tests/test_storage_mapping.py
tests/test_s3_bridge.py
tests/test_migration_service.py
tests/test_read_flow.py
tests/test_dashboard.py
tests/test_audit_log.py
```

---

## Acceptance Criteria

1. Integration test: end-to-end flow passes without mocking internal steps
2. Syntax check: all files parse under Python 3.10 (Odoo 17 baseline)
3. Security: all 7 security tests pass
4. Uninstall: module removes cleanly without data loss
5. Regression: 80/80 tests green
6. Release checklist: all items verified

---

## Task Breakdown

| Step | What | Deliverable |
|------|------|-------------|
| 1 | Write integration test | `tests/test_integration.py` |
| 2 | Syntax scan for Odoo 17 | Report + any fixes |
| 3 | Write security tests | `tests/test_security.py` |
| 4 | Write uninstall test | `tests/test_uninstall.py` |
| 5 | Run full regression | Test log + summary |
| 6 | Verify release checklist | `RELEASE_CHECKLIST.md` or inline report |

---

## Dependencies

| ID | Status |
|----|--------|
| FPAO-001 Storage Mapping | FROZEN |
| FPAO-002 S3 Bridge | FROZEN |
| FPAO-003 Migration Pipeline | FROZEN |
| FPAO-004 Read Flow | FROZEN |
| FPAO-005 Dashboard | FROZEN |
| FPAO-006 Audit | FROZEN |

---

## Open Questions (to resolve before freeze)

1. **Integration test S3 strategy**: Use moto `mock_aws()` (same as existing
   S3 Bridge tests) → yes, consistent.

2. **Uninstall test approach**: Test uninstall by removing module from
   `installed_modules` via SQL, or rely on standard Odoo test uninstall?
   Recommend: test that the module can be cleanly uninstalled via
   `modules.uninstall` API.

3. **Release checklist format**: Capture as a new file or as part of the
   validation report? Recommend: final report in
   `docs/release/RELEASE_VALIDATION.md`.
