# Attachment Optimizer

> **Reduce Odoo filestore size by up to 95% while keeping full rollback safety.**

![Attachment Optimizer](attachment_optimizer/static/description/preview.png)

**Version:** 19.0.1.0.0 -- **License:** LGPL-3 -- **Publisher:** FoxPink -- Maintained for **Odoo 14.0-19.0** (one validated build per series)

## Why use Attachment Optimizer?

- **Reduce local storage usage** — move attachments to S3-compatible storage
- **Keep existing Odoo workflows unchanged** — transparent serving from S3
- **Migrate gradually with full visibility** — queue-based, visible progress
- **Retry failed uploads safely** — idempotent, no duplicates
- **Verify every migrated object** — SHA-256 checksum on every file
- **Preserve rollback capability** — original filestore never deleted

## Features

### Storage
- **Analyze attachment usage** — find large, old, unused attachments
- **Detect migration candidates** — filter by size, age, model, access frequency
- **Reduce filestore growth** — move cold data to S3, keep hot data local

### Migration
- **Queue-based migration** — analyze → queue → upload → verify → finalize
- **SHA-256 verification** — every file checksummed after upload
- **Retry failed uploads safely** — idempotent, no duplicates

### Safety
- **Original filestore preserved** — no data deleted during migration
- **Immutable audit logs** — every migration action logged
- **Multi-company isolation** — record rules enforce data isolation

### Monitoring
- **Dashboard** — KPI cards (total, migrated, saved bytes, failed) with live progress
- **Health Checks** — 17 automated checks (DB, S3, queue, config, runtime)
- **Recovery Engine** — 5 automated repair rules for stuck/failed operations

## Screenshots

![Storage Mappings List](attachment_optimizer/static/description/screenshot_01_storage_mapping_list.png)
![Storage Mapping Form](attachment_optimizer/static/description/screenshot_02_storage_mapping_form.png)
![Migration Operations List](attachment_optimizer/static/description/screenshot_03_migration_operation_list.png)
![Migration Operation Form](attachment_optimizer/static/description/screenshot_04_migration_operation_form.png)
![Audit Log List](attachment_optimizer/static/description/screenshot_05_audit_log_list.png)
![Storage Mappings Search](attachment_optimizer/static/description/screenshot_06_storage_mapping_search.png)
![Settings](attachment_optimizer/static/description/screenshot_07_settings.png)
![Access Rights / Groups](attachment_optimizer/static/description/screenshot_08_access_rights.png)

## Installation

**Option 1 - Odoo Apps Store:** Download the ZIP for your Odoo version from the [Releases](https://github.com/FoxPinkHQ/attachment-optimizer/releases) page, unzip into your addons directory, restart Odoo, and install via Apps.

**Option 2 - Git:**

```bash
git clone -b 19.0 https://github.com/FoxPinkHQ/attachment-optimizer addons/attachment_optimizer
```

After adding the module, restart Odoo, activate Developer Mode, go to **Apps -> Update Apps List**, search for "Attachment Optimizer", and install.

## Usage

1. **Configure S3** — Settings → Attachment Optimizer: endpoint, region, keys, bucket
2. **Test Connection** — click "Test Connection"
3. **Analyze Storage** — Dashboard → Analyze to find migration candidates
4. **Create Queue** — Action → Create Migration Queue
5. **Process Queue** — Action → Process Queue
5. **Verify Dashboard** — monitor KPIs and progress

## Configuration

1. **S3 Credentials:** Settings → Attachment Optimizer — enter endpoint, region, keys, bucket
2. **Test Connection:** click "Test Connection" to verify S3 reachability
3. **Auto-Recovery:** optionally enable auto-recovery in the same settings section

## Security

- **Original attachments remain in the Odoo filestore.** No data is deleted during migration.
- **Finalized attachments are transparently served from S3.**
- **SHA-256 checksum verification guarantees integrity.**
- **Queue processing is idempotent.**
- **Multi-company isolation** — record rules enforce data isolation

## Technical Notes

- Migration does not delete original attachments — dual-write for rollback safety
- Finalized attachments served from S3 via presigned URL stream
- SHA-256 checksum verification on every upload
- Queue processing is idempotent — safe to retry

## Installation

**Option 1 - Odoo Apps Store:** Download the ZIP for your Odoo version from the [Releases](https://github.com/FoxPinkHQ/attachment-optimizer/releases) page, unzip into your addons directory, restart Odoo, and install via Apps.

**Option 2 - Git:**

```bash
git clone -b 19.0 https://github.com/FoxPinkHQ/attachment-optimizer addons/attachment_optimizer
```

After adding the module, restart Odoo, activate Developer Mode, go to **Apps -> Update Apps List**, search for "Attachment Optimizer", and install.

## Configuration

1. **S3 Credentials:** Settings → Attachment Optimizer — enter endpoint URL, region, access key, secret key, bucket name
2. **Test Connection:** click "Test Connection" to verify S3 reachability
3. **Auto-Recovery:** optionally enable auto-recovery in the same settings section

## Compatibility

| Odoo Version | Status |
|---|---|
| 19.0 | ✅ This branch |
| 18.0 | [Branch 18.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/18.0) |
| 17.0 | [Branch 17.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/17.0) |
| 16.0 | [Branch 16.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/16.0) |
| 15.0 | [Branch 15.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/15.0) |
| 14.0 | [Branch 14.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/14.0) |

Each series has its own git branch and validated release ZIP. Install the build matching your Odoo version.

## Dependencies

- `base` (always)
- `web` (dashboard OWL components)

## Support

- **Issues:** [GitHub Issues](https://github.com/FoxPinkHQ/attachment-optimizer/issues)
- **Email:** aduy000@gmail.com

## License

**LGPL-3** -- see [LICENSE](LICENSE).