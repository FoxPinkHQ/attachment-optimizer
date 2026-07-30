# Attachment Optimizer

> **Reduce Odoo filestore size by up to 95% while keeping full rollback safety.**

![Attachment Optimizer](attachment_optimizer/static/description/preview.png)

**Version:** 18.0.2.1.0 — **License:** LGPL-3 — **Publisher:** FoxPink — Maintained for **Odoo 14.0-19.0** (one validated build per series)

---

## Why use Attachment Optimizer?

> **Attachment Optimizer helps companies keep Odoo storage under control by moving binary attachments to S3-compatible object storage without changing existing business workflows. It preserves rollback safety, verifies every migrated object, and provides full auditability throughout the migration process.**

- **Reduce backup time** — from hours to minutes
- **Reduce VPS storage cost** — S3 0.02$/GB vs local SSD 0.10$/GB
- **Move attachments safely** — copy → verify → serve; original never deleted
- **Zero downtime** — attachments stay accessible during migration
- **Rollback anytime** — original filestore preserved, no data deleted

---

## How It Works

```
Analyze → Create Queue → Claim → Upload → Verify → Finalize
                                    ↑_________↓
                                    Retry (idempotent)
```

---

## Features

### Storage
- **Analyze attachment usage** — find large, old, unused attachments
- **Detect migration candidates** — filter by size, age, model, access frequency
- **Reduce filestore growth** — move cold data to S3, keep hot data local

### Migration
- **Queue-based migration** — analyze → queue → claim → upload → verify → finalize
- **SHA-256 verification** — every file checksummed after upload
- **Retry failed uploads safely** — idempotent, no duplicates

### Safety
- **Original filestore preserved** — no data deleted during migration
- **Immutable audit logs** — every action logged with user, timestamp, result
- **Multi-company isolation** — record rules enforce data isolation

### Monitoring
- **Dashboard** — KPI cards (total, migrated, saved bytes, failed) with live progress
- **Health Checks** — 17 automated checks (DB, S3, queue, config, runtime)
- **Recovery Engine** — 5 rules auto-recover interrupted uploads

---

## Safety First

```
✓ Original filestore never deleted — dual-write for rollback safety
✓ Rollback always possible — finalized attachments served from S3 via presigned URL
✓ SHA-256 verification — integrity guaranteed on every file
✓ Immutable audit trail — every action logged with user, timestamp, result
✓ Retry is idempotent — retries never create duplicates
```

---

## Screenshots

![01 Dashboard](attachment_optimizer/static/description/screenshot_01_dashboard.png)
![02 Settings](attachment_optimizer/static/description/screenshot_02_settings.png)
![03 Storage Mapping List](attachment_optimizer/static/description/screenshot_03_storage_mapping_list.png)
![04 Storage Mapping Form](attachment_optimizer/static/description/screenshot_04_storage_mapping_form.png)
![05 Migration Queue](attachment_optimizer/static/description/screenshot_05_migration_operation_list.png)
![06 Migration Operation Form](attachment_optimizer/static/description/screenshot_06_migration_operation_form.png)
![07 Audit Logs](attachment_optimizer/static/description/screenshot_07_audit_log_list.png)
![08 Access Rights](attachment_optimizer/static/description/screenshot_08_access_rights.png)

---

## Installation

**Option 1 — Odoo Apps Store:** Download the ZIP for your Odoo version from the [Releases](https://github.com/FoxPinkHQ/attachment-optimizer/releases) page, unzip into your addons directory, restart Odoo, and install via Apps.

**Option 2 — Git:**

```bash
git clone -b 18.0 https://github.com/FoxPinkHQ/attachment-optimizer addons/attachment_optimizer
```

After adding the module, restart Odoo, activate Developer Mode, go to **Apps → Update Apps List**, search for **Attachment Optimizer**, and install.

---

## Getting Started

1. **Configure S3** — Settings → Attachment Optimizer: endpoint, region, access key, secret key, bucket
2. **Test Connection** — verify S3 reachability
3. **Analyze Storage** — Dashboard → Analyze → find migration candidates
4. **Create Queue** — review candidates → Create Migration Queue
5. **Process Queue** — click Process Queue → monitor live progress
6. **Verify Dashboard** — confirm migrated count, saved bytes, failed count

---

## Configuration

1. **S3 Credentials:** Settings → Attachment Optimizer — enter endpoint URL, region, access key, secret key, bucket name
2. **Test Connection** — click "Test Connection" to verify S3 reachability
3. **Auto-Recovery:** optionally enable auto-recovery in the same settings section

> **Recommended:** Use the Settings page instead of editing System Parameters manually.

---

## Safety

- **Original attachments remain in the Odoo filestore.** No data is deleted during migration.
- **Finalized attachments are transparently served from S3** via presigned URLs.
- **SHA-256 checksum verification** guarantees integrity on every file.
- **Queue processing is idempotent** — retries never create duplicates.
- **Multi-company isolation** via record rules — users only see their company's data.

---

## Current Limitations

- Single S3 bucket per installation
- No automatic filestore cleanup after finalization
- Queue processing is manual (cron planned)
- Single worker per request (horizontal scaling planned)

---

## Technical Notes

- **Original filestore is preserved** — dual-write for rollback safety
- **Finalized attachments served from S3** via presigned URL stream
- **SHA-256 checksum verification** guarantees integrity on every file
- **Queue processing is idempotent** — retries never create duplicates
- **Dual-write during transition** — both filestore and S3 have the file until finalized

---

## Compatibility

Validated release available for every Odoo series from 14.0 to 19.0.  
Each version is maintained in its own branch.

| Odoo Version | Status |
|---|---|
| 19.0 | [Branch 19.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/19.0) |
| 18.0 | ✅ This branch |
| 17.0 | [Branch 17.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/17.0) |
| 16.0 | [Branch 16.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/16.0) |
| 15.0 | [Branch 15.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/15.0) |
| 14.0 | [Branch 14.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/14.0) |

Each series has its own git branch and validated release ZIP. Install the build matching your Odoo version.

---

## Dependencies

- `base` (always)
- `web` (dashboard OWL components)

---

## Support

- **Issues:** [GitHub Issues](https://github.com/FoxPinkHQ/attachment-optimizer/issues)
- **Email:** aduy000@gmail.com

---

## License

**LGPL-3** — see [LICENSE](LICENSE).