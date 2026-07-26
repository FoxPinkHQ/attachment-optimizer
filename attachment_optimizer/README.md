# Attachment Optimizer

Analyze Odoo attachment storage and migrate files to S3-compatible object storage.

## Features

- Analyze attachment storage usage across all models
- Queue attachments for migration to S3-compatible storage
- Upload, verify (SHA-256 checksum), and finalize migration per attachment
- Transparent S3 serving via `ir.binary` controller extension — finalized attachments served directly from S3
- Full audit trail with immutable logs
- Dashboard with KPI overview (total, migrated, saved bytes, failed)
- Batch upload with configurable limit
- Retry failed operations individually or in bulk
- Multi-company isolation via record rules

## Installation

Dependencies: `base`, `web`. The `boto3` Python package is required at runtime for S3 operations.

```bash
pip install boto3
```

Install the module via Apps menu.

## Configuration

Set the following system parameters (Settings → System Parameters):

| Key | Description |
|-----|-------------|
| `attachment_storage.s3.endpoint_url` | S3-compatible endpoint URL |
| `attachment_storage.s3.region` | S3 region (default: `us-east-1`) |
| `attachment_storage.s3.access_key_id` | S3 access key |
| `attachment_storage.s3.secret_access_key` | S3 secret key |
| `attachment_storage.s3.bucket` | Default S3 bucket |

## Usage

1. Assign a user to the **Storage Optimization Manager** group
2. Open the **Storage Optimization** dashboard
3. Click **Analyze Storage** to scan attachments
4. Review candidate count and click **Create Migration Queue**
5. Open **Migration Operations** and click **Start Upload** to begin batch migration
6. Monitor progress on the dashboard

## Security

- Role-based access: `group_storage_optimization_manager`
- Audit logs are immutable (write/unlink blocked at model level)
- Multi-company record rules isolate data by company
- Sudo usage is scoped to config parameters and attachment binary reads only

## Multi-company

All core models (`attachment.storage.mapping`, `attachment.migration.operation`, `attachment.audit.log`) include a `company_id` field. Record rules enforce `('company_id', 'in', company_ids)`.

## Technical Notes

- Migration does not delete original filestore data — attachments remain accessible via Odoo's default controller
- SHA-256 checksum verification runs after every upload before marking a mapping as finalized
- Upload batch limit: 100 operations per request

## License

LGPL-3
