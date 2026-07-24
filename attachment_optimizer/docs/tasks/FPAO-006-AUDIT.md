# FPAO-006 — Audit

## Status: FROZEN (decisions locked, ready to implement)

---

## Objective

Add an audit log layer that records every migration action for traceability,
support/debug, and customer confidence. The audit is a **passive recorder** —
it never modifies behavior, only observes and persists.

---

## Frozen Decisions

### Decision 1 — Transaction boundary

**Same-transaction logging.** Audit records live or die with the operation.
No savepoint, no external log. MVP simplicity > append-only guarantees.

### Decision 2 — Dashboard "Create Migration Queue" action

**YES — logged.** Separate action type `migration_queue_created` to distinguish
the trigger from individual upload/finalize steps.

### Decision 3 — Menu placement

**Visible menu** under Storage Optimization, named "Audit Logs". ACL-gated
(read-only for manager, invisible for others).

---

## Scope

### 1. Audit Model — `foxpink.audit.log`

| Field | Type | Purpose |
|-------|------|---------|
| `user_id` | Many2one `res.users` | Who triggered the action |
| `action` | Selection | `analyze`, `migration_queue_created`, `queue`, `upload`, `verify`, `finalize`, `retry`, `cancel` |
| `attachment_id` | Many2one `ir.attachment` | Which attachment was affected |
| `operation_id` | Many2one `foxpink.migration.operation` | Link to operation (if applicable) |
| `mapping_id` | Many2one `foxpink.storage.mapping` | Link to mapping (if applicable) |
| `result` | Selection | `success`, `failure` |
| `error_message` | Text | Error details if failure |
| `create_date` | Datetime (auto) | When the action occurred |

#### Immutability rule

The audit model is **read-only at application layer**. No edit, no delete,
no unlink for any user. Only `create()` via logging hooks.

### 2. Logging Hooks

Hooks are placed in `MigrationService` methods. Each hook is a single
`self.env['foxpink.audit.log'].create({...})` call, no branching logic.

| Method | Action logged |
|--------|---------------|
| `analyze_candidates()` | `analyze` (summary: N candidates found) |
| `action_analyze_and_queue()` (Dashboard) | `migration_queue_created` |
| `create_migration_operations()` | `queue` (per attachment) |
| `_process_single()` → upload start | `upload` |
| `_process_single()` → verify | `verify` |
| `_process_single()` → finalize | `finalize` |
| `action_retry()` | `retry` |
| `action_cancel()` | `cancel` |

### 3. Transaction

Same-transaction logging. Audit records are never rolled back independently.

---

## Out of Scope (explicitly excluded)

| Feature | Reason |
|---------|--------|
| Security audit system | Not a security tool — only tracks storage migration actions |
| Compliance module | No regulatory framework targeted |
| Log viewer / advanced filtering | Odoo tree view with search is sufficient for MVP |
| SIEM / external integration | No export, webhook, or syslog for MVP |
| Immutable / blockchain log | Tamper-proofing is future concern, not MVP |
| Retroactive audit | Does not backfill logs for pre-existing mappings |
| Retention / cleanup policy | Manual deletion via Odoo is fine |

---

## Files to Create / Modify

### New files

```
models/audit_log.py
views/audit_log_views.xml
```

### Modified files

| File | Change |
|------|--------|
| `models/__init__.py` | Add `from . import audit_log` |
| `services/migration_service.py` | Add `_log_audit()` calls in each method |
| `models/migration_operation.py` | Add audit log to `action_analyze_and_queue()`, `action_retry()`, `action_cancel()` |
| `security/ir.model.access.csv` | Add read-only access for manager group |
| `__manifest__.py` | Add `views/audit_log_views.xml` to data |

---

## Acceptance Criteria

1. Every migration action produces a `foxpink.audit.log` record
2. Log records are visible to Storage Optimization Manager only (read-only)
3. No user can edit, delete, or unlink audit records
4. Log records contain: user, action, attachment id, timestamp, result
5. Failed operations include error message in the audit log
6. Tree view allows filtering by action, result, date, user
7. "Create Migration Queue" (Dashboard) produces `migration_queue_created` log
8. No performance regression — log creation is a single `create()` per action

---

## Test Plan

### Unit tests (`tests/test_audit_log.py`)

| Test | Scenario |
|------|----------|
| 01 | `analyze` logs created with correct action field |
| 02 | `migration_queue_created` log from Dashboard action |
| 03 | `queue` logs created with attachment reference |
| 04 | `upload`+`verify`+`finalize` logs created through pipeline |
| 05 | `retry` + `cancel` logs created with user reference |
| 06 | Failed operation logs include error message |
| 07 | Manager can read audit log |
| 08 | Non-manager cannot read audit log |
| 09 | Audit record cannot be written or deleted |

---

## Task Breakdown

| Step | File | What |
|------|------|------|
| 1 | `models/audit_log.py` | Define `foxpink.audit.log` with fields + `_log()` helper + `check_access_rights` override to block write/unlink |
| 2 | `models/__init__.py` | Add import |
| 3 | `services/migration_service.py` | Add `_log_audit()` and call at each pipeline stage |
| 4 | `models/migration_operation.py` | Add audit logging to `action_analyze_and_queue()`, `action_retry()`, `action_cancel()` |
| 5 | `security/ir.model.access.csv` | Add read-only ACL for manager group |
| 6 | `views/audit_log_views.xml` | Tree + search view + action + menu |
| 7 | `__manifest__.py` | Register new view file |
| 8 | `tests/test_audit_log.py` | All 9 tests |

---

## Dependencies

| ID | Status |
|----|--------|
| FPAO-001 Storage Mapping | FROZEN |
| FPAO-002 S3 Bridge | FROZEN |
| FPAO-003 Migration Pipeline | FROZEN |
| FPAO-004 Read Flow | FROZEN |
| FPAO-005 Dashboard | FROZEN |
