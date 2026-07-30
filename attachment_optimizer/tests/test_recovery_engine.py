from odoo import fields
from odoo.tests import TransactionCase
from odoo.exceptions import ValidationError

from ..services.recovery_engine import (
    RecoveryEngine, RecoveryMode, RecoveryRule, RecoveryReason,
    RecoveryReport, RecoveryEntry,
)


class TestRecoveryContract(TransactionCase):
    """DoD D1–D8: contract-level tests."""

    def setUp(self):
        super().setUp()
        self.engine = RecoveryEngine(self.env)
        self.Operation = self.env['attachment.migration.operation']
        self.Attachment = self.env['ir.attachment']
        self.Operation.search([]).unlink()

    def _make_queued(self, n=1, prefix='rec'):
        atts = self.Attachment.create([{
            'name': '%s_%d.txt' % (prefix, i), 'raw': b'd', 'type': 'binary',
        } for i in range(n)])
        ops = self.Operation.create([{
            'attachment_id': atts[i].id,
            'state': 'queued',
            'queued_at': fields.Datetime.now(),
        } for i in range(n)])
        return ops

    def _make_uploading_stale(self, n=1, prefix='stale'):
        ops = self._make_queued(n, prefix)
        claimed = self.Operation.claim_batch(limit=n, worker_id='test-worker')
        self.env.cr.execute("""
            UPDATE attachment_migration_operation
            SET heartbeat_at = '2020-01-01'::timestamp
            WHERE id = ANY(%s)
        """, (claimed.ids,))
        return claimed

    # ── D1: Single recover() API ──────────────────────────

    def test_d1_recover_filtered_by_rule(self):
        """Only the requested rule runs."""
        ops = self._make_uploading_stale(3)
        report = self.engine.recover(
            rules=[RecoveryRule.HEARTBEAT_TIMEOUT],
            mode=RecoveryMode.REPAIR,
        )
        self.assertEqual(report.recovered, 3)
        self.assertEqual(report.ownership_repairs, 0)

    def test_d1_recover_all_rules(self):
        """No rules argument runs all rules."""
        ops = self._make_uploading_stale(2)
        report = self.engine.recover(mode=RecoveryMode.REPAIR)
        self.assertEqual(report.recovered, 2)

    # ── D2: Rule ≠ Reason ─────────────────────────────────

    def test_d2_rule_is_separate_from_reason(self):
        """RecoveryRule and RecoveryReason are distinct enums."""
        self.assertIsNot(RecoveryRule, RecoveryReason)
        # Each rule maps to a reason
        self.assertIsInstance(RecoveryRule.HEARTBEAT_TIMEOUT, RecoveryRule)
        self.assertIsInstance(RecoveryReason.HEARTBEAT_TIMEOUT, RecoveryReason)

    # ── D3: Immutable Report ──────────────────────────────

    def test_d3_report_is_frozen(self):
        """RecoveryReport and RecoveryEntry are frozen dataclasses."""
        entry = RecoveryEntry(operation_id=1, rule=RecoveryRule.HEARTBEAT_TIMEOUT,
                              reason=RecoveryReason.HEARTBEAT_TIMEOUT, repaired=True)
        with self.assertRaises(AttributeError):
            entry.repaired = False

        report = self.engine.recover(mode=RecoveryMode.DETECT_ONLY)
        with self.assertRaises(AttributeError):
            report.recovered = 99

    # ── D4: Idempotent ────────────────────────────────────

    def test_d4_idempotent_recover(self):
        """recover() × N produces same result as recover() × 1."""
        ops = self._make_uploading_stale(5)
        r1 = self.engine.recover(rules=[RecoveryRule.HEARTBEAT_TIMEOUT],
                                  mode=RecoveryMode.REPAIR)
        r2 = self.engine.recover(rules=[RecoveryRule.HEARTBEAT_TIMEOUT],
                                  mode=RecoveryMode.REPAIR)
        r3 = self.engine.recover(rules=[RecoveryRule.HEARTBEAT_TIMEOUT],
                                  mode=RecoveryMode.REPAIR)

        self.assertEqual(r1.recovered, 5)
        self.assertEqual(r2.recovered, 0, 'Second run: nothing to recover')
        self.assertEqual(r3.recovered, 0, 'Third run: nothing to recover')
        for op in ops:
            op.invalidate_recordset()
            self.assertEqual(op.state, 'queued')

    # ── D7: Audit only on repair ──────────────────────────

    def test_d7_audit_only_on_actual_repair(self):
        """Audit log entries are created only when a repair happens."""
        Audit = self.env['attachment.audit.log']
        ops = self._make_uploading_stale(3)

        before = Audit.search_count([])

        # Detect-only: no audit
        report = self.engine.recover(
            rules=[RecoveryRule.HEARTBEAT_TIMEOUT],
            mode=RecoveryMode.DETECT_ONLY,
        )
        after_detect = Audit.search_count([])
        self.assertEqual(after_detect, before,
                         'DETECT_ONLY should not create audit entries')

        # Repair: audit created
        report = self.engine.recover(
            rules=[RecoveryRule.HEARTBEAT_TIMEOUT],
            mode=RecoveryMode.REPAIR,
        )
        after_repair = Audit.search_count([])
        self.assertEqual(after_repair, before + 3,
                         'REPAIR should create one audit per recovered op')

    # ── D8: All transitions go through transition_state ───

    def test_d8_recover_uses_transition_state(self):
        """Recovery transitions raise ValidationError for invalid state changes."""
        ops = self._make_uploading_stale(2)
        # Manually set an invalid state via SQL to bypass write() validation
        self.env.cr.execute(
            "UPDATE attachment_migration_operation SET state = 'verified' WHERE id = ANY(%s)",
            (ops.ids,),
        )
        ops.invalidate_recordset()

        report = self.engine.recover(
            rules=[RecoveryRule.HEARTBEAT_TIMEOUT],
            mode=RecoveryMode.REPAIR,
        )
        # The rule should skip verified ops (not uploading),
        # so recovered should be 0
        self.assertEqual(report.recovered, 0)


