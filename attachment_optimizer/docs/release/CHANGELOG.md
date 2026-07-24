# Changelog

## v1.0.0 (2026-07-24)

**Initial Release**

| FPAO | Component | Description |
|------|-----------|-------------|
| 001 | Storage Mapping | `foxpink.storage.mapping` model with lifecycle state machine (pending → uploading → uploaded → verified → finalized) |
| 002 | S3 Bridge | `S3Bridge` service with boto3 abstraction, retry (3x exponential backoff), access denied fail-fast |
| 003 | Migration Pipeline | `MigrationService` with analyze/queue/upload/verify/finalize pipeline, content-addressed S3 keys (SHA-256) |
| 004 | Read Flow | `ir.binary._get_stream_for` override serving finalized mappings from S3 via standard `/web/content` |
| 005 | Dashboard | Kanban overview grouped by status, "Create Migration Queue" and "Retry" buttons, ACL-gated |
| 006 | Audit | `foxpink.audit.log` model with immutable records, same-transaction logging across all pipeline stages |
| 007 | Validation | 82 tests across all components, security verification (9 tests), uninstall verification (4 tests), Odoo 17 syntax scan |
