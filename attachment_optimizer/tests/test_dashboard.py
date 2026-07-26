from odoo.tests import TransactionCase


class TestDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ICP = cls.env['ir.config_parameter'].sudo()
        ICP.set_param('attachment_storage.s3.bucket', 'test-bucket')
        ICP.set_param('attachment_storage.s3.region', 'us-east-1')
        ICP.set_param('attachment_storage.s3.access_key_id', 'testing')
        ICP.set_param('attachment_storage.s3.secret_access_key', 'testing')
        group = cls.env.ref(
            'attachment_optimizer.group_storage_optimization_manager'
        )
        cls.manager = cls.env['res.users'].create({
            'name': 'Manager',
            'login': 'dashboard_manager',
            'groups_id': [(4, cls.env.ref('base.group_user').id), (4, group.id)],
        })
        cls.non_manager = cls.env['res.users'].create({
            'name': 'Employee',
            'login': 'dashboard_employee',
            'groups_id': [(4, cls.env.ref('base.group_user').id)],
        })
        cls.menu_dashboard = cls.env.ref(
            'attachment_optimizer.attachment_optimizer_dashboard_menu'
        )
        cls.menu_migration = cls.env.ref(
            'attachment_optimizer.attachment_optimizer_migration_operation_menu'
        )
        cls.menu_mapping = cls.env.ref(
            'attachment_optimizer.attachment_storage_mapping_menu'
        )

    def _visible_to(self, menu, user):
        menus = self.env['ir.ui.menu'].with_user(user).search(
            [('id', '=', menu.id)]
        )
        return bool(menus)

    def test_01_dashboard_menu_visible_to_manager(self):
        self.assertTrue(self._visible_to(self.menu_dashboard, self.manager))

    def test_02_dashboard_menu_hidden_from_non_manager(self):
        self.assertFalse(self._visible_to(self.menu_dashboard, self.non_manager))

    def test_03_migration_operation_menu_visible_to_manager(self):
        self.assertTrue(self._visible_to(self.menu_migration, self.manager))

    def test_04_migration_operation_menu_hidden_from_non_manager(self):
        self.assertFalse(self._visible_to(self.menu_migration, self.non_manager))

    def test_05_storage_mapping_menu_visible_to_manager(self):
        self.assertTrue(self._visible_to(self.menu_mapping, self.manager))

    def test_06_analyze_and_queue_returns_notification(self):
        result = self.env[
            'attachment.migration.operation'
        ].with_user(self.manager).action_analyze_and_queue()
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['tag'], 'display_notification')

    def test_07_retry_all_failed_returns_notification_when_none_failed(self):
        result = self.env[
            'attachment.migration.operation'
        ].with_user(self.manager).action_retry_all_failed()
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['tag'], 'display_notification')

    def test_08_retry_all_failed_returns_notification_when_failed_exist(self):
        op = self.env['attachment.migration.operation'].create({
            'attachment_id': self.env['ir.attachment'].create({
                'name': 'retry_test.txt',
                'raw': b'test',
                'type': 'binary',
            }).id,
            'state': 'failed',
            'error_message': 'test error',
        })
        result = self.env[
            'attachment.migration.operation'
        ].with_user(self.manager).action_retry_all_failed()
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['tag'], 'display_notification')
        self.assertIn('re-queued', result['params']['message'])
