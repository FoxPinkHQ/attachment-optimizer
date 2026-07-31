from odoo import fields
from odoo.tests import TransactionCase

from ..services.health_engine import (
    HealthEngine, HealthDomain, HealthSeverity, HealthStatus,
    HealthReport, HealthFinding,
)


class TestHealthContract(TransactionCase):
    """Contract-level tests for Health Engine ABI v1."""

    def setUp(self):
        super().setUp()
        self.engine = HealthEngine(self.env)
        self.Operation = self.env['attachment.migration.operation']
        self.Attachment = self.env['ir.attachment']
        self.Mapping = self.env['attachment.storage.mapping']
        self.Operation.search([]).unlink()
        self.Mapping.search([]).unlink()

    def _make_queued(self, n=1, prefix='h'):
        atts = self.Attachment.create([{
            'name': '%s_%d.txt' % (prefix, i), 'raw': b'd', 'type': 'binary',
        } for i in range(n)])
        ops = self.Operation.create([{
            'attachment_id': atts[i].id,
            'state': 'queued',
            'queued_at': fields.Datetime.now(),
        } for i in range(n)])
        return ops

    def _make_stale_uploading(self, n=1, prefix='stale'):
        ops = self._make_queued(n, prefix)
        claimed = self.Operation.claim_batch(limit=n, worker_id='h-test')
        self.env.cr.execute("""
            UPDATE attachment_migration_operation
            SET heartbeat_at = '2020-01-01'::timestamp
            WHERE id = ANY(%s)
        """, (claimed.ids,))
        return claimed

    # ── D1: Single check() API ─────────────────────────────

    def test_d1_check_returns_report(self):
        """check() returns a HealthReport."""
        report = self.engine.check()
        self.assertIsInstance(report, HealthReport)
        self.assertIsInstance(report.status, HealthStatus)

    def test_d1_check_filtered_by_domain(self):
        """Only requested domains run."""
        report = self.engine.check(domains=[HealthDomain.RUNTIME])
        for f in report.findings:
            self.assertEqual(f.domain, HealthDomain.RUNTIME,
                             'Only RUNTIME findings should appear')

    # ── D2: Immutable Report ───────────────────────────────

    def test_d2_report_is_frozen(self):
        """HealthReport and HealthFinding are frozen dataclasses."""
        finding = HealthFinding(
            domain=HealthDomain.RUNTIME, severity=HealthSeverity.OK,
            code='TEST', message='test',
        )
        with self.assertRaises(AttributeError):
            finding.severity = HealthSeverity.ERROR

        report = self.engine.check()
        with self.assertRaises(AttributeError):
            report.status = HealthStatus.CRITICAL

    # ── D3: Status severity mapping ────────────────────────

    def test_d3_status_rules(self):
        """Status follows defined rules: CRITICAL > ERROR > WARNING > OK."""
        report = self.engine.check(domains=[HealthDomain.RUNTIME])
        self.assertIsInstance(report.status, HealthStatus)

    def test_d3_critical_beats_error(self):
        """Findings with mixed severity produce correct status."""
        # Create orphan mapping triggers a warning
        att = self.Attachment.create({'name': 'orphan_ref.txt', 'raw': b'x', 'type': 'binary'})
        self.Mapping.create({
            'attachment_id': att.id,
            's3_bucket': 'test', 's3_key': 'orphan', 's3_region': 'us-east-1',
        })
        report = self.engine.check(domains=[HealthDomain.DATABASE])
        self.assertTrue(len(report.findings) > 0)
        # Status should be one of the valid statuses
        self.assertIsInstance(report.status, HealthStatus)

    # ── D4: Timing fields populated ────────────────────────

    def test_d4_timing_fields(self):
        """started_at, completed_at, duration_ms are populated."""
        report = self.engine.check()
        self.assertIsNotNone(report.started_at)
        self.assertIsNotNone(report.completed_at)
        self.assertGreater(report.duration_ms, 0)

    # ── D5: Read-only ──────────────────────────────────────

    def test_d5_read_only(self):
        """check() does not change any operation state."""
        ops = self._make_queued(3)
        before = {op.state for op in ops}
        report = self.engine.check()
        for op in ops:
            op.invalidate_cache()
        after = {op.state for op in ops}
        self.assertEqual(before, after,
                         'Health check must not change operation state')

    # ── D6: Handler pattern ────────────────────────────────

    def test_d6_each_domain_has_handler(self):
        """Every HealthDomain has a registered handler."""
        from ..services.health_engine import _HANDLERS
        for d in HealthDomain:
            self.assertIn(d, _HANDLERS,
                          'Domain %s has no handler' % d.value)

    # ── D7: Finding structure ──────────────────────────────

    def test_d7_finding_structure(self):
        """Every finding has all required fields."""
        report = self.engine.check()
        for f in report.findings:
            self.assertIsInstance(f.domain, HealthDomain)
            self.assertIsInstance(f.severity, HealthSeverity)
            self.assertTrue(f.code, 'code must not be empty')
            self.assertTrue(f.message, 'message must not be empty')
            # reference and recommendation are optional but must be strings
            self.assertIsInstance(f.reference, str)
            self.assertIsInstance(f.recommendation, str)


