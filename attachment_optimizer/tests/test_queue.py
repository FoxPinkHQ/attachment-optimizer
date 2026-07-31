from odoo import fields, api, sql_db
from odoo.tests import TransactionCase
from odoo.exceptions import ValidationError
from ..services.recovery_engine import (
    RecoveryEngine, RecoveryMode, RecoveryRule, RecoveryReason,
)


class TestQueueConcurrency(TransactionCase):
    """Phase 2 Queue Layer tests — claim_batch, heartbeat, ownership lifecycle."""

    def setUp(self):
        super().setUp()
        self.env['attachment.migration.operation'].search([]).unlink()

    def _create_queued_ops(self, n, prefix='qt'):
        Operation = self.env['attachment.migration.operation']
        Attachment = self.env['ir.attachment']
        ids = []
        for i in range(n):
            att = Attachment.create({
                'name': '%s_%d.txt' % (prefix, i), 'raw': b'd', 'type': 'binary',
            })
            op = Operation.create({
                'attachment_id': att.id, 'state': 'queued',
                'queued_at': fields.Datetime.now(),
            })
            ids.append(op.id)
        return ids

    def test_01_claim_batch_sets_state_and_ownership(self):
        ids = self._create_queued_ops(5)
        Operation = self.env['attachment.migration.operation']

        claimed = Operation.claim_batch(limit=3, worker_id='test-worker')
        self.assertEqual(len(claimed), 3)
        for op in claimed:
            self.assertEqual(op.state, 'uploading')
            self.assertEqual(op.worker_id, 'test-worker')
            self.assertTrue(op.processing_token)
            self.assertTrue(op.claimed_at)
            self.assertTrue(op.heartbeat_at)
            self.assertTrue(op.started_at)

        remaining = Operation.search([('state', '=', 'queued')])
        self.assertEqual(len(remaining), 2)

    def test_02_claim_batch_respects_limit(self):
        self._create_queued_ops(20)
        Operation = self.env['attachment.migration.operation']

        batch1 = Operation.claim_batch(limit=7, worker_id='w1')
        self.assertEqual(len(batch1), 7)
        batch2 = Operation.claim_batch(limit=7, worker_id='w2')
        self.assertEqual(len(batch2), 7)
        batch3 = Operation.claim_batch(limit=7, worker_id='w3')
        self.assertEqual(len(batch3), 6)

        workers = set()
        for op in batch1 | batch2 | batch3:
            workers.add(op.worker_id)
            self.assertEqual(op.state, 'uploading')
        self.assertEqual(workers, {'w1', 'w2', 'w3'})

    def test_03_no_duplicate_claims(self):
        ids = set(self._create_queued_ops(10))
        Operation = self.env['attachment.migration.operation']

        claimed_ids = set()
        for i in range(3):
            batch = Operation.claim_batch(limit=5, worker_id='w%d' % i)
            for op in batch:
                self.assertNotIn(op.id, claimed_ids, 'Duplicate claim')
                claimed_ids.add(op.id)
        self.assertEqual(claimed_ids, ids)

    def test_04_claim_batch_returns_empty_when_none_queued(self):
        Operation = self.env['attachment.migration.operation']
        claimed = Operation.claim_batch(limit=10, worker_id='w1')
        self.assertEqual(len(claimed), 0)

    def test_05_heartbeat_validates_token(self):
        ids = self._create_queued_ops(2)
        Operation = self.env['attachment.migration.operation']

        claimed = Operation.claim_batch(limit=2, worker_id='hb-test')
        op1, op2 = claimed[0], claimed[1]

        Operation.heartbeat(op1.id, op1.processing_token)
        Operation.heartbeat(op2.id, op2.processing_token)

        with self.assertRaises(ValidationError):
            Operation.heartbeat(op1.id, 'wrong-token')

    def test_06_heartbeat_fails_for_non_uploading_op(self):
        Operation = self.env['attachment.migration.operation']
        att = self.env['ir.attachment'].create({
            'name': 'hb_fail.txt', 'raw': b'd', 'type': 'binary',
        })
        op = Operation.create({
            'attachment_id': att.id, 'state': 'queued',
        })

        with self.assertRaises(ValidationError):
            Operation.heartbeat(op.id, 'any-token')

    def test_07_recover_clears_ownership_and_state_goes_queued(self):
        ids = self._create_queued_ops(3)
        Operation = self.env['attachment.migration.operation']
        claimed = Operation.claim_batch(limit=3, worker_id='to-recover')

        self.env.cr.execute("""
            UPDATE attachment_migration_operation
            SET heartbeat_at = '2020-01-01'::timestamp
            WHERE id = ANY(%s)
        """, (claimed.ids,))

        engine = RecoveryEngine(self.env)
        report = engine.recover(
            rules=[RecoveryRule.HEARTBEAT_TIMEOUT],
            mode=RecoveryMode.REPAIR,
        )
        self.assertEqual(report.recovered, 3)

        for op in claimed:
            op.invalidate_recordset()
            self.assertEqual(op.state, 'queued')
            self.assertFalse(op.processing_token)
            self.assertFalse(op.worker_id)
            self.assertFalse(op.claimed_at)
            self.assertFalse(op.heartbeat_at)

        re_claimed = Operation.claim_batch(limit=3, worker_id='recovered')
        self.assertEqual(len(re_claimed), 3)

    def test_08_ownership_cleared_on_terminal_transition(self):
        Operation = self.env['attachment.migration.operation']
        ids = self._create_queued_ops(2)
        claimed = Operation.claim_batch(limit=2, worker_id='owner-check')

        for op in claimed:
            op.transition_state('failed', completed_at=fields.Datetime.now())
            self.assertFalse(op.processing_token)
            self.assertFalse(op.worker_id)
            self.assertFalse(op.claimed_at)
            self.assertFalse(op.heartbeat_at)
            self.assertFalse(op.is_active)

    def test_09_retry_creates_claimable_operation(self):
        Operation = self.env['attachment.migration.operation']
        att = self.env['ir.attachment'].create({
            'name': 'retry_claimable.txt', 'raw': b'd', 'type': 'binary',
        })
        old_op = Operation.create({
            'attachment_id': att.id, 'state': 'failed',
            'error_message': 'first failure',
        })

        created = old_op._retry_operations()
        self.assertEqual(len(created), 1)
        new_op = created[0]
        self.assertEqual(new_op.state, 'queued')
        self.assertEqual(new_op.retry_of.id, old_op.id)
        self.assertEqual(new_op.root_operation_id.id, old_op.id)
        self.assertEqual(new_op.attempt, 2)

        claimed = Operation.claim_batch(limit=10, worker_id='retry-worker')
        self.assertIn(new_op.id, claimed.ids)
        self.assertNotIn(old_op.id, claimed.ids)
        self.assertEqual(old_op.state, 'failed')

    def test_09b_retry_button_opens_new_operation(self):
        attachment = self.env['ir.attachment'].create({
            'name': 'retry_feedback.txt', 'raw': b'd', 'type': 'binary',
        })
        operation = self.env['attachment.migration.operation'].create({
            'attachment_id': attachment.id, 'state': 'failed',
            'error_message': 'first failure',
        })

        action = operation.action_retry()

        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(
            action['res_model'], 'attachment.migration.operation'
        )
        self.assertTrue(action['res_id'])

    def test_10_create_queue_single_sql_no_duplicate(self):
        Operation = self.env['attachment.migration.operation']
        Attachment = self.env['ir.attachment']
        att = Attachment.create({
            'name': 'createq_test.txt', 'raw': b'd', 'type': 'binary',
        })

        ops1 = Operation.create_queue([att.id])
        self.assertEqual(len(ops1), 1)
        self.assertEqual(ops1.state, 'queued')

        ops2 = Operation.create_queue([att.id])
        self.assertEqual(len(ops2), 0)

    def test_11_upload_button_returns_notification_and_reload(self):
        attachment = self.env['ir.attachment'].create({
            'name': 'missing_binary.txt', 'type': 'binary',
        })
        operation = self.env['attachment.migration.operation'].create({
            'attachment_id': attachment.id,
            'state': 'queued',
        })

        action = operation.action_upload()

        self.assertEqual(operation.state, 'failed')
        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(action['params']['next']['tag'], 'reload')

    def test_12_cancel_queued_operation_and_retry(self):
        attachment = self.env['ir.attachment'].create({
            'name': 'cancel_test.txt', 'raw': b'd', 'type': 'binary',
        })
        operation = self.env['attachment.migration.operation'].create({
            'attachment_id': attachment.id,
            'state': 'queued',
        })

        action = operation.action_cancel()

        self.assertEqual(operation.state, 'cancelled')
        self.assertFalse(operation.is_active)
        self.assertTrue(operation.completed_at)
        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(action['params']['next']['tag'], 'reload')
        audit = self.env['attachment.audit.log'].search([
            ('operation_id', '=', operation.id),
            ('action', '=', 'cancel'),
        ])
        self.assertEqual(len(audit), 1)

        retry_action = operation.action_retry()
        self.assertEqual(retry_action['type'], 'ir.actions.act_window')
        retry = self.env['attachment.migration.operation'].browse(
            retry_action['res_id']
        )
        self.assertEqual(retry.state, 'queued')
        self.assertEqual(retry.retry_of, operation)


