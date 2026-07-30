# Attachment Optimizer

> **Reduce Odoo filestore growth by moving attachments to S3-compatible storage while keeping full rollback safety.**

![Attachment Optimizer](attachment_optimizer/static/description/preview.png)

**Version:** 19.0.1.0.0 â€” **License:** LGPL-3 â€” **Publisher:** FoxPink â€” Validated release available for every Odoo series from 14.0 to 19.0.

---

## Why use Attachment Optimizer?

Attachment Optimizer helps organizations keep Odoo storage under control by moving binary attachments to S3-compatible object storage without changing existing business workflows. The migration is verifiable, auditable, and fully reversible because original filestore data is preserved.

- **Reduce backup time** â€” from hours to minutes
- **Reduce infrastructure costs** â€” move cold attachments to low-cost object storage
- **Move attachments safely** â€” copy â†’ verify â†’ serve; original never deleted
- **Zero downtime** â€” attachments stay accessible during migration
- **Rollback anytime** â€” original filestore remains untouched

---

## How It Works

```
Analyze â†’ Queue â†’ Claim â†’ Upload â†’ Verify â†’ Finalize
                      â†‘_________â†“
                      Retry (idempotent)
```

---

## Architecture

```
Dashboard
     â”‚
Migration Service
     â”‚
Queue Engine
     â”‚
Recovery Engine
     â”‚
S3 Bridge
     â”‚
Amazon S3 / MinIO / Compatible
```

---

## Features

### Storage
- **Analyze attachment usage** â€” find large, old, unused attachments
- **Detect migration candidates** â€” filter by size, age, model, access frequency
- **Reduce filestore growth** â€” move cold data to S3, keep hot data local

### Migration
- **Queue-based migration** â€” analyze â†’ queue â†’ claim â†’ upload â†’ verify â†’ finalize
- **SHA-256 verification** â€” every file checksummed after upload
- **Retry failed uploads safely** â€” idempotent, no duplicates

### Safety
- **Original filestore preserved** â€” no data deleted during migration
- **Immutable audit logs** â€” every action logged with user, timestamp, result
- **Multi-company isolation** â€” record rules enforce data isolation

### Monitoring
- **Dashboard** â€” KPI cards (total, migrated, saved bytes, failed) with live progress
- **Health Checks** â€” 17 automated checks (DB, S3, queue, config, runtime)
- **Recovery Engine** â€” 5 rules auto-recover interrupted uploads

---

## Safety First

```
âœ“ Original filestore never deleted â€” dual-write for rollback safety
âœ“ Rollback always possible â€” original filestore remains untouched
âœ“ SHA-256 verification â€” integrity guaranteed on every file
âœ“ Immutable audit trail â€” every action logged with user, timestamp, result
âœ“ Retry is idempotent â€” retries never create duplicates
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

**Option 1 â€” Odoo Apps Store:** Download the ZIP for your Odoo version from the [Releases](https://github.com/FoxPinkHQ/attachment-optimizer/releases) page, unzip into your addons directory, restart Odoo, and install via Apps.

**Option 2 â€” Git:**

```bash
git clone -b 19.0 https://github.com/FoxPinkHQ/attachment-optimizer addons/attachment_optimizer
```

After adding the module, restart Odoo, activate Developer Mode, go to **Apps â†’ Update Apps List**, search for **Attachment Optimizer**, and install.

---

## Getting Started

1. **Configure S3** â€” Settings â†’ Attachment Optimizer: endpoint, region, access key, secret key, bucket
2. **Test Connection** â€” verify S3 reachability
3. **Analyze Storage** â€” Dashboard â†’ Analyze â†’ find migration candidates
4. **Create Queue** â€” review candidates â†’ Create Migration Queue
5. **Process Queue** â€” click Process Queue â†’ monitor live progress
6. **Monitor Dashboard** â€” confirm migrated count, saved bytes, failed count

---

## Configuration

1. **S3 Credentials:** Settings â†’ Attachment Optimizer â€” enter endpoint URL, region, access key, secret key, bucket name
2. **Test Connection** â€” click "Test Connection" to verify S3 reachability
3. **Auto-Recovery:** optionally enable auto-recovery in the same settings section

> **Recommended:** Use the Settings page instead of editing System Parameters manually.

---

## Security

- **Role-based access** â€” Storage Optimization Manager group controls dashboard/settings
- **Multi-company isolation** â€” record rules enforce data isolation
- **Immutable audit log** â€” every action logged with user, timestamp, result

---

## Current Limitations

- Single S3 bucket per installation
- No automatic filestore cleanup after finalization
- Migration queue is started manually
- Single worker per request (horizontal scaling planned)

---

## Technical Notes

- **Original filestore is preserved** â€” dual-write for rollback safety
- **Finalized attachments served from S3** via presigned URL stream
- **SHA-256 checksum verification** guarantees integrity on every file
- **Queue processing is idempotent** â€” retries never create duplicates
- **Dual-write during transition** â€” both filestore and S3 have the file until finalized

---

## Compatibility

Validated release available for every Odoo series from 14.0 to 19.0.  
Every supported Odoo version has its own dedicated branch and release package.

| Odoo Version | Status |
|---|---|
| 19.0 | [Branch 19.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/19.0) |
| 18.0 | âœ… This branch |
| 17.0 | [Branch 17.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/17.0) |
| 16.0 | [Branch 16.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/16.0) |
| 15.0 | [Branch 15.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/15.0) |
| 14.0 | [Branch 14.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/14.0) |

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

**LGPL-3** â€” see [LICENSE](LICENSE).