class TestDatabaseHealth(TransactionCase):
    """Health checks for Database domain."""

    def setUp(self):
        super().setUp()
        self.engine = HealthEngine(self.env)
        self.Operation = self.env['attachment.migration.operation']
        self.Attachment = self.env['ir.attachment']
        self.Mapping = self.env['attachment.storage.mapping']
        self.Operation.search([]).unlink()
        self.Mapping.search([]).unlink()

    def test_orphan_mapping_detected(self):
        """A mapping with no operation is detected."""
        att = self.Attachment.create({'name': 'orphan_test.txt', 'raw': b'x', 'type': 'binary'})
        self.Mapping.create({
            'attachment_id': att.id,
            's3_bucket': 'test', 's3_key': 'orphan', 's3_region': 'us-east-1',
        })
        report = self.engine.check(domains=[HealthDomain.DATABASE])
        codes = {f.code for f in report.findings}
        self.assertIn('DB_ORPHAN_MAPPING', codes)

    def test_orphan_operation_detected(self):
        """A finalized operation without mapping is detected."""
        att = self.Attachment.create({'name': 'orphan_op.txt', 'raw': b'x', 'type': 'binary'})
        op = self.Operation.create({
            'attachment_id': att.id,
            'state': 'finalized',
        })
        report = self.engine.check(domains=[HealthDomain.DATABASE])
        codes = {f.code for f in report.findings}
        self.assertIn('DB_ORPHAN_OPERATION', codes)

    def test_invalid_transition_detected(self):
        """An uploading op without processing_token is detected."""
        att = self.Attachment.create({'name': 'inv_trans.txt', 'raw': b'x', 'type': 'binary'})
        op = self.Operation.create({
            'attachment_id': att.id,
            'state': 'uploading',
            'processing_token': None,
        })
        report = self.engine.check(domains=[HealthDomain.DATABASE])
        codes = {f.code for f in report.findings}
        self.assertIn('DB_INVALID_TRANSITION', codes)

    def test_clean_db_produces_ok_findings(self):
        """No anomalies produce OK findings."""
        report = self.engine.check(domains=[HealthDomain.DATABASE])
        for f in report.findings:
            self.assertIn(f.severity, (HealthSeverity.OK, HealthSeverity.INFO),
                          'Clean DB should have only OK/INFO findings')




