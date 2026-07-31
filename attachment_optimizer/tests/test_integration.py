import hashlib

from odoo.tests import SavepointCase


class TestIntegration(SavepointCase):

    def setUp(self):
        super().setUp()
        self.env['attachment.migration.operation'].search([]).unlink()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_bucket = 'integration-test-bucket'
        cls.test_data = b'integration test content for full pipeline'
        cls.checksum = hashlib.sha256(cls.test_data).hexdigest()
        cls.s3_key = 'objects/%s/%s' % (cls.checksum[:2], cls.checksum)

        cls.binary = cls.env['ir.binary']

        cls.attachment = cls.env['ir.attachment'].create({
            'name': 'integration_test.pdf',
            'raw': cls.test_data,
            'type': 'binary',
            'mimetype': 'application/pdf',
        })

        ICP = cls.env['ir.config_parameter'].sudo()
        ICP.set_param('attachment_storage.s3.bucket', cls.test_bucket)
        ICP.set_param('attachment_storage.s3.region', 'us-east-1')
        ICP.set_param('attachment_storage.s3.access_key_id', 'testing')
        ICP.set_param('attachment_storage.s3.secret_access_key', 'testing')

    def _setup_moto_s3(self):
        try:
            import boto3
            from moto import mock_aws
        except ImportError:
            self.skipTest('moto or boto3 not available')
        mock = mock_aws()
        mock.start()
        self._mock_aws = mock
        client = boto3.client('s3', region_name='us-east-1')
        client.create_bucket(Bucket=self.test_bucket)
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('attachment_storage.s3.endpoint_url', '')

    def test_01_full_pipeline(self):
        """End-to-end: analyze -- queue -- upload -- verify -- finalize -- read -- audit."""
        self._setup_moto_s3()

        from ..services.migration_service import MigrationService
        service = MigrationService(self.env)

        # Step 1: Analyze
        candidates = service.analyze_candidates()
        self.assertIn(self.attachment, candidates,
                      'Attachment must be a migration candidate')

        # Step 2: Create queue
        ops = service.create_migration_operations([self.attachment.id])
        self.assertTrue(ops, 'Migration operations must be created')
        op = ops[0]
        self.assertEqual(op.state, 'queued')

        # Step 3: Process queue (upload -- verify -- finalize)
        results = service.process_queue(batch_size=10)
        self.assertEqual(results['success'], 1,
                         'Pipeline must succeed for the attachment')
        self.assertEqual(results['failed'], 0)

        # Step 4: Verify mapping is finalized
        Mapping = self.env['attachment.storage.mapping']
        mapping = Mapping.lookup_by_attachment(self.attachment.id)
        self.assertTrue(mapping, 'Mapping must exist after pipeline')
        self.assertEqual(mapping.status, 'finalized')
        self.assertEqual(mapping.s3_key, self.s3_key)
        self.assertEqual(mapping.checksum_sha256, self.checksum)

        # Step 5: Verify operation is finalized
        op.invalidate_cache()
        self.assertEqual(op.state, 'finalized')
        self.assertEqual(op.mapping_id.id, mapping.id)

        # Step 6: Read from S3 via ir.binary extension
        stream = self.binary._get_stream_from(self.attachment, 'datas')
        self.assertIsNotNone(stream, 'Must return stream from S3')
        self.assertEqual(stream.data, self.test_data)
        self.assertEqual(stream.mimetype, 'application/pdf')

        # Step 7: Verify store_fname unchanged
        self.attachment.invalidate_cache()
        self.assertTrue(self.attachment.store_fname)

        # Step 8: Verify audit log entries
        AuditLog = self.env['attachment.audit.log']
        logs = AuditLog.search([
            ('attachment_id', '=', self.attachment.id),
        ], order='create_date ASC')
        actions = logs.mapped('action')
        self.assertIn('queue', actions)
        self.assertIn('upload', actions)
        self.assertIn('verify_finalize', actions)
        for log in logs:
            self.assertEqual(log.result, 'success',
                             'All steps must be success')

    def tearDown(self):
        if getattr(self, '_mock_aws', None):
            self._mock_aws.stop()
            self._mock_aws = None
        from unittest.mock import patch
        patch.stopall()
        super().tearDown()
