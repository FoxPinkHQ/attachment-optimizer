from odoo.tests import TransactionCase
from odoo.exceptions import AccessError
from odoo.tools import mute_logger


class TestSecurity(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group = cls.env.ref(
            'attachment_optimizer.group_storage_optimization_manager'
        )
        cls.manager = cls.env['res.users'].create({
            'name': 'Sec Mgr',
            'login': 'security_manager',
            'groups_id': [(4, cls.env.ref('base.group_user').id), (4, group.id)],
        })
        cls.non_manager = cls.env['res.users'].create({
            'name': 'Sec Emp',
            'login': 'security_employee',
            'groups_id': [(4, cls.env.ref('base.group_user').id)],
        })
        cls.attachment = cls.env['ir.attachment'].create({
            'name': 'security_test.txt',
            'raw': b'security test',
            'type': 'binary',
        })

    # -- Menu ACL --

    def _visible_to(self, menu, user):
        return bool(self.env['ir.ui.menu'].with_user(user).search([('id', '=', menu.id)]))

    def test_01_non_manager_cannot_see_storage_mapping_menu(self):
        """Menu invisible to non_manager because model ACL restricts access."""
        menu = self.env.ref('attachment_optimizer.attachment_storage_mapping_menu')
        self.assertFalse(self._visible_to(menu, self.non_manager))

    def test_02_non_manager_cannot_see_dashboard_menu(self):
        menu = self.env.ref('attachment_optimizer.foxpink_dashboard_menu')
        self.assertFalse(self._visible_to(menu, self.non_manager))

    def test_03_non_manager_cannot_see_audit_menu(self):
        menu = self.env.ref('attachment_optimizer.foxpink_audit_log_menu')
        self.assertFalse(self._visible_to(menu, self.non_manager))

    # -- Model ACL --

    def test_04_non_manager_cannot_read_storage_mapping(self):
        mapping = self.env['attachment.storage.mapping'].create({
            'attachment_id': self.attachment.id,
            's3_bucket': 'test',
            's3_key': 'test',
            's3_region': 'us-east-1',
        })
        with self.assertRaises(AccessError), mute_logger('odoo.addons.base.models.ir_model'):
            self.env['attachment.storage.mapping'].with_user(
                self.non_manager
            ).search([('id', '=', mapping.id)])

    def test_05_non_manager_cannot_read_migration_operation(self):
        op = self.env['attachment.migration.operation'].create({
            'attachment_id': self.attachment.id,
        })
        with self.assertRaises(AccessError), mute_logger('odoo.addons.base.models.ir_model'):
            self.env['attachment.migration.operation'].with_user(
                self.non_manager
            ).search([('id', '=', op.id)])

    def test_06_non_manager_cannot_read_audit_log(self):
        audit = self.env['attachment.audit.log']._log(
            action='analyze', attachment_id=self.attachment.id,
        )
        with self.assertRaises(AccessError), mute_logger('odoo.addons.base.models.ir_model'):
            self.env['attachment.audit.log'].with_user(
                self.non_manager
            ).search([('id', '=', audit.id)])

    # -- Audit immutability (model-level, not just ACL) --

    def test_07_audit_log_cannot_be_written(self):
        audit = self.env['attachment.audit.log']._log(
            action='analyze', attachment_id=self.attachment.id,
        )
        with self.assertRaises(AccessError):
            audit.write({'error_message': 'tampered'})

    def test_08_audit_log_cannot_be_deleted(self):
        audit = self.env['attachment.audit.log']._log(
            action='analyze', attachment_id=self.attachment.id,
        )
        with self.assertRaises(AccessError):
            audit.unlink()

    # -- Read flow ACL --

    def test_09_read_flow_respects_attachment_acl(self):
        """User without attachment read access must not get stream."""
        no_access_user = self.env['res.users'].create({
            'name': 'No Read',
            'login': 'no_read_acl',
            'groups_id': [(6, 0, [])],
        })
        env = self.env(user=no_access_user)
        binary = env['ir.binary']
        record = env['ir.attachment'].browse(self.attachment.id)
        stream = binary._get_stream_from(record, 'datas')
        self.assertIsNone(stream)