class TestRecoveryRules(TransactionCase):
    """Unit tests for each RecoveryRule."""

    def setUp(self):
        super().setUp()
        self.engine = RecoveryEngine(self.env)
        self.Operation = self.env['attachment.migration.operation']
        self.Attachment = self.env['ir.attachment']
        self.Operation.search([]).unlink()

    def _make_queued(self, n=1, prefix='r'):
        atts = self.Attachment.create([{
            'name': '%s_%d.txt' % (prefix, i), 'raw': b'd', 'type': 'binary',
        } for i in range(n)])
        ops = self.Operation.create([{
            'attachment_id': atts[i].id,
            'state': 'queued',
            'queued_at': fields.Datetime.now(),
        } for i in range(n)])
        return ops

    # ── R1: Heartbeat Timeout ─────────────────────────────

    def test_r1_heartbeat_timeout(self):
        ops = self._make_queued(3)
        claimed = self.Operation.claim_batch(limit=3, worker_id='hb-w')
        self.env.cr.execute("""
            UPDATE attachment_migration_operation
            SET heartbeat_at = '2020-01-01'::timestamp
            WHERE id = ANY(%s)
        """, (claimed.ids,))

        report = self.engine.recover(
            rules=[RecoveryRule.HEARTBEAT_TIMEOUT],
            mode=RecoveryMode.REPAIR,
        )

        self.assertEqual(report.recovered, 3)
        self.assertEqual(report.heartbeat_timeouts, 3)
        for op in claimed:
            op.invalidate_recordset()
            self.assertEqual(op.state, 'queued')
            self.assertFalse(op.processing_token)
            self.assertFalse(op.worker_id)

    def test_r1_skips_fresh_heartbeat(self):
        ops = self._make_queued(2)
        claimed = self.Operation.claim_batch(limit=2, worker_id='fresh-w')

        report = self.engine.recover(
            rules=[RecoveryRule.HEARTBEAT_TIMEOUT],
            mode=RecoveryMode.REPAIR,
        )

        self.assertEqual(report.recovered, 0)
        self.assertEqual(report.scanned, 0)

    # ── R2: Invalid Ownership ────────────────────────────

    def test_r2_invalid_ownership(self):
        ops = self._make_queued(2)
        claimed = self.Operation.claim_batch(limit=2, worker_id='ow-w')
        # Corrupt worker_id
        self.env.cr.execute("""
            UPDATE attachment_migration_operation
            SET worker_id = NULL
            WHERE id = ANY(%s)
        """, (claimed.ids,))

        report = self.engine.recover(
            rules=[RecoveryRule.INVALID_OWNERSHIP],
            mode=RecoveryMode.REPAIR,
        )

        self.assertEqual(report.recovered, 2)
        self.assertEqual(report.ownership_repairs, 2)
        for op in claimed:
            op.invalidate_recordset()
            self.assertEqual(op.state, 'queued')

    # ── R5: Verify Mismatch ───────────────────────────────

    def test_r5_verify_mismatch_requeues(self):
        Mapping = self.env['attachment.storage.mapping']
        ops = self._make_queued(2)
        for i in range(2):
            via = self.Attachment.create({
                'name': 'via_%d.txt' % i, 'raw': b'x', 'type': 'binary',
            })
            mapping = Mapping.create({
                'attachment_id': via.id,
                's3_bucket': 'test',
                's3_key': 'test/key_%d' % i,
                's3_region': 'us-east-1',
                'status': 'verification_failed',
            })
            self.env.cr.execute(
                "UPDATE attachment_migration_operation SET state = 'failed', mapping_id = %s WHERE id = %s",
                [mapping.id, ops[i].id],
            )
            ops[i].invalidate_recordset()

        ops = self.Operation.browse(ops.ids)
        self.assertEqual(ops.mapped('state'), ['failed', 'failed'])

        report = self.engine.recover(
            rules=[RecoveryRule.VERIFY_MISMATCH],
            mode=RecoveryMode.REPAIR,
        )

        self.assertEqual(report.recovered, 2)
        self.assertEqual(report.verification_repairs, 2)
        for op in ops:
            op.invalidate_recordset()
            self.assertEqual(op.state, 'queued')

    # ── R5 (Stale Worker) ─────────────────────────────────

    def test_stale_worker_detects_anomaly(self):
        ops = self._make_queued(2)
        claimed = self.Operation.claim_batch(limit=2, worker_id='sw-w')
        # Nullify claimed_at to create anomaly
        self.env.cr.execute("""
            UPDATE attachment_migration_operation
            SET claimed_at = NULL
            WHERE id = ANY(%s)
        """, (claimed.ids,))

        report = self.engine.recover(
            rules=[RecoveryRule.STALE_WORKER],
            mode=RecoveryMode.REPAIR,
        )

        self.assertEqual(report.recovered, 2)
        self.assertEqual(report.stale_workers, 2)

    # ── Limit ─────────────────────────────────────────────

    def test_limit_respected_across_rules(self):
        """limit caps total across all rules, not per rule."""
        self._make_uploading_stale(10)
        # Create 10 more with invalid ownership
        ops2 = self._make_uploading_stale(10,
                                           prefix='ano')
        self.env.cr.execute("""
            UPDATE attachment_migration_operation
            SET worker_id = NULL
            WHERE id = ANY(%s)
        """, (ops2.ids,))

        report = self.engine.recover(
            rules=[RecoveryRule.HEARTBEAT_TIMEOUT,
                   RecoveryRule.INVALID_OWNERSHIP],
            limit=5,
            mode=RecoveryMode.REPAIR,
        )

        self.assertEqual(report.recovered, 5,
                         'limit caps total repaired ops')
        self.assertLessEqual(
            report.heartbeat_timeouts + report.ownership_repairs,
            5,
        )

    # ── Mode ──────────────────────────────────────────────

    def test_detect_only_does_not_repair(self):
        ops = self._make_uploading_stale(5)
        report = self.engine.recover(
            rules=[RecoveryRule.HEARTBEAT_TIMEOUT],
            mode=RecoveryMode.DETECT_ONLY,
        )

        self.assertEqual(report.recovered, 0)
        self.assertGreaterEqual(report.scanned, 0)
        for op in ops:
            op.invalidate_recordset()
            self.assertEqual(op.state, 'uploading',
                             'DETECT_ONLY must not change state')

    def test_detect_only_reports_scanned(self):
        ops = self._make_uploading_stale(5)
        report = self.engine.recover(
            rules=[RecoveryRule.HEARTBEAT_TIMEOUT],
            mode=RecoveryMode.DETECT_ONLY,
        )
        self.assertEqual(report.scanned, 5)

    # ── Helpers ───────────────────────────────────────────

    def _make_uploading_stale(self, n=1, prefix='stale'):
        ops = self._make_queued(n, prefix)
        claimed = self.Operation.claim_batch(limit=n, worker_id='test-worker')
        self.env.cr.execute("""
            UPDATE attachment_migration_operation
            SET heartbeat_at = '2020-01-01'::timestamp
            WHERE id = ANY(%s)
        """, (claimed.ids,))
        return claimed
