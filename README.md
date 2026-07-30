# Attachment Optimizer

> **Reduce Odoo filestore size by up to 95% while keeping full rollback safety.**

![Attachment Optimizer](attachment_optimizer/static/description/preview.png)

**Version:** 18.0.2.1.0 -- **License:** LGPL-3 -- **Publisher:** FoxPink -- Maintained for **Odoo 14.0-19.0** (one validated build per series)

## Benefits

- **Smaller backups** → backup/restore nhanh gấp 10x
- **Lower storage costs** → S3 0.02$/GB vs SSD 0.10$/GB
- **Safe rollback** → filestore + S3 dual-write, không xóa dữ liệu gốc
- **Zero interruption** → attachment vẫn accessible suốt quá trình migrate
- **Compliance-ready** → immutable audit trail cho mọi hành động migrate

## Features

- **Migration pipeline** -- analyze, queue, upload, verify and finalize attachment migration to S3-compatible storage
- **Automatic recovery** -- recovers interrupted uploads (heartbeat timeout, stale workers, partial uploads, ownership conflicts, verify mismatch)
- **Health monitoring** -- detects configuration and storage problems before migration (17 checks)
- **Dashboard** -- KPI cards (total, migrated, saved bytes, failed) with live progress bar
- **S3 bridge** -- configurable endpoint, region and credentials; works with AWS S3, MinIO, any S3-compatible store
- **Audit trail** -- every migration action logged with user, timestamp and result
- **Retry and resume** -- failed uploads retried individually or in bulk; idempotent design prevents duplicates

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
git clone -b 18.0 https://github.com/FoxPinkHQ/attachment-optimizer addons/attachment_optimizer
```

After adding the module, restart Odoo, activate Developer Mode, go to **Apps -> Update Apps List**, search for "Attachment Optimizer", and install.

## Configuration

1. **S3 Credentials:** Settings -> Attachment Optimizer -- enter endpoint URL, region, access key, secret key and bucket name
2. **Test Connection:** click "Test Connection" to verify S3 reachability
3. **Auto-Recovery:** optionally enable auto-recovery in the same settings section

## Dependencies

- `base` (always)
- `web` (dashboard OWL components)

## Compatibility

| Odoo Version | Status |
|---|---|
| 19.0 | [Branch 19.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/19.0) |
| 18.0 | ✅ This branch |
| 17.0 | [Branch 17.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/17.0) |
| 16.0 | [Branch 16.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/16.0) |
| 15.0 | [Branch 15.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/15.0) |
| 14.0 | [Branch 14.0](https://github.com/FoxPinkHQ/attachment-optimizer/tree/14.0) |

Each series has its own git branch and validated release ZIP. Install the build matching your Odoo version.

## Support

- **Issues:** [GitHub Issues](https://github.com/FoxPinkHQ/attachment-optimizer/issues)
- **Email:** aduy000@gmail.com

## License

**LGPL-3** -- see [LICENSE](LICENSE).