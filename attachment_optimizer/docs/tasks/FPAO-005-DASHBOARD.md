# FPAO-005 — Dashboard

## Status: PROPOSAL (not frozen, not implemented)

---

## Objective

Build a UI dashboard for Storage Optimization Manager to monitor externalization
state and trigger migration operations. **No new business logic** — the dashboard
is a read/write interface on existing contracts (`foxpink.storage.mapping`,
`foxpink.migration.operation`, `MigrationService`).

---

## Scope

### 1. Storage Overview — top-level stats

| Metric | Source |
|--------|--------|
| Total attachments | `ir.attachment` search count |
| Externalized | `foxpink.storage.mapping` count with `status = 'finalized'` |
| Pending migrations | `foxpink.migration.operation` count with `status = 'pending'` |
| Failed operations | `foxpink.migration.operation` count with `status = 'failed'` |

### 2. Migration Queue — list of `foxpink.migration.operation` records

- Display: attachment name, status, error message (if failed), create date
- Buttons: **Retry Failed** (calls `MigrationService.retry_failed`)
- Only visible when queue is non-empty

### 3. Migration Trigger — action button

- **Analyze & Migrate** button
- Calls `MigrationService.analyze_candidates()` then `MigrationService.create_migration_operations()`
- Shows feedback (toast / reload)
- Only enabled for Storage Optimization Manager

### 4. Security

- Menu and views gated by `foxpink.group_storage_optimization_manager`
- No new permission groups

---

## Out of Scope (explicitly excluded)

| Feature | Reason |
|---------|--------|
| S3 browser / object listing | Not in ARCHITECTURE.md — crosses into infrastructure UI |
| Direct S3 upload/delete | Mapping lifecycle is automated; manual S3 ops bypass integrity checks |
| Manual mapping editing | Mapping is created/updated only through migration pipeline |
| Cleanup UI | Not part of MVP — deferred to FPAO-006 (Audit) |
| Compression UI | Not in SPEC.md |
| Advanced analytics / charts | Not in MVP requirement |
| Storage size calculations | Requires `ir.attachment` `file_size` aggregation — not available for all stores |

---

## Files to Create

```
views/dashboard_views.xml          — action + menu + tree/form views
security/ir.model.access.csv       — (extend existing file)
wizards/                           — (only if needed for trigger feedback)
```

Files expected to **remain unchanged**:

| File | Reason |
|------|--------|
| `models/*` | No new models |
| `services/*` | No new services |
| `tests/test_dashboard.py` | Ui-level tests minimal; core logic already tested under FPAO-001/002/003 |

---

## Dependencies

| ID | Status |
|----|--------|
| FPAO-001 Storage Mapping | FROZEN |
| FPAO-002 S3 Bridge | FROZEN |
| FPAO-003 Migration Pipeline | FROZEN |
| FPAO-004 Read Flow | FROZEN |

---

## Acceptance Criteria

1. Storage Optimization Manager sees dashboard with correct counts
2. Non-manager sees no menu item
3. Migration queue renders active/failed operations
4. "Analyze & Migrate" triggers pipeline and updates counts
5. "Retry Failed" triggers retry on failed operations
6. All actions use existing service methods — no new SQL or S3 calls

---

## Test Plan

Minimal — core logic already has 15 (FPAO-001) + 11 (FPAO-002) + 13 (FPAO-003) + 11 (FPAO-004) = 50 tests.

Dashboard tests:

- `test_dashboard_menu_visible_to_manager`
- `test_dashboard_menu_hidden_from_other_users`
- `test_analyze_migrate_button_triggers_service`
- `test_retry_failed_button_triggers_service`

Integration tests (optional, can defer):

- `test_dashboard_counts_match_database`

---

## Task Breakdown

| Step | File | What |
|------|------|------|
| 1 | `views/dashboard_views.xml` | Action + menu + tree view for `foxpink.migration.operation` + kanban/summary view |
| 2 | `security/ir.model.access.csv` | Ensure `foxpink.migration.operation` read for manager group |
| 3 | `tests/test_dashboard.py` | Menu visibility + trigger tests |
| 4 | `__manifest__.py` | Add view file dependency |

---

## Open Questions (to resolve before freeze)

1. **Feedback mechanism**: After "Analyze & Migrate", reload the page? Odoo client action with notification?
   → Recommend: simple `action_reload()` via button on `ir.actions.server` or client action with `{type: 'ir.actions.client', tag: 'reload'}`.

2. **Where to place the trigger**: A button in a form view? A dedicated menu item with server action?
   → Recommend: button in a kanban "dashboard" view.

3. **Zero-state UX**: When no operations exist, show empty queue or hide the queue section entirely?
   → Recommend: hide with `invisible` via `context` or optional field check.

---

## Not Yet — Deferred to Future Phases

- Audit log viewer (FPAO-006)
- Pre-migration validation wizard (FPAO-007)
- Storage size chart
- Per-attachment externalization status in attachment list view
