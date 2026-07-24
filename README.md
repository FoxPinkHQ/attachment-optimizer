# Attachment Optimizer

> Analyze Odoo attachment storage and migrate files to S3-compatible object storage for **Odoo 18.0** Community Edition.

![Attachment Optimizer](attachment_optimizer/static/description/banner.png)

**Version:** 18.0.1.0.0 -- **License:** LGPL-3 -- **Publisher:** FoxPink -- Maintained for **Odoo 14.0-18.0**

## Features

- **Storage Analysis** -- scan all binary attachments and identify migration candidates
- **S3 Migration Pipeline** -- upload attachments to S3-compatible storage with content-addressed keys (SHA-256)
- **Checksum Verification** -- verify S3 object integrity before finalizing the migration
- **Transparent Read Flow** -- externalized attachments are served from S3 via standard `/web/content` without modifying `ir.attachment`
- **No Filestore Modification** -- original filestore files are preserved; S3 is an additional source, not a replacement
- **Migration Dashboard** -- monitor queue status, retry failed operations, track progress
- **Audit Trail** -- immutable log of all migration actions (user, action, timestamp, result)

## Screenshots

| # | View | Description |
|---|------|-------------|
| 01 | **Storage Mappings List** | Danh sách mappings — điểm vào chính, lọc theo trạng thái |
| 02 | **Storage Mapping Form** | Chi tiết mapping: attachment, S3 bucket/key, checksum, timestamp |
| 03 | **Migration Operations List** | Theo dõi tiến trình migration: queued/uploading/finalized/failed |
| 04 | **Migration Operation Form** | Chi tiết operation: state, mapping liên quan, error message |
| 05 | **Audit Log List** | Lịch sử thay đổi: user, action, attachment, result, timestamp |
| 06 | **Storage Mappings Search/Filter** | Tìm kiếm & lọc nâng cao (status, bucket, active) |

![01 Storage Mappings List](attachment_optimizer/static/description/screenshot_01_storage_mapping_list.png)
![02 Storage Mapping Form](attachment_optimizer/static/description/screenshot_02_storage_mapping_form.png)
![03 Migration Operations List](attachment_optimizer/static/description/screenshot_03_migration_operation_list.png)
![04 Migration Operation Form](attachment_optimizer/static/description/screenshot_04_migration_operation_form.png)
![05 Audit Log List](attachment_optimizer/static/description/screenshot_05_audit_log_list.png)
![06 Storage Mappings Search](attachment_optimizer/static/description/screenshot_06_storage_mapping_search.png)

## Installation

**Option 1 - Odoo Apps Store:** Download the ZIP for Odoo 18.0 from the [Releases](https://github.com/FoxPinkHQ/attachment-optimizer/releases) page, unzip into your addons directory, restart Odoo, and install via Apps.

**Option 2 - Git:**

```bash
git clone -b 18.0 https://github.com/FoxPinkHQ/attachment-optimizer addons/attachment_optimizer
```

After adding the module, restart Odoo, activate Developer Mode, go to **Apps -> Update Apps List**, search for "Attachment Optimizer", and install.

## Configuration

1. Set the following system parameters (**Settings > Technical > System Parameters**):
   - `attachment_storage.s3.bucket` -- S3 bucket name
   - `attachment_storage.s3.region` -- AWS region (default: `us-east-1`)
   - `attachment_storage.s3.access_key_id` -- S3 access key
   - `attachment_storage.s3.secret_access_key` -- S3 secret key
   - `attachment_storage.s3.endpoint_url` -- optional, for S3-compatible providers (MinIO, AWS S3, DigitalOcean Spaces)
2. Grant **Storage Optimization Manager** role to users who will manage migrations

## Dependencies

- `base` (always)
- `web` (views)

## Compatibility

| Odoo Version | Status |
|---|---|
| 18.0 | Supported |
| 17.0 | Supported |
| 16.0 | Supported |
| 15.0 | Supported |
| 14.0 | Supported |

Each series has its own git branch and validated release ZIP. Install the build matching your Odoo version.

## Support

- **Issues:** [GitHub Issues](https://github.com/FoxPinkHQ/attachment-optimizer/issues)
- **Email:** aduy000@gmail.com

## License

**LGPL-3** -- see [LICENSE](LICENSE).
