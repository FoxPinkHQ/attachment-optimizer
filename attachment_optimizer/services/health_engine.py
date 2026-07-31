import logging
import os
import platform
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Collection, List, Optional

from odoo import fields

_logger = logging.getLogger(__name__)


class HealthDomain(Enum):
    DATABASE = 'database'
    S3 = 's3'
    QUEUE = 'queue'
    CONFIGURATION = 'configuration'
    RUNTIME = 'runtime'


class HealthSeverity(Enum):
    OK = 'ok'
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'
    CRITICAL = 'critical'


class HealthStatus(Enum):
    OK = 'ok'
    WARNING = 'warning'
    ERROR = 'error'
    CRITICAL = 'critical'


_STATUS_MAP = {
    HealthSeverity.CRITICAL: HealthStatus.CRITICAL,
    HealthSeverity.ERROR: HealthStatus.ERROR,
    HealthSeverity.WARNING: HealthStatus.WARNING,
    HealthSeverity.INFO: HealthStatus.OK,
    HealthSeverity.OK: HealthStatus.OK,
}


@dataclass(frozen=True)
class HealthFinding:
    domain: HealthDomain
    severity: HealthSeverity
    code: str
    message: str
    recommendation: str = ''
    reference: str = ''


@dataclass(frozen=True)
class HealthReport:
    status: HealthStatus = HealthStatus.OK
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_ms: int = 0
    checks: int = 0
    passed: int = 0
    findings: List[HealthFinding] = field(default_factory=list)


class HealthCheckHandler:
    domain: HealthDomain
    priority: int = 500

    def check(self, env) -> List[HealthFinding]:
        raise NotImplementedError

    def _finding(self, severity, code, message, recommendation='', reference=''):
        return HealthFinding(
            domain=self.domain, severity=severity, code=code,
            message=message, recommendation=recommendation, reference=reference,
        )

    def ok(self, code, message):
        return self._finding(HealthSeverity.OK, code, message)

    def info(self, code, message, recommendation='', reference=''):
        return self._finding(HealthSeverity.INFO, code, message, recommendation, reference)

    def warning(self, code, message, recommendation='', reference=''):
        return self._finding(HealthSeverity.WARNING, code, message, recommendation, reference)

    def error(self, code, message, recommendation='', reference=''):
        return self._finding(HealthSeverity.ERROR, code, message, recommendation, reference)

    def critical(self, code, message, recommendation='', reference=''):
        return self._finding(HealthSeverity.CRITICAL, code, message, recommendation, reference)


