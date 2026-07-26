from odoo.tests import TransactionCase
from odoo.exceptions import ValidationError


class TestStorageMapping(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Mapping = cls.env['attachment.storage.mapping']
        cls.Attachment = cls.env['ir.attachment']

        cls.attachment = cls.Attachment.create({
            'name': 'test_doc.pdf',
            'raw': b'fake binary content for testing',
        })

    def _create_mapping(self, attachment=None):
        return self.Mapping.create_mapping(
            attachment_id=attachment or self.attachment.id,
            s3_bucket='test-bucket',
            s3_key='attachments/test_doc.pdf',
            s3_region='us-east-1',
        )

    def test_01_create_mapping(self):
        mapping = self._create_mapping()
        self.assertEqual(mapping.attachment_id.id, self.attachment.id)
        self.assertEqual(mapping.s3_bucket, 'test-bucket')
        self.assertEqual(mapping.s3_key, 'attachments/test_doc.pdf')
        self.assertEqual(mapping.s3_region, 'us-east-1')
        self.assertEqual(mapping.status, 'pending')

    def test_02_prevent_duplicate_mapping(self):
        self._create_mapping()
        with self.assertRaises(ValidationError):
            self._create_mapping()

    def test_03_lookup_by_attachment(self):
        mapping = self._create_mapping()
        found = self.Mapping.lookup_by_attachment(self.attachment.id)
        self.assertEqual(found.id, mapping.id)

    def test_04_lookup_nonexistent_attachment(self):
        result = self.Mapping.lookup_by_attachment(999999)
        self.assertFalse(result)

    def test_05_get_external_location_before_migration(self):
        mapping = self._create_mapping()
        location = self.Mapping.get_external_location(self.attachment.id)
        self.assertIsNone(location)

    def test_06_get_external_location_after_finalize(self):
        mapping = self._create_mapping()
        mapping.action_update_status('uploading')
        mapping.action_update_status('uploaded')
        mapping.action_update_status('verified', checksum='abc123')
        mapping.action_update_status('finalized')
        location = self.Mapping.get_external_location(self.attachment.id)
        self.assertEqual(location['bucket'], 'test-bucket')
        self.assertEqual(location['key'], 'attachments/test_doc.pdf')
        self.assertEqual(location['region'], 'us-east-1')
        self.assertEqual(location['checksum'], 'abc123')

    def test_07_full_lifecycle_transitions(self):
        mapping = self._create_mapping()
        self.assertEqual(mapping.status, 'pending')
        mapping.action_update_status('uploading')
        self.assertEqual(mapping.status, 'uploading')
        mapping.action_update_status('uploaded')
        self.assertEqual(mapping.status, 'uploaded')
        mapping.action_update_status('verified', checksum='def456')
        self.assertEqual(mapping.status, 'verified')
        self.assertEqual(mapping.checksum_sha256, 'def456')
        self.assertTrue(mapping.verification_timestamp)
        mapping.action_update_status('finalized')
        self.assertEqual(mapping.status, 'finalized')

    def test_08_upload_failure_transition(self):
        mapping = self._create_mapping()
        mapping.action_update_status('uploading')
        mapping.action_update_status('failed', error='Connection timeout')
        self.assertEqual(mapping.status, 'failed')
        self.assertEqual(mapping.error_message, 'Connection timeout')
        mapping.action_reset()
        self.assertEqual(mapping.status, 'pending')

    def test_09_verification_failure_transition(self):
        mapping = self._create_mapping()
        mapping.action_update_status('uploading')
        mapping.action_update_status('uploaded')
        mapping.action_update_status('verification_failed', error='Checksum mismatch')
        self.assertEqual(mapping.status, 'verification_failed')
        self.assertEqual(mapping.error_message, 'Checksum mismatch')
        mapping.action_reset()
        self.assertEqual(mapping.status, 'pending')

    def test_10_invalid_transition_raises_error(self):
        mapping = self._create_mapping()
        with self.assertRaises(ValidationError):
            mapping.action_update_status('finalized')

    def test_11_get_external_location_return_none_for_failed(self):
        mapping = self._create_mapping()
        mapping.action_update_status('uploading')
        mapping.action_mark_failed('Connection timeout')
        location = self.Mapping.get_external_location(self.attachment.id)
        self.assertIsNone(location)

    def test_12_uninstall_isolation(self):
        mapping = self._create_mapping()
        mapping.unlink()
        remaining = self.Mapping.search([
            ('attachment_id', '=', self.attachment.id),
        ])
        self.assertFalse(remaining)

    def test_13_sql_constraint_unique_attachment(self):
        self._create_mapping()
        with self.assertRaises(Exception):
            self.Mapping.create({
                'attachment_id': self.attachment.id,
                's3_bucket': 'another-bucket',
                's3_key': 'another-key',
                's3_region': 'eu-west-1',
            })

    def test_14_cannot_finalize_without_verification(self):
        mapping = self._create_mapping()
        mapping.action_update_status('uploading')
        mapping.action_update_status('uploaded')
        with self.assertRaises(ValidationError):
            mapping.action_update_status('finalized')

    def test_15_mapping_unlink_does_not_delete_attachment(self):
        mapping = self._create_mapping()
        attachment_id = mapping.attachment_id.id
        mapping.unlink()
        self.assertTrue(
            self.env['ir.attachment'].browse(attachment_id).exists(),
        )
