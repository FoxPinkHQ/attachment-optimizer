from odoo.tests import SavepointCase


class TestDashboard(SavepointCase):

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
        menu_groups = menu.sudo().groups_id
        if not menu_groups:
            return True
        return bool(menu_groups & user.groups_id)

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

    def test_06b_analyze_storage_does_not_create_queue(self):
        Operation = self.env['attachment.migration.operation']
        before = Operation.search_count([])
        result = Operation.with_user(self.manager).action_analyze_storage()
        self.assertEqual(result['tag'], 'display_notification')
        self.assertEqual(Operation.search_count([]), before)
        self.assertIn('No queue was created', result['params']['message'])

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

    def test_09_total_attachments_excludes_view_assets(self):
        eligible = self.env['ir.attachment'].create({
            'name': 'eligible.txt',
            'raw': b'eligible',
            'type': 'binary',
            'res_model': 'res.partner',
        })
        excluded = self.env['ir.attachment'].create({
            'name': 'generated-asset.js',
            'raw': b'generated',
            'type': 'binary',
            'res_model': 'ir.ui.view',
        })

        data = self.env[
            'attachment.storage.mapping'
        ].action_get_dashboard_data()

        self.assertTrue(eligible.store_fname)
        self.assertTrue(excluded.store_fname)
        expected = self.env['ir.attachment'].search_count([
            ('type', '=', 'binary'),
            ('store_fname', '!=', False),
            ('res_model', '!=', 'ir.ui.view'),
            ('company_id', 'in', [False] + self.env.companies.ids),
        ])
        self.assertEqual(data['total_attachments'], expected)

    def test_09b_total_attachments_excludes_other_companies(self):
        other_company = self.env['res.company'].create({
            'name': 'Dashboard Other Company',
        })
        self.env['ir.attachment'].sudo().create({
            'name': 'foreign-company.txt',
            'raw': b'foreign',
            'type': 'binary',
            'company_id': other_company.id,
        })

        scoped_env = self.env(
            context=dict(
                self.env.context,
                allowed_company_ids=[self.env.company.id],
            )
        )
        data = scoped_env[
            'attachment.storage.mapping'
        ].action_get_dashboard_data()

        expected = scoped_env['ir.attachment'].sudo().search_count([
            ('type', '=', 'binary'),
            ('store_fname', '!=', False),
            ('res_model', '!=', 'ir.ui.view'),
            ('company_id', 'in', [False] + scoped_env.companies.ids),
        ])
        self.assertEqual(data['total_attachments'], expected)

    def test_10_manager_can_load_dashboard_with_attachment_operations(self):
        attachment = self.env['ir.attachment'].create({
            'name': 'manager-dashboard.txt',
            'raw': b'dashboard',
            'type': 'binary',
            'company_id': self.env.company.id,
        })
        self.env['attachment.migration.operation'].create({
            'attachment_id': attachment.id,
            'company_id': self.env.company.id,
            'state': 'failed',
        })

        data = self.env[
            'attachment.storage.mapping'
        ].with_user(self.manager).action_get_dashboard_data()

        self.assertIn('recent_operations', data)
        self.assertIn(
            'manager-dashboard.txt',
            [operation['attachment_name'] for operation in data['recent_operations']],
        )