class DatabaseHealth(HealthCheckHandler):
    domain = HealthDomain.DATABASE
    priority = 100

    def check(self, env):
        findings = []
        Operation = env['attachment.migration.operation']

        # Orphan mappings: mapping exists but no operation references it
        env.cr.execute("""
            SELECT mp.id FROM attachment_storage_mapping mp
            LEFT JOIN attachment_migration_operation op ON op.mapping_id = mp.id
            WHERE op.id IS NULL
            LIMIT 10
        """)
        orphan_maps = [r[0] for r in env.cr.fetchall()]
        if orphan_maps:
            findings.append(self.warning(
                'DB_ORPHAN_MAPPING',
                '%d storage mappings have no linked migration operation' % len(orphan_maps),
                'Review and clean up orphan mappings via consistency check',
                'attachment.storage.mapping id in %s' % orphan_maps,
            ))
        else:
            findings.append(self.ok('DB_ORPHAN_MAPPING', 'No orphan storage mappings'))

        # Orphan operations: finalized/verified but no mapping
        orphan_ops = Operation.search([
            ('state', 'in', ('finalized', 'verified')),
            ('mapping_id', '=', False),
        ])
        if orphan_ops:
            ids = orphan_ops.ids[:10]
            findings.append(self.warning(
                'DB_ORPHAN_OPERATION',
                '%d operations are finalized/verified with no mapping' % len(orphan_ops),
                'Run consistency check to resolve orphan operations',
                'attachment.migration.operation id in %s' % ids,
            ))
        else:
            findings.append(self.ok('DB_ORPHAN_OPERATION', 'No orphan operations'))

        # Duplicate active: multiple active ops for same attachment
        env.cr.execute("""
            SELECT a.id, COUNT(op.id) as cnt
            FROM attachment_migration_operation op
            JOIN ir_attachment a ON a.id = op.attachment_id
            WHERE op.is_active = TRUE
            GROUP BY a.id
            HAVING COUNT(op.id) > 1
            LIMIT 10
        """)
        duplicates = env.cr.fetchall()
        if duplicates:
            refs = ['attachment_id=%d' % r[0] for r in duplicates]
            findings.append(self.error(
                'DB_DUPLICATE_ACTIVE',
                '%d attachments have multiple active operations' % len(duplicates),
                'Only one active operation per attachment is allowed',
                '; '.join(refs),
            ))
        else:
            findings.append(self.ok('DB_DUPLICATE_ACTIVE', 'No duplicate active operations'))

        # Broken FK: mapping references non-existent attachment
        env.cr.execute("""
            SELECT mp.id FROM attachment_storage_mapping mp
            LEFT JOIN ir_attachment a ON a.id = mp.attachment_id
            WHERE a.id IS NULL
            LIMIT 10
        """)
        broken = [r[0] for r in env.cr.fetchall()]
        if broken:
            findings.append(self.error(
                'DB_BROKEN_FK',
                '%d storage mappings reference deleted attachments' % len(broken),
                'Remove or reassign orphaned storage mappings',
                'attachment.storage.mapping id in %s' % broken,
            ))
        else:
            findings.append(self.ok('DB_BROKEN_FK', 'No broken foreign key references'))

        # Invalid transitions: operations in uploading state without token
        env.cr.execute("""
            SELECT id FROM attachment_migration_operation
            WHERE state = 'uploading'
              AND processing_token IS NULL
            LIMIT 10
        """)
        invalid = [r[0] for r in env.cr.fetchall()]
        if invalid:
            findings.append(self.warning(
                'DB_INVALID_TRANSITION',
                '%d operations are uploading without processing_token' % len(invalid),
                'Run Recovery Engine InvalidOwnershipRule',
                'attachment.migration.operation id in %s' % invalid,
            ))
        else:
            findings.append(self.ok('DB_INVALID_TRANSITION', 'No invalid state transitions'))

        return findings


class QueueHealth(HealthCheckHandler):
    domain = HealthDomain.QUEUE
    priority = 200

    def check(self, env):
        findings = []
        Operation = env['attachment.migration.operation']

        # Backlog size
        queued_count = Operation.search_count([('state', '=', 'queued')])
        findings.append(self.info(
            'QUEUE_BACKLOG',
            '%d operations in queued state' % queued_count,
            recommendation=(
                'Monitor for growth; run process_queue if backlog persists'
                if queued_count > 100 else ''
            ),
        ))

        # Stuck uploading (no heartbeat > 30 min)
        env.cr.execute("""
            SELECT id FROM attachment_migration_operation
            WHERE state = 'uploading'
              AND processing_token IS NOT NULL
              AND heartbeat_at < %s::timestamp - INTERVAL '30 minutes'
            LIMIT 10
        """, (fields.Datetime.now().isoformat(),))
        stuck = env.cr.fetchall()
        if stuck:
            ids = [r[0] for r in stuck]
            findings.append(self.warning(
                'QUEUE_STUCK_UPLOADING',
                '%d operations stuck in uploading state' % len(stuck),
                'Run Recovery Engine HeartbeatTimeoutRule',
                'attachment.migration.operation id in %s' % ids,
            ))
        else:
            findings.append(self.ok('QUEUE_STUCK_UPLOADING', 'No stuck uploading operations'))

        # Stuck failed
        failed_count = Operation.search_count([('state', '=', 'failed')])
        if failed_count > 0:
            findings.append(self.warning(
                'QUEUE_FAILED_OPS',
                '%d operations in failed state' % failed_count,
                'Run Recovery Engine VerifyMismatchRule and PartialUploadRule',
            ))
        else:
            findings.append(self.ok('QUEUE_FAILED_OPS', 'No failed operations'))

        # Oldest queued age
        env.cr.execute("""
            SELECT MIN(queued_at) FROM attachment_migration_operation
            WHERE state = 'queued' AND queued_at IS NOT NULL
        """)
        oldest = env.cr.fetchone()[0]
        if oldest:
            age = fields.Datetime.now() - oldest
            age_hours = age.total_seconds() / 3600
            if age_hours > 24:
                findings.append(self.warning(
                    'QUEUE_OLDEST_AGE',
                    'Oldest queued operation is %.1f hours old' % age_hours,
                    'Check worker availability and queue throughput',
                ))
            elif age_hours > 1:
                findings.append(self.info(
                    'QUEUE_OLDEST_AGE',
                    'Oldest queued operation is %.1f hours old' % age_hours,
                ))

        return findings


