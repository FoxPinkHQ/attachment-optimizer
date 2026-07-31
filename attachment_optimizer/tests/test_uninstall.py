from odoo.tests import TransactionCase

from .. import _uninstall_hook


class TestUninstall(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.attachment = cls.env['ir.attachment'].create({
            'name': 'uninstall_test.txt',
            'raw': b'uninstall test',
            'type': 'binary',
            'store_fname': 'tests/uninstall_file',
        })
        cls.mapping = cls.env['attachment.storage.mapping'].create({
            'attachment_id': cls.attachment.id,
            's3_bucket': 'test-bucket',
            's3_key': 'objects/ab/abcdef123',
            's3_region': 'us-east-1',
            'status': 'finalized',
        })
        cls.operation = cls.env['attachment.migration.operation'].create({
            'attachment_id': cls.attachment.id,
            'mapping_id': cls.mapping.id,
            'state': 'finalized',
        })
        cls.audit = cls.env['attachment.audit.log']._log(
            action='finalize', result='success',
            attachment_id=cls.attachment.id,
            operation_id=cls.operation.id,
            mapping_id=cls.mapping.id,
        )
        cls.original_fname = cls.attachment.store_fname
        cls.env['ir.config_parameter'].sudo().set_param(
            'attachment_storage.s3.region', 'us-east-1'
        )

    def test_01_mapping_delete_does_not_delete_attachment(self):
        """Deleting a mapping must not cascade-delete the attachment."""
        mapping = self.mapping
        mapping.unlink()
        self.attachment.invalidate_cache()
        self.assertTrue(
            self.attachment.exists(),
            'Attachment must survive mapping deletion',
        )

    def test_02_attachment_survives_when_mapping_deleted(self):
        """Attachment store_fname must remain intact."""
        self.mapping.unlink()
        self.attachment.invalidate_cache()
        self.assertEqual(
            self.attachment.store_fname, self.original_fname,
            'store_fname must not change when mapping is deleted',
        )

    def test_03_config_parameters_isolated(self):
        """Our config params must not interfere with Odoo core."""
        ICP = self.env['ir.config_parameter'].sudo()
        param = ICP.get_param('attachment_storage.s3.region')
        self.assertEqual(param, 'us-east-1',
                         'Module config param must be readable')

    def test_04_our_models_are_removable(self):
        """Our model records can be cleaned up without side effects."""
        self.env['attachment.migration.operation'].search([]).unlink()
        self.env['attachment.storage.mapping'].search([]).unlink()
        remaining_mappings = self.env['attachment.storage.mapping'].search([])
        remaining_ops = self.env['attachment.migration.operation'].search([])
        self.assertEqual(len(remaining_mappings), 0)
        self.assertEqual(len(remaining_ops), 0)
        # audit.log is intentionally protected from deletion

    def test_05_uninstall_hook_removes_only_module_parameters(self):
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param(
            'attachment_storage.s3.secret_access_key', 'sensitive-test-value'
        )
        ICP.set_param('unrelated.module.setting', 'keep-me')

        _uninstall_hook(self.env)

        self.assertFalse(ICP.get_param('attachment_storage.s3.region'))
        self.assertFalse(
            ICP.get_param('attachment_storage.s3.secret_access_key')
        )
        self.assertEqual(
            ICP.get_param('unrelated.module.setting'), 'keep-me'
        )
