# Attachment Optimizer

> **Replicate and serve Odoo attachments from S3-compatible storage with rollback safety.**

![Attachment Optimizer](attachment_optimizer/static/description/preview.png)

**Version:** 15.0.1.0.5 -- **License:** LGPL-3 -- **Publisher:** FoxPink -- Maintained for **Odoo 14.0-19.0** (one validated build per series)

---

## Why use Attachment Optimizer?

Attachment Optimizer analyzes Odoo attachment storage and replicates selected binary attachments to S3-compatible object storage without changing existing business workflows. Each migration is verifiable, auditable, and reversible because the original filestore data is preserved.

| Problem | Solution |
|--------|----------|
| Need an external object copy | Replicate attachments to S3-compatible storage |
| Need verified object storage | Validate every uploaded object with SHA-256 |
| Need transparent access | Serve finalized mappings through Odoo with filestore fallback |
| Migration risk | SHA-256 verification |
| Rollback concern | Original filestore preserved |

- **Replicate attachments safely** — copy → verify → serve; original never deleted
- **Preserve access continuity** — attachments remain accessible during migration
- **Rollback anytime** — original filestore remains untouched

### Typical use cases

- ERP with millions of attachments
- Manufacturing systems storing PDFs
- Accounting databases with invoices
- Document-heavy Odoo deployments

> **Add verified S3-compatible attachment storage without changing business workflows.**

---

## How It Works

```
Analyze
    │
Queue
    │
Claim
    │
Upload
    │
Verify
    │
Finalize
     ▲
     │
Retry (idempotent)
```

---

## Architecture

```text
               Dashboard
                   │
        ┌──────────┴──────────┐
        │                     │
Migration Service      Health Engine
        │
   Queue Engine
        │
   Recovery Engine
        │
     S3 Bridge
        │
 Amazon S3 / MinIO / Compatible
```

---

## Features

### Storage
- **Analyze attachment usage** — find large, old, unused attachments
- **Detect migration candidates** — filter by size, age, model, access frequency
- **Track migrated volume** — measure attachments replicated to object storage

### Migration
- **Queue-based migration** — analyze → queue → claim → upload → verify → finalize
- **SHA-256 verification** — every file checksummed after upload
- **Retry failed uploads safely** — idempotent, no duplicates

### Safety
- **Original filestore preserved** — no data deleted during migration
- **Immutable audit logs** — every action logged with user, timestamp, result
- **Multi-company isolation** — record rules enforce data isolation

### Monitoring
- **Dashboard** — KPI cards (eligible, verified S3 copy, failed) with live progress and a contextual Pro upgrade moment
- **Health Checks** — 17 automated checks (DB, S3, queue, config, runtime)
- **Recovery Engine** — 5 rules auto-recover interrupted uploads

---

## Safety First

```
✓ Original filestore never deleted — retained for rollback safety
✓ Rollback always possible — original filestore remains untouched
✓ SHA-256 verification — integrity guaranteed on every file
✓ Immutable audit trail — every action logged with user, timestamp, result
✓ Retry is idempotent — retries never create duplicates
```

---

## Screenshots

![Storage Optimization Dashboard](attachment_optimizer/static/description/screenshot_09_dashboard.png)
![Storage Mappings List](attachment_optimizer/static/description/screenshot_01_storage_mapping_list.png)
![Storage Mapping Form](attachment_optimizer/static/description/screenshot_02_storage_mapping_form.png)
![Migration Operations List](attachment_optimizer/static/description/screenshot_03_migration_operation_list.png)
![Migration Operation Form](attachment_optimizer/static/description/screenshot_04_migration_operation_form.png)
![Audit Log List](attachment_optimizer/static/description/screenshot_05_audit_log_list.png)
![Storage Mappings Search](attachment_optimizer/static/description/screenshot_06_storage_mapping_search.png)
![Settings](attachment_optimizer/static/description/screenshot_07_settings.png)
![Access Rights / Groups](attachment_optimizer/static/description/screenshot_08_access_rights.png)

---

## Installation

