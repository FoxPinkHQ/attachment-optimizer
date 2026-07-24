# Docker Verification Environment

## Overview

This Docker Compose environment provides everything needed to verify
`attachment_optimizer` v1.0.0 in a clean Odoo 18 instance with
MinIO (S3-compatible storage) for offline testing.

## Services

| Service | Image | Purpose |
|---------|-------|---------|
| `fp18-odoo` | `foxpink-odoo:18.0` (odoo:18.0 + boto3) | Odoo 18 with module |
| `fp18-db` | `postgres:15` | Database |
| `fp18-minio` | `minio/minio` | S3-compatible storage |
| `fp18-mc` | `minio/mc` | Auto-creates bucket on startup |

## Quick Start

### Prerequisites

- Docker Engine 24+
- Docker Compose v2+
- 4 GB RAM minimum, 8 GB recommended

### Start

```bash
cd docker
docker compose up -d --build
```

Wait ~60 seconds for all services to initialize, then:

- **Odoo**: http://localhost:18018
- **MinIO Console**: http://localhost:9001 (login: `minioadmin` / `minioadmin`)
- **MinIO S3 API**: http://localhost:9000

### Setup Odoo Database

1. Open http://localhost:18018
2. Create a new database (e.g., `attachment_opt18`)
3. Activate Developer Mode (Settings → Activate Developer Mode)
4. Go to Apps → Update Apps List
5. Search for `attachment_optimizer` and install

### Configure S3

In Odoo, set the following system parameters
(Settings → Technical → System Parameters):

| Key | Value |
|-----|-------|
| `attachment_storage.s3.endpoint_url` | `http://minio:9000` |
| `attachment_storage.s3.region` | `us-east-1` |
| `attachment_storage.s3.bucket` | `attachment-storage-test` |
| `attachment_storage.s3.access_key_id` | `minioadmin` |
| `attachment_storage.s3.secret_access_key` | `minioadmin` |

## Verification Flow

### 1. Create Test Attachment

Create a binary attachment via Settings → Technical → Attachments,
or programmatically via Odoo shell.

### 2. Navigate to Dashboard

Storage Optimization → Dashboard — shows analysis overview.

### 3. Create Migration Queue

Storage Optimization → Migration Operations → **Create Migration Queue**.

### 4. Process Queue

Run the pipeline:

```bash
docker exec fp18-odoo odoo shell -d <db_name> --db_host db --db_user odoo --db_password odoo --db_port 5432 --no-http
```

Inside the shell:

```python
from odoo.addons.attachment_optimizer.services.migration_service import MigrationService
s = MigrationService(self.env)
r = s.process_queue()
print(r)
```

### 5. Verify

- View Storage Mappings — check status = `finalized`
- Open the attachment via the UI — content still served correctly
- Check Audit Logs — all migration events recorded

## Shutdown

```bash
docker compose down
```

To remove all data:

```bash
docker compose down -v
```