class S3Health(HealthCheckHandler):
    domain = HealthDomain.S3
    priority = 300

    def check(self, env):
        findings = []
        ICP = env['ir.config_parameter'].sudo()

        bucket = ICP.get_param('attachment_storage.s3.bucket', '')
        if not bucket:
            findings.append(self.warning(
                'S3_BUCKET_MISSING',
                'S3 bucket is not configured',
                'Set attachment_storage.s3.bucket in System Parameters',
            ))
            return findings

        try:
            from ..services.s3_bridge import S3Bridge
            s3 = S3Bridge(env)

            # HEAD bucket
            try:
                head_ok = s3.head(bucket, 'health-check-ping')
                findings.append(self.ok(
                    'S3_HEAD',
                    'S3 HEAD operation succeeded for bucket %s' % bucket,
                ))
            except Exception as e:
                findings.append(self.error(
                    'S3_HEAD_FAILED',
                    'S3 HEAD failed for bucket %s: %s' % (bucket, e),
                    'Verify bucket exists and credentials are valid',
                    'attachment_storage.s3.bucket=%s' % bucket,
                ))

            # List to verify read access
            try:
                mappings = env['attachment.storage.mapping'].search([
                    ('s3_bucket', '=', bucket), ('s3_key', '!=', False),
                ], limit=1)
                if mappings:
                    mp = mappings[0]
                    obj = s3.get_object(bucket, mp.s3_key)
                    findings.append(self.ok(
                        'S3_GET',
                        'S3 GET succeeded for existing object %s' % mp.s3_key,
                    ))
                    findings.append(self.ok(
                        'S3_ACCESS',
                        'Read access verified for bucket %s' % bucket,
                    ))
                else:
                    findings.append(self.info(
                        'S3_GET',
                        'No existing objects to verify S3 GET; HEAD only',
                    ))
            except Exception as e:
                findings.append(self.error(
                    'S3_GET_FAILED',
                    'S3 GET failed for bucket %s: %s' % (bucket, e),
                    'Verify IAM policy allows s3:GetObject',
                    'attachment_storage.s3.bucket=%s' % bucket,
                ))

        except ImportError:
            findings.append(self.critical(
                'S3_BOTO3_MISSING',
                'boto3 library is not available',
                'Install boto3: pip install boto3',
            ))
        except Exception as e:
            _logger.warning('S3 health check error: %s', e)
            findings.append(self.error(
                'S3_CHECK_ERROR',
                'S3 health check failed: %s' % e,
            ))

        return findings


class ConfigHealth(HealthCheckHandler):
    domain = HealthDomain.CONFIGURATION
    priority = 400

    REQUIRED_PARAMS = {
        'attachment_storage.s3.bucket': 'S3 bucket name',
        'attachment_storage.s3.region': 'S3 region',
    }

    INT_PARAMS = {
        'attachment_storage.recovery.limit': 'Recovery batch limit',
    }

    def check(self, env):
        findings = []
        ICP = env['ir.config_parameter'].sudo()

        for key, desc in self.REQUIRED_PARAMS.items():
            val = ICP.get_param(key, '').strip()
            if not val:
                findings.append(self.error(
                    'CFG_MISSING_%s' % key.upper().replace('.', '_'),
                    'Required config %s (%s) is not set' % (key, desc),
                    'Set %s in System Parameters' % key,
                ))
            else:
                findings.append(self.ok(
                    'CFG_%s' % key.upper().replace('.', '_'),
                    '%s is configured: %s' % (desc, val),
                ))

        for key, desc in self.INT_PARAMS.items():
            val = ICP.get_param(key, '')
            if val:
                try:
                    int(val)
                except (ValueError, TypeError):
                    findings.append(self.warning(
                        'CFG_INVALID_%s' % key.upper().replace('.', '_'),
                        '%s (%s) is not a valid integer: %s' % (key, desc, val),
                        'Set %s to a valid integer' % key,
                    ))

        # Check recovery enabled
        recovery_enabled = ICP.get_param('attachment_storage.recovery.enabled', 'True')
        if recovery_enabled not in ('True', 'true', '1'):
            findings.append(self.info(
                'CFG_RECOVERY_DISABLED',
                'Recovery engine is disabled via config',
                'Set attachment_storage.recovery.enabled=True to enable',
            ))

        return findings