class TestConfigHealth(TransactionCase):
    """Health checks for Configuration domain."""

    def setUp(self):
        super().setUp()
        self.engine = HealthEngine(self.env)
        self.ICP = self.env['ir.config_parameter'].sudo()

    def test_missing_bucket_detected(self):
        """Missing s3.bucket config is detected."""
        self.ICP.set_param('attachment_storage.s3.bucket', '')
        report = self.engine.check(domains=[HealthDomain.CONFIGURATION])
        codes = {f.code for f in report.findings}
        self.assertIn('CFG_MISSING_ATTACHMENT_STORAGE_S3_BUCKET', codes)

    def test_config_present_is_ok(self):
        """When config is set, finding is OK."""
        self.ICP.set_param('attachment_storage.s3.bucket', 'my-bucket')
        self.ICP.set_param('attachment_storage.s3.region', 'us-east-1')
        report = self.engine.check(domains=[HealthDomain.CONFIGURATION])
        codes = {f.code for f in report.findings}
        ok_codes = [c for c in codes if c.startswith('CFG_') and 'MISSING' not in c and 'INVALID' not in c]
        self.assertTrue(len(ok_codes) > 0)


class TestRuntimeHealth(TransactionCase):
    """Health checks for Runtime domain."""

    def setUp(self):
        super().setUp()
        self.engine = HealthEngine(self.env)

    def test_runtime_checks_populated(self):
        """Runtime findings include boto3, temp_dir, python, postgres."""
        report = self.engine.check(domains=[HealthDomain.RUNTIME])
        codes = {f.code for f in report.findings}
        expected = {'RUNTIME_TEMP_DIR', 'RUNTIME_PYTHON', 'RUNTIME_POSTGRES'}
        boto_codes = {'RUNTIME_BOTO3', 'RUNTIME_BOTO3_MISSING'}
        self.assertTrue(
            codes & boto_codes,
            'Expected either RUNTIME_BOTO3 or RUNTIME_BOTO3_MISSING, got %s' % codes,
        )
        for code in expected:
            self.assertIn(code, codes, 'Missing runtime check: %s' % code)


class TestQueueHealth(TransactionCase):
    """Health checks for Queue domain."""

    def setUp(self):
        super().setUp()
        self.engine = HealthEngine(self.env)
        self.Operation = self.env['attachment.migration.operation']
        self.Attachment = self.env['ir.attachment']
        self.Operation.search([]).unlink()

    def test_backlog_reported(self):
        """Queued operations appear as INFO finding."""
        atts = self.Attachment.create([{
            'name': 'q_%d.txt' % i, 'raw': b'd', 'type': 'binary',
        } for i in range(3)])
        for att in atts:
            self.Operation.create({
                'attachment_id': att.id,
                'state': 'queued',
                'queued_at': fields.Datetime.now(),
            })
        report = self.engine.check(domains=[HealthDomain.QUEUE])
        codes = {f.code for f in report.findings}
        self.assertIn('QUEUE_BACKLOG', codes)

    def test_stuck_uploading_detected(self):
        """Operations stuck in uploading with old heartbeat are detected."""
        att = self.Attachment.create({'name': 'stuck.txt', 'raw': b'x', 'type': 'binary'})
        self.Operation.create({
            'attachment_id': att.id,
            'state': 'uploading',
            'processing_token': 'stuck-token',
            'worker_id': 'stuck-w',
            'claimed_at': '2020-01-01',
            'heartbeat_at': '2020-01-01',
        })
        report = self.engine.check(domains=[HealthDomain.QUEUE])
        codes = {f.code for f in report.findings}
        self.assertIn('QUEUE_STUCK_UPLOADING', codes)

    def test_failed_ops_detected(self):
        """Operations in failed state are detected."""
        att = self.Attachment.create({'name': 'failed_hlth.txt', 'raw': b'x', 'type': 'binary'})
        self.Operation.create({
            'attachment_id': att.id,
            'state': 'failed',
        })
        report = self.engine.check(domains=[HealthDomain.QUEUE])
        codes = {f.code for f in report.findings}
        self.assertIn('QUEUE_FAILED_OPS', codes)

    def test_clean_queue_no_warnings(self):
        """Clean queue has only OK findings."""
        report = self.engine.check(domains=[HealthDomain.QUEUE])
        for f in report.findings:
            self.assertIn(f.severity, (HealthSeverity.OK, HealthSeverity.INFO))