class TestQueueStress(TransactionCase):
    """Overlapping-transaction concurrency — no threading needed.

    Opens separate DB connections sequentially, overlapping their transactions
    so FOR UPDATE SKIP LOCKED resolves contention correctly.

    Data is seeded via raw SQL (bulk insert) and committed so all connections
    can see it.
    """

    def setUp(self):
        super().setUp()
        db = sql_db.db_connect(self.env.cr.dbname)
        with db.cursor() as cr:
            env = api.Environment(cr, self.env.uid, self.env.context)
            env['attachment.migration.operation'].search([]).unlink()
            cr.commit()

    def _seed_data(self, n, prefix='stress'):
        db = sql_db.db_connect(self.env.cr.dbname)
        uid = self.env.uid
        with db.cursor() as cr:
            env = api.Environment(cr, uid, self.env.context)
            cid = env.company.id
            cr.execute("""
                INSERT INTO ir_attachment
                    (name, type, db_datas, store_fname, company_id, create_uid, create_date, write_uid, write_date)
                SELECT
                    %s || '_' || g || '.txt', 'binary', '\\x64', NULL,
                    %s, %s, NOW(), %s, NOW()
                FROM generate_series(0, %s-1) g
                RETURNING id
            """, (prefix, cid, uid, uid, n))
            att_ids = [r[0] for r in cr.fetchall()]
            cr.execute("""
                INSERT INTO attachment_migration_operation
                    (attachment_id, company_id, state, queued_at, create_uid, create_date, write_uid, write_date)
                SELECT
                    unnest(%s::int[]), %s, 'queued', NOW(), %s, NOW(), %s, NOW()
                RETURNING id
            """, (att_ids, cid, uid, uid))
            op_ids = [r[0] for r in cr.fetchall()]
            cr.commit()
        return op_ids

    def _claim_in_tx(self, db_name, uid, limit, worker_id):
        """Open a new connection, claim, return (ids, cursor) — cursor NOT committed."""
        db = sql_db.db_connect(db_name)
        cr = db.cursor()
        env = api.Environment(cr, uid, {})
        claimed = env['attachment.migration.operation'].claim_batch(
            limit=limit, worker_id=worker_id,
        )
        return list(claimed.ids), cr

    def test_overlapping_tx_claim_no_duplicate(self):
        """Overlapping TX: C1 holds lock, C2 SKIP LOCKED claims remaining."""
        total_ops = 100
        db_name = self.env.cr.dbname
        uid = self.env.uid

        # Seed data
        op_ids = set(self._seed_data(total_ops, 'overlap'))

        # C1: claim 40 ops, hold transaction (don't commit)
        batch1_ids, cr1 = self._claim_in_tx(db_name, uid, 40, 'c1')

        # C2: claim remaining — FOR UPDATE SKIP LOCKED skips C1's locked rows
        batch2_ids, cr2 = self._claim_in_tx(db_name, uid, 999, 'c2')

        # Commit both
        cr1.commit()
        cr1.close()
        cr2.commit()
        cr2.close()

        claimed = set(batch1_ids) | set(batch2_ids)

        self.assertEqual(len(batch1_ids), 40,
                         'C1 should claim 40')
        self.assertEqual(len(batch2_ids), total_ops - 40,
                         'C2 should claim remaining 60')
        self.assertEqual(len(claimed), total_ops,
                         'All ops claimed exactly once')
        self.assertEqual(claimed, op_ids,
                         'Every seeded op is claimed')

    def test_overlapping_tx_three_workers_no_duplicate(self):
        """3 overlapping TXs: each claims, no overlap, all claimed."""
        total_ops = 300
        db_name = self.env.cr.dbname
        uid = self.env.uid
        op_ids = set(self._seed_data(total_ops, 'overlap3'))

        limits = [100, 150, 999]  # C3 gets remaining 50
        cursors = []
        batch_ids_list = []

        for i, lim in enumerate(limits):
            ids, cr = self._claim_in_tx(db_name, uid, lim, 'c%d' % i)
            batch_ids_list.append(ids)
            cursors.append(cr)

        for cr in cursors:
            cr.commit()
            cr.close()

        all_claimed = set()
        for i, ids in enumerate(batch_ids_list):
            self.assertTrue(
                len(ids) > 0,
                'Worker %d should claim some ops' % i,
            )
            self.assertFalse(
                all_claimed & set(ids),
                'No duplicate claims for worker %d' % i,
            )
            all_claimed |= set(ids)

        self.assertEqual(len(all_claimed), total_ops,
                         'All ops claimed')
        self.assertEqual(all_claimed, op_ids)