class RuntimeHealth(HealthCheckHandler):
    domain = HealthDomain.RUNTIME
    priority = 500

    def check(self, env):
        findings = []

        # boto3
        try:
            import boto3
            findings.append(self.ok('RUNTIME_BOTO3', 'boto3 is installed (version %s)' % boto3.__version__))
        except ImportError:
            findings.append(self.error(
                'RUNTIME_BOTO3_MISSING',
                'boto3 is not installed',
                'Install boto3: pip install boto3',
            ))

        # Temp directory writable
        temp_dir = tempfile.gettempdir()
        test_file = os.path.join(temp_dir, '.health_check_%d' % id(env))
        try:
            with open(test_file, 'w') as f:
                f.write('ok')
            os.unlink(test_file)
            findings.append(self.ok('RUNTIME_TEMP_DIR', 'Temp directory is writable: %s' % temp_dir))
        except (OSError, PermissionError) as e:
            findings.append(self.critical(
                'RUNTIME_TEMP_DIR_NOT_WRITABLE',
                'Temp directory is not writable: %s' % temp_dir,
                'Check filesystem permissions',
                'path=%s' % temp_dir,
            ))

        # Python version
        pyver = platform.python_version()
        parts = pyver.split('.')
        major, minor = int(parts[0]), int(parts[1])
        if (major, minor) >= (3, 10):
            findings.append(self.ok('RUNTIME_PYTHON', 'Python %s' % pyver))
        else:
            findings.append(self.warning(
                'RUNTIME_PYTHON',
                'Python %s is below recommended 3.10+' % pyver,
                'Upgrade Python to 3.10 or later',
            ))

        # PostgreSQL version
        env.cr.execute("SHOW server_version")
        pgver = env.cr.fetchone()[0]
        findings.append(self.ok('RUNTIME_POSTGRES', 'PostgreSQL %s' % pgver))

        return findings


_HANDLERS = {
    handler_class.domain: handler_class()
    for handler_class in (
        DatabaseHealth, QueueHealth, S3Health, ConfigHealth, RuntimeHealth,
    )
}

_SORTED_DOMAINS = sorted(
    HealthDomain,
    key=lambda d: _HANDLERS[d].priority,
)


class HealthEngine:
    def __init__(self, env):
        self.env = env

    def check(
        self,
        domains: Optional[Collection[HealthDomain]] = None,
    ) -> HealthReport:
        started_at = datetime.utcnow()
        active_domains = domains or _SORTED_DOMAINS
        all_findings = []

        for domain_enum in _SORTED_DOMAINS:
            if domain_enum not in active_domains:
                continue
            handler = _HANDLERS[domain_enum]
            try:
                findings = handler.check(self.env)
                all_findings.extend(findings)
            except Exception as e:
                _logger.exception('Health check for %s failed', domain_enum.value)
                all_findings.append(HealthFinding(
                    domain=domain_enum,
                    severity=HealthSeverity.ERROR,
                    code='HEALTH_CHECK_ERROR',
                    message='Health check for %s failed: %s' % (domain_enum.value, e),
                    recommendation='Check logs for details',
                ))

        completed_at = datetime.utcnow()
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)

        severity_map = {
            HealthSeverity.CRITICAL: HealthStatus.CRITICAL,
            HealthSeverity.ERROR: HealthStatus.ERROR,
            HealthSeverity.WARNING: HealthStatus.WARNING,
            HealthSeverity.INFO: HealthStatus.OK,
            HealthSeverity.OK: HealthStatus.OK,
        }

        worst = HealthStatus.OK
        for f in all_findings:
            mapped = severity_map.get(f.severity, HealthStatus.OK)
            mapped_order = [HealthStatus.OK, HealthStatus.WARNING, HealthStatus.ERROR, HealthStatus.CRITICAL]
            if mapped_order.index(mapped) > mapped_order.index(worst):
                worst = mapped

        passed = sum(1 for f in all_findings if f.severity in (HealthSeverity.OK, HealthSeverity.INFO))

        return HealthReport(
            status=worst,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            checks=len(all_findings),
            passed=passed,
            findings=all_findings,
        )
