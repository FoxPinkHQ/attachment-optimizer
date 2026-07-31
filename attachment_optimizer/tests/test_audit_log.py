from odoo.tests import SavepointCase
from odoo.exceptions import AccessError
from odoo.tools import mute_logger


class TestAuditLog(SavepointCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group = cls.env.ref(
            'attachment_optimizer.group_storage_optimization_manager'
        )
        cls.manager = cls.env['res.users'].create({
            'name': 'Audit Mgr',
            'login': 'audit_manager',
            'groups_id': [(4, cls.env.ref('base.group_user').id), (4, group.id)],
        })
        cls.non_manager = cls.env['res.users'].create({
            'name': 'Audit Emp',
            'login': 'audit_employee',
            'groups_id': [(4, cls.env.ref('base.group_user').id)],
        })
        cls.attachment = cls.env['ir.attachment'].create({
            'name': 'audit_test.txt',
            'raw': b'audit test',
            'type': 'binary',
            'store_fname': 'tests/audit_file',
        })

    def _log(self, **kw):
        vals = {
            'action': 'analyze',
            'attachment_id': self.attachment.id,
        }
        vals.update(kw)
        return self.env['attachment.audit.log']._log(**vals)

    def test_01_analyze_log_created(self):
        audit = self._log(action='analyze')
        self.assertEqual(audit.action, 'analyze')
        self.assertEqual(audit.result, 'success')

    def test_02_migration_queue_created_log(self):
        audit = self._log(action='migration_queue_created')
        self.assertEqual(audit.action, 'migration_queue_created')

    def test_03_queue_log_with_attachment(self):
        audit = self._log(
            action='queue', attachment_id=self.attachment.id,
        )
        self.assertEqual(audit.attachment_id.id, self.attachment.id)

    def test_04_upload_verify_finalize_logs_created(self):
        upload = self._log(action='upload')
        verify = self._log(action='verify')
        finalize = self._log(action='finalize')
        self.assertEqual(upload.action, 'upload')
        self.assertEqual(verify.action, 'verify')
        self.assertEqual(finalize.action, 'finalize')

    def test_05_retry_cancel_logs_created(self):
        retry = self._log(action='retry')
        cancel = self._log(action='cancel')
        self.assertEqual(retry.action, 'retry')
        self.assertEqual(cancel.action, 'cancel')

    def test_06_failure_log_includes_error(self):
        audit = self._log(
            action='upload', result='failure',
            error_message='Connection refused',
        )
        self.assertEqual(audit.result, 'failure')
        self.assertEqual(audit.error_message, 'Connection refused')

    def test_07_manager_can_read_audit_log(self):
        audit = self._log(action='analyze')
        logs = self.env['attachment.audit.log'].with_user(
            self.manager
        ).search([('id', '=', audit.id)])
        self.assertTrue(logs)

    def test_08_non_manager_cannot_read_audit_log(self):
        audit = self._log(action='analyze')
        with self.assertRaises(AccessError), mute_logger('odoo.addons.base.models.ir_model'):
            self.env['attachment.audit.log'].with_user(
                self.non_manager
            ).search([('id', '=', audit.id)])

    def test_09_audit_record_cannot_be_modified(self):
        audit = self._log(action='analyze')
        with self.assertRaises(AccessError):
            audit.write({'error_message': 'tampered'})

    def test_10_audit_record_cannot_be_deleted(self):
        audit = self._log(action='analyze')
        with self.assertRaises(AccessError):
            audit.unlink()
