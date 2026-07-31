import hashlib

from odoo.tests import SavepointCase

from ..services.migration_service import MigrationService
from ..services.s3_bridge import S3Bridge


class TestMigrationService(SavepointCase):

    def setUp(self):
        super().setUp()
        self.env['attachment.migration.operation'].search([]).unlink()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = MigrationService(cls.env)
        cls.bridge = S3Bridge(cls.env)
        cls.test_bucket = 'test-bucket'
        cls.test_data = b'fake binary content for migration test'

        cls.attachment = cls.env['ir.attachment'].create({
            'name': 'migration_test.pdf',
            'raw': cls.test_data,
            'type': 'binary',
        })

        cls.attachment_url = cls.env['ir.attachment'].create({
            'name': 'url_link',
            'type': 'url',
            'url': 'https://example.com/file.pdf',
        })

        ICP = cls.env['ir.config_parameter'].sudo()
        ICP.set_param('attachment_storage.s3.bucket', cls.test_bucket)
        ICP.set_param('attachment_storage.s3.region', 'us-east-1')
        ICP.set_param('attachment_storage.s3.access_key_id', 'testing')
        ICP.set_param('attachment_storage.s3.secret_access_key', 'testing')

        cls.checksum = hashlib.sha256(cls.test_data).hexdigest()

    def _setup_mock_s3(self):
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
        ICP.set_param('attachment_storage.s3.bucket', self.test_bucket)

    def test_01_analyze_candidates_finds_eligible(self):
        self.attachment.write({'store_fname': 'tests/test_store'})
        candidates = self.service.analyze_candidates()
        self.assertIn(self.attachment, candidates)

    def test_02_analyze_candidates_excludes_mapped(self):
        self.attachment.write({'store_fname': 'tests/test_store'})
        Mapping = self.env['attachment.storage.mapping']
        Mapping.create_mapping(
            attachment_id=self.attachment.id,
            s3_bucket=self.test_bucket,
            s3_key='tests/mapped',
            s3_region='us-east-1',
        )
        candidates = self.service.analyze_candidates()
        self.assertNotIn(self.attachment, candidates)

    def test_03_analyze_candidates_excludes_url_attachments(self):
        candidates = self.service.analyze_candidates()
        self.assertNotIn(self.attachment_url, candidates)

    def test_04_analyze_candidates_filters_by_model(self):
        self.attachment.write({'store_fname': 'tests/test_store'})
        self.attachment.write({'res_model': 'res.partner'})
        candidates = self.service.analyze_candidates(res_model='res.partner')
        self.assertIn(self.attachment, candidates)
        candidates_other = self.service.analyze_candidates(res_model='sale.order')
        self.assertNotIn(self.attachment, candidates_other)

    def test_05_create_migration_operations(self):
        self.attachment.write({'store_fname': 'tests/test_store'})
        ops = self.service.create_migration_operations([self.attachment.id])
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops.state, 'queued')
        self.assertEqual(ops.attachment_id.id, self.attachment.id)

    def test_06_create_operations_skips_duplicates(self):
        self.attachment.write({'store_fname': 'tests/test_store'})
        self.service.create_migration_operations([self.attachment.id])
        ops2 = self.service.create_migration_operations([self.attachment.id])
        self.assertEqual(len(ops2), 0)

    def test_07_full_migration_pipeline(self):
        self._setup_mock_s3()
        self.attachment.write({'store_fname': 'tests/test_file'})
        op = self.service.create_migration_operations([self.attachment.id])
        results = self.service.process_queue(batch_size=10)
        self.assertEqual(results['success'], 1)
        self.assertEqual(results['failed'], 0)
        op.invalidate_cache()
        self.assertEqual(op.state, 'finalized')
        mapping = op.mapping_id
        self.assertTrue(mapping)
        self.assertEqual(mapping.status, 'finalized')
        self.assertEqual(mapping.checksum_sha256, self.checksum)

    def test_08_migration_allows_create_without_bucket(self):
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('attachment_storage.s3.bucket', '')
        ops = self.service.create_migration_operations([self.attachment.id])
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops.state, 'queued')

    def test_09_process_queue_handles_multiple(self):
        self._setup_mock_s3()
        att2 = self.env['ir.attachment'].create({
            'name': 'test2.txt',
            'raw': b'second file content',
            'type': 'binary',
            'store_fname': 'tests/test2',
        })
        self.attachment.write({'store_fname': 'tests/test_file'})
        ops = self.service.create_migration_operations([
            self.attachment.id, att2.id,
        ])
        self.assertEqual(len(ops), 2)
        results = self.service.process_queue(batch_size=10)
        self.assertEqual(results['success'], 2)

    def test_10_process_queue_respects_batch_size(self):
        self._setup_mock_s3()
        attachments = []
        for i in range(5):
            att = self.env['ir.attachment'].create({
                'name': 'batch_%d.txt' % i,
                'raw': b'content %d' % i,
                'type': 'binary',
                'store_fname': 'tests/batch_%d' % i,
            })
            attachments.append(att)
        self.service.create_migration_operations([a.id for a in attachments])
        results = self.service.process_queue(batch_size=3)
        self.assertEqual(results['success'], 3)
        remaining = self.env['attachment.migration.operation'].search([
            ('state', '=', 'queued'),
        ])
        self.assertEqual(len(remaining), 2)

    def test_11_finalize_does_not_modify_ir_attachment(self):
        self._setup_mock_s3()
        self.attachment.invalidate_cache()
        orig_store_fname = self.attachment.store_fname
        op = self.service.create_migration_operations([self.attachment.id])
        self.service.process_queue()
        op.invalidate_cache()
        self.assertEqual(op.state, 'finalized')
        self.attachment.invalidate_cache()
        self.assertEqual(self.attachment.store_fname, orig_store_fname)
        self.assertTrue(orig_store_fname)

    def test_12_finalized_attachment_still_readable_via_filestore(self):
        self._setup_mock_s3()
        self.attachment.write({'store_fname': 'tests/test_store'})
        op = self.service.create_migration_operations([self.attachment.id])
        self.service.process_queue()
        op.invalidate_cache()
        self.assertEqual(op.state, 'finalized')
        self.attachment.invalidate_cache()
        self.assertTrue(self.attachment.datas)

    def test_13_s3_key_is_checksum_based(self):
        self._setup_mock_s3()
        self.attachment.write({'store_fname': 'tests/test_store'})
        op = self.service.create_migration_operations([self.attachment.id])
        self.service.process_queue()
        op.invalidate_cache()
        expected_key = 'objects/%s/%s' % (self.checksum[:2], self.checksum)
        self.assertEqual(op.mapping_id.s3_key, expected_key)

    def tearDown(self):
        if getattr(self, '_mock_aws', None):
            self._mock_aws.stop()
            self._mock_aws = None
        from unittest.mock import patch
        patch.stopall()
        super().tearDown()

    def test_14_analyze_excludes_previously_failed_attachment(self):
        self.attachment.write({'store_fname': 'tests/test_store'})
        self.env['attachment.migration.operation'].create({
            'attachment_id': self.attachment.id,
            'state': 'failed',
            'error_message': 'Previous migration failed',
        })

        candidates = self.service.analyze_candidates()

        self.assertNotIn(self.attachment, candidates)

    def test_15_failed_upload_does_not_log_success(self):
        broken = self.env['ir.attachment'].create({
            'name': 'missing-binary.txt',
            'type': 'binary',
        })
        operation = self.service.create_migration_operations([broken.id])

        result = self.service.process_queue(operation_ids=operation.ids)

        self.assertEqual(result['failed'], 1)
        logs = self.env['attachment.audit.log'].search([
            ('operation_id', '=', operation.id),
            ('action', '=', 'upload'),
        ])
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs.result, 'failure')

    def test_16_analyze_excludes_attachments_from_other_companies(self):
        other_company = self.env['res.company'].create({
            'name': 'Migration Other Company',
        })
        foreign = self.env['ir.attachment'].sudo().create({
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
        candidates = MigrationService(scoped_env).analyze_candidates()

        self.assertNotIn(foreign, candidates)
