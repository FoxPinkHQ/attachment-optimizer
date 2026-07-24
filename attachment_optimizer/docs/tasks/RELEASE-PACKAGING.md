# Release Packaging Review

## Status: PROPOSAL

---

## Objective

Review and finalize all packaging artifacts for the v1.0 release of
`foxpink_attachment_optimizer`. **No code changes** — only metadata,
documentation, and packaging files.

---

## Scope

### 1. `__manifest__.py` — metadata audit

| Field | Current | Required |
|-------|---------|----------|
| `name` | `FoxPink Attachment Optimizer` | OK |
| `version` | `18.0.1.0.0` | OK (follows Odoo versioning: odoo.major.mini.patch) |
| `category` | `Storage` | OK |
| `summary` | Present | OK |
| `description` | Present | OK |
| `author` | `FoxPink` | OK |
| `website` | `https://foxpink.dev` | OK |
| `license` | `LGPL-3` | OK |
| `depends` | `base`, `web` | OK |
| `data` | 6 view/security files | OK |
| `installable` | `True` | OK |
| `application` | `False` | OK (module, not app) |
| `auto_install` | `False` | OK |

**Action**: Verify no missing keys. Add `icon` path if icon exists.

### 2. `README.md`

Generate from `docs/release/templates/README.md` following MODULE_STANDARDS.md:

- Version line: `<manifest version>`
- License: LGPL-3
- Publisher: FoxPink
- Maintained for Odoo 18.0 (MVP scope)
- Screenshots: None yet (MVP has no UI screenshots beyond standard views)
- Description: module overview from SPEC.md

**Action**: Create `README.md` at module root.

### 3. `LICENSE`

Copy from `docs/release/templates/LICENSE` (LGPL-3 verbatim). Place at
module root. Include `!/LICENSE` in `.gitignore` if publishing separately.

**Action**: Verify LICENSE is present and correct.

### 4. Module icon

Odoo convention: `static/description/icon.png` (128×128 or 256×256).

Options:
- Generate a simple SVG/PNG (FoxPink brand color + storage icon)
- Use a placeholder generic icon

**Decision needed**: Create icon or leave generic?

### 5. `static/description/index.html`

Optional for Odoo module store. Can be auto-generated or hand-written.

**Decision needed**: Create description page or skip for MVP?

### 6. Changelog

Document in `docs/release/CHANGELOG.md`:

```
v1.0.0 (2026-07-24)
  - Initial release
  - FPAO-001: Storage mapping model + lifecycle
  - FPAO-002: S3 bridge with retry + checksum verification
  - FPAO-003: Migration pipeline (analyze, queue, upload, verify, finalize)
  - FPAO-004: Read flow via ir.binary extension (S3 source)
  - FPAO-005: Dashboard (kanban overview, migration trigger, retry)
  - FPAO-006: Audit log (immutable, same-transaction)
  - FPAO-007: 82 tests, security verification, uninstall validation
```

**Action**: Create `docs/release/CHANGELOG.md`.

### 7. `.gitignore`

Verify the repo-level `.gitignore` (if publishing to GitHub):

```gitignore
/*
!/foxpink_attachment_optimizer
!/README.md
!/LICENSE
```

**Action**: Create `.gitignore` if needed for standalone publishing.

---

## Out of Scope

| Item | Reason |
|------|--------|
| Odoo store submission | Not applicable — private/internal module |
| Signed release tag | Future concern |
| Release ZIP packaging | Done manually or via CI |
| PyPI / pip packaging | Odoo modules are not pip packages |
| Multi-version packaging | Odoo 18.0 only for MVP — IMPLEMENTATION_PLAN §2 |

---

## Acceptance Criteria

1. `__manifest__.py` passes Odoo module validation (all required keys)
2. `README.md` follows template, no drift from MODULE_STANDARDS
3. `LICENSE` is verbatim LGPL-3
4. `static/description/icon.png` exists (if decision = create)
5. `docs/release/CHANGELOG.md` documents all FPAO deliverables
6. All files compile after any metadata changes

---

## Decisions Needed Before Freeze

### D1: Module icon

- Option A: Generate 128×128 PNG (FoxPink brand, storage theme)
- Option B: Skip icon, rely on Odoo default

### D2: Description page

- Option A: Create `static/description/index.html`
- Option B: Skip for MVP

---

## Files to Create / Modify

| File | Action |
|------|--------|
| `README.md` | Create from template |
| `LICENSE` | Copy verbatim LGPL-3 |
| `static/description/icon.png` | Create (if D1=A) |
| `static/description/index.html` | Create (if D2=A) |
| `docs/release/CHANGELOG.md` | Create |
| `.gitignore` | Create (if standalone publishing) |

## Files to Verify (no changes expected)

| File | Check |
|------|-------|
| `__manifest__.py` | All required keys present |
| All `*.py` | Still compile after updates |
