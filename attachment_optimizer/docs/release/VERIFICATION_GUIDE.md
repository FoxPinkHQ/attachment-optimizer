# Verification Guide — attachment_optimizer v1.0.0

## Prerequisites

- Docker Engine 24+ (Docker Desktop or Rancher Desktop)
- Docker Compose v2+
- 4 GB RAM minimum, 8 GB recommended
- Ports **18018**, **9000**, **9001** must be free

## 1. Start Environment

```bash
cd docker
docker compose up -d --build
```

Wait ~90 seconds for all services to become healthy:

```bash
docker compose ps
```

Expected output:

```
NAME                SERVICE             STATUS
fp18-db             db                  running (healthy)
fp18-minio          minio               running (healthy)
fp18-mc             createbuckets       exited (0)
fp18-odoo           odoo                running
```

## 2. Access Odoo

Open http://localhost:18018 in your browser.

### Database Setup

1. Click **Create Database**
2. Set:
   - Database Name: `attachment_opt18`
   - Email: `admin@example.com`
   - Password: `admin`
   - Phone: (optional)
   - Load Demo Data: **checked**
   - Default Language: English
3. Click **Create Database** and wait for initialization

### Module Installation

1. Activate **Developer Mode**:
   - Settings → Activate Developer Mode
2. Go to **Apps** → click **Update Apps List** (🔍 icon)
3. Search for `attachment_optimizer`
4. Click **Install**

## 3. Configure S3 (MinIO)

The Docker environment includes MinIO at `http://minio:9000` with:
- Access Key: `minioadmin`
- Secret Key: `minioadmin`
- Pre-created bucket: `attachment-storage-test`

### Set Odoo System Parameters

Navigate to **Settings → Technical → System Parameters** and create:

| Key | Value |
|-----|-------|
| `attachment_storage.s3.endpoint_url` | `http://minio:9000` |
| `attachment_storage.s3.region` | `us-east-1` |
| `attachment_storage.s3.access_key_id` | `minioadmin` |
| `attachment_storage.s3.secret_access_key` | `minioadmin` |
| `attachment_storage.s3.bucket` | `attachment-storage-test` |

### Verify S3 Connection

Open **Storage Optimization → Dashboard**. The kanban view shows all storage
mappings (initially empty).

## 4. Verification Flow

### Step 1 — Create Test Attachments

Navigate to **Settings → Technical → Attachments** and create 2-3 binary
attachments with small files (PDF, images, or text).

### Step 2 — Analyze Candidates

Open **Storage Optimization → Migration Operations**.
Click **Create Migration Queue**.

A notification confirms: *N migration operation(s) created*.

### Step 3 — Process Queue

Run the migration pipeline via Odoo shell:

```bash
docker exec ao18-odoo odoo shell -d attachment_opt18 --db_host db --db_user odoo --db_password odoo --db_port 5432 --no-http
```

Inside the shell:

```python
from odoo.addons.attachment_optimizer.services.migration_service import MigrationService
s = MigrationService(self.env)
result = s.process_queue()
print('Success:', result['success'], 'Failed:', result['failed'])
exit()
```

### Step 4 — Verify Storage Mappings

Go to **Storage Optimization → Storage Mappings**.

Each migrated attachment shows:
- Status: `finalized` (green badge)
- S3 Key: `objects/{sha256[:2]}/{sha256}`
- Checksum: SHA-256 hash match

### Step 5 — Verify Read Flow

1. Open **Settings → Technical → Attachments**
2. Open one of the migrated attachments
3. Click the download link — attachment should download correctly

### Step 6 — Check Audit Logs

Go to **Storage Optimization → Audit Logs**.

Expected events in chronological order:

| Action | Result |
|--------|--------|
| `analyze` | success |
| `migration_queue_created` | success |
| `queue` (× N) | success |
| `upload` (× N) | success |
| `verify` (× N) | success |
| `finalize` (× N) | success |

### Step 7 — Verify store_fname Unchanged

Check directly in the database that the original filestore path is preserved:

```bash
docker exec ao18-db psql -U odoo -d attachment_opt18 -c \
  "SELECT id, name, store_fname FROM ir_attachment WHERE store_fname IS NOT NULL;"
```

All `store_fname` values should be unchanged from their original values.

## 5. Security Verification

### Test ACL

1. Log out as admin
2. Create a new user with only `Employee` group (no Storage Optimization Manager)
3. Log in as that user
4. Verify:
   - No **FoxPink** menu appears
   - Direct URL access to `/web#action=attachment_dashboard_action` returns access error

### Test Audit Immutability

From Odoo shell:

```python
log = self.env['attachment.audit.log'].search([], limit=1)
log.write({'error_message': 'tampered'})   # must raise AccessError
log.unlink()                               # must raise AccessError
```

## 6. Clean Uninstall Verification

1. Go to **Apps → attachment_optimizer**
2. Click **Uninstall**
3. Confirm uninstall
4. Verify:
   - Module removed from installed apps list
   - Attachments remain in **Settings → Technical → Attachments**
   - No `attachment_storage.s3.*` parameters remain in System Parameters

## 7. Troubleshooting

### Odoo fails to start

Check logs:

```bash
docker logs fp18-odoo
```

Common causes:
- Database not ready — wait 15 seconds, retry
- Port conflict — change `18018` in docker-compose.yml

### S3 Connection Failed

```bash
# Test MinIO is accessible from Odoo container
docker exec fp18-odoo curl -s http://minio:9000/minio/health/live
```

Expected response: `{"status":"ok"}`

### Migration Fails

Check the error message in:
- **Storage Optimization → Migration Operations** (error_message column)
- **Storage Optimization → Audit Logs** (failure entries)

### MinIO Console

Access http://localhost:9001 (credentials: `minioadmin` / `minioadmin`)
to browse S3 objects and verify uploaded content.