**Option 1 — Odoo Apps Store:** Download the ZIP for your Odoo version from the [Releases](https://github.com/FoxPinkHQ/attachment-optimizer/releases) page, unzip into your addons directory, restart Odoo, and install via Apps.

**Option 2 — Git:**

```bash
git clone -b 17.0 https://github.com/FoxPinkHQ/attachment-optimizer addons/attachment_optimizer
```

Before installing the module, install the required Python dependency in the same environment that runs Odoo:

```bash
pip3 install boto3
```

For Docker deployments, add `boto3` to the Odoo image instead of installing it manually inside a running container. After adding the module, restart Odoo, activate Developer Mode, go to **Apps → Update Apps List**, search for **Attachment Optimizer**, and install.

> **Deployment note:** This module requires Python code and the external `boto3` package. It is intended for Odoo.sh and on-premise/Docker deployments where server dependencies can be installed; it is not compatible with Odoo Online.

---

## Getting Started

1. **Configure S3** — Settings → Attachment Optimizer: endpoint, region, access key, secret key, bucket
2. **Test Connection** — verify S3 reachability
3. **Analyze Storage** — Dashboard → Analyze → find migration candidates
4. **Create Queue** — review candidates → Create Migration Queue
5. **Process Queue** — click Process Queue → monitor live progress
6. **Monitor Dashboard** — confirm migrated count, migrated volume, and failed count

---

## Configuration

1. **S3 Credentials:** Settings → Attachment Optimizer — enter endpoint URL, region, access key, secret key, bucket name
2. **Test Connection** — click "Test Connection" to verify S3 reachability
3. **Auto-Recovery:** optionally enable auto-recovery in the same settings section

> **Recommended:** Use the Settings page instead of editing System Parameters manually.

---

## Security

- **Role-based access** — Storage Optimization Manager group controls dashboard/settings
- **Multi-company isolation** — record rules enforce data isolation
- **Immutable audit log** — every action logged with user, timestamp, result
- **No credential is stored in audit logs**

---

## Current Limitations

- Single S3 bucket per installation
- No automatic filestore cleanup after finalization
- Migration queue is started manually
- Horizontal worker scaling is not currently supported

---

## Free Edition and Pro

The Free Edition provides the complete verified migration foundation without trial limits. **Attachment Optimizer Pro is now available** for teams that need automated routing, measurable filestore reclamation, and controlled recovery.

### Attachment Optimizer Pro — available now

- **Safe local cleanup** — reclaim filestore space after SHA-256 verification, retention, and confirmation
- **Automatic storage routing** — route new attachments by model, MIME type, size, company, priority, and bucket
- **One-click restore** — restore selected mappings or complete batches to the Odoo filestore
- **Scheduled lifecycle policies** — automate migrate, archive, cleanup, and restore actions when due
- **Multi-bucket and multi-company routing** — isolate storage profiles and rules by company
- **Background processing** — atomic worker claims, configurable batch limits, scheduled processing, and retry safety
- **Storage analytics** — report attachment volume, migration progress, reclaimed space, and failures
- **Advanced security** — manager-only credentials, IAM provider support, server-side encryption settings, and multi-company rules
- **Operational alerts** — notify administrators about failed queues, stuck operations, and verification failures

> **Pro release:** Version 15.0.1.0.4 is validated for Odoo 15.0 and priced at US$49 one-time per Odoo major version. Provider-to-provider migration, rate throttling, and cost forecasting are not included in this release.

---

## Technical Notes

- **Original filestore is preserved** — retained for rollback safety
- **Finalized attachments served from S3** through Odoo with automatic filestore fallback
- **SHA-256 checksum verification** guarantees integrity on every file
- **Queue processing is idempotent** — retries never create duplicates
- **No monkey-patching of core Odoo models**
- **No modification of existing business workflows**

---

## Compatibility

Validated release available for every Odoo series from 14.0 to 19.0.  
Every supported Odoo version has its own dedicated branch and release package.

| Odoo Version | Status |
|---|---|
| 19.0 | [Branch 19.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/19.0) |
| 18.0 | [Branch 18.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/18.0) |
| 17.0 | [Branch 17.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/17.0) |
| 16.0 | [Branch 16.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/16.0) |
| 15.0 | ✅ This branch |
| 14.0 | [Branch 14.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/14.0) |

---

## Dependencies

- `base` (always)
- `web` (dashboard OWL components)
- **Python:** `boto3`

---

## Support

- **Issues:** [GitHub Issues](https://github.com/FoxPinkHQ/attachment-optimizer/issues)

---

## License

**LGPL-3** — see [LICENSE](LICENSE).

