import hashlib

from odoo.tests import SavepointCase



class TestReadFlow(SavepointCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_bucket = 'test-bucket'
        cls.test_data = b'read flow test content'
        cls.checksum = hashlib.sha256(cls.test_data).hexdigest()
        cls.s3_key = 'objects/%s/%s' % (cls.checksum[:2], cls.checksum)

        cls.binary = cls.env['ir.binary']

        cls.attachment = cls.env['ir.attachment'].create({
            'name': 'read_test.pdf',
            'raw': cls.test_data,
            'type': 'binary',
            'mimetype': 'application/pdf',
        })

        cls.attachment_no_mapping = cls.env['ir.attachment'].create({
            'name': 'no_mapping.txt',
            'raw': b'no mapping content',
            'type': 'binary',
            'mimetype': 'text/plain',
        })

        ICP = cls.env['ir.config_parameter'].sudo()
        ICP.set_param('attachment_storage.s3.bucket', cls.test_bucket)
        ICP.set_param('attachment_storage.s3.region', 'us-east-1')
        ICP.set_param('attachment_storage.s3.access_key_id', 'testing')
        ICP.set_param('attachment_storage.s3.secret_access_key', 'testing')

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
        client.put_object(Bucket=self.test_bucket, Key=self.s3_key, Body=self.test_data)

        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('attachment_storage.s3.endpoint_url', '')

    def _create_finalized_mapping(self, attachment):
        Mapping = self.env['attachment.storage.mapping']
        mapping = Mapping.create_mapping(
            attachment_id=attachment.id,
            s3_bucket=self.test_bucket,
            s3_key=self.s3_key,
            s3_region='us-east-1',
        )
        mapping.action_update_status('uploading')
        mapping.action_update_status('uploaded')
        mapping.action_update_status('verified', checksum=self.checksum)
        mapping.action_update_status('finalized')
        return mapping

    def test_01_stream_from_s3_when_mapping_finalized(self):
        self._setup_mock_s3()
        self._create_finalized_mapping(self.attachment)
        stream = self.binary._get_stream_from(self.attachment, 'datas')
        self.assertIsNotNone(stream)
        self.assertEqual(stream.data, self.test_data)
        self.assertEqual(stream.mimetype, 'application/pdf')

    def test_02_fallback_to_filestore_when_no_mapping(self):
        stream = self.binary._get_stream_from(
            self.attachment_no_mapping, 'datas'
        )
        self.assertIsNone(stream)

    def test_03_fallback_to_filestore_when_mapping_not_finalized(self):
        self.env['attachment.storage.mapping'].create_mapping(
            attachment_id=self.attachment.id,
            s3_bucket=self.test_bucket,
            s3_key=self.s3_key,
            s3_region='us-east-1',
        )
        stream = self.binary._get_stream_from(self.attachment, 'datas')
        self.assertIsNone(stream)

    def test_04_stream_has_correct_mimetype(self):
        self._setup_mock_s3()
        self._create_finalized_mapping(self.attachment)
        stream = self.binary._get_stream_from(self.attachment, 'datas')
        self.assertEqual(stream.mimetype, 'application/pdf')

    def test_05_stream_has_correct_filename(self):
        self._setup_mock_s3()
        self._create_finalized_mapping(self.attachment)
        stream = self.binary._get_stream_from(self.attachment, 'datas', filename='custom.pdf')
        self.assertEqual(stream.download_name, 'custom.pdf')

    def test_06_finalized_mapping_missing_s3_falls_back(self):
        self._create_finalized_mapping(self.attachment)
        stream = self.binary._get_stream_from(self.attachment, 'datas')
        self.assertEqual(stream.data, self.test_data)

    def test_07_store_fname_unchanged_after_read(self):
        self._setup_mock_s3()
        self._create_finalized_mapping(self.attachment)
        self.binary._get_stream_from(self.attachment, 'datas')
        self.attachment.invalidate_cache()
        self.assertTrue(self.attachment.store_fname)

    def test_08_mapping_lookup_by_attachment_returns_mapping(self):
        self._create_finalized_mapping(self.attachment)
        Mapping = self.env['attachment.storage.mapping']
        mapping = Mapping.lookup_by_attachment(self.attachment.id)
        self.assertTrue(mapping)
        self.assertEqual(mapping.status, 'finalized')

    def test_09_get_external_location(self):
        self._create_finalized_mapping(self.attachment)
        Mapping = self.env['attachment.storage.mapping']
        location = Mapping.get_external_location(self.attachment.id)
        self.assertEqual(location['bucket'], self.test_bucket)
        self.assertEqual(location['key'], self.s3_key)
        self.assertEqual(location['checksum'], self.checksum)

    def test_10_attachment_without_mapping_serves_from_filestore(self):
        stream = self.binary._get_stream_from(
            self.attachment_no_mapping, 'datas'
        )
        self.assertIsNone(stream)

    def test_11_respects_attachment_acl(self):
        self._setup_mock_s3()
        self._create_finalized_mapping(self.attachment)
        no_access_user = self.env['res.users'].create({
            'name': 'No Access',
            'login': 'no_access_acl',
            'groups_id': [(6, 0, [])],
        })
        env = self.env(user=no_access_user)
        binary = env['ir.binary']
        record = env['ir.attachment'].browse(self.attachment.id)
        stream = binary._get_stream_from(record, 'datas')
        self.assertIsNone(stream)

    def tearDown(self):
        if getattr(self, '_mock_aws', None):
            self._mock_aws.stop()
            self._mock_aws = None
        from unittest.mock import patch
        patch.stopall()
        super().tearDown()
