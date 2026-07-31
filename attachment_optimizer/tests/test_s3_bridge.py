import hashlib

from odoo.tests import TransactionCase
from odoo.exceptions import UserError

from ..services.s3_bridge import S3Bridge, S3BridgeError


class TestS3Bridge(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bridge = S3Bridge(cls.env)
        cls.test_bucket = 'test-bucket'
        cls.test_key = 'attachments/test_doc.pdf'
        cls.test_data = b'fake binary content for testing'

        ICP = cls.env['ir.config_parameter'].sudo()
        ICP.set_param('attachment_storage.s3.endpoint_url', 'http://localhost:9000')
        ICP.set_param('attachment_storage.s3.region', 'us-east-1')
        ICP.set_param('attachment_storage.s3.access_key_id', 'minioadmin')
        ICP.set_param('attachment_storage.s3.secret_access_key', 'minioadmin')

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
        ICP.set_param('attachment_storage.s3.region', 'us-east-1')
        ICP.set_param('attachment_storage.s3.access_key_id', 'testing')
        ICP.set_param('attachment_storage.s3.secret_access_key', 'testing')

    def test_01_upload_success(self):
        self._setup_mock_s3()
        result = self.bridge.upload(self.test_bucket, self.test_key, self.test_data)
        self.assertTrue(result)

    def test_02_upload_and_verify(self):
        self._setup_mock_s3()
        result = self.bridge.upload(
            self.test_bucket, self.test_key, self.test_data,
            checksum=self.checksum,
        )
        self.assertTrue(result)

    def test_03_verify_checksum_match(self):
        self._setup_mock_s3()
        self.bridge.upload(self.test_bucket, self.test_key, self.test_data)
        result = self.bridge.verify(self.test_bucket, self.test_key, self.checksum)
        self.assertTrue(result)

    def test_04_verify_checksum_mismatch(self):
        self._setup_mock_s3()
        self.bridge.upload(self.test_bucket, self.test_key, self.test_data)
        wrong_checksum = hashlib.sha256(b'different data').hexdigest()
        result = self.bridge.verify(self.test_bucket, self.test_key, wrong_checksum)
        self.assertFalse(result)

    def test_05_get_object_returns_content(self):
        self._setup_mock_s3()
        self.bridge.upload(self.test_bucket, self.test_key, self.test_data)
        content = self.bridge.get_object(self.test_bucket, self.test_key)
        self.assertEqual(content, self.test_data)

    def test_06_delete_object(self):
        self._setup_mock_s3()
        self.bridge.upload(self.test_bucket, self.test_key, self.test_data)
        self.bridge.delete(self.test_bucket, self.test_key)
        with self.assertRaises(S3BridgeError):
            self.bridge.get_object(self.test_bucket, self.test_key)

    def test_07_upload_to_nonexistent_bucket_raises_error(self):
        self._setup_mock_s3()
        with self.assertRaises(S3BridgeError):
            self.bridge.upload('nonexistent-bucket', self.test_key, self.test_data)

    def test_08_get_config_returns_configured_values(self):
        self._setup_mock_s3()
        config = self.bridge._get_config()
        self.assertEqual(config['region'], 'us-east-1')
        self.assertEqual(config['access_key_id'], 'testing')
        self.assertEqual(config['secret_access_key'], 'testing')

    def test_09_get_nonexistent_object_raises_error(self):
        self._setup_mock_s3()
        with self.assertRaises(S3BridgeError):
            self.bridge.get_object(self.test_bucket, 'nonexistent_key')

    def test_10_compute_checksum(self):
        self._setup_mock_s3()
        self.bridge.upload(self.test_bucket, self.test_key, self.test_data)
        result = self.bridge.verify(self.test_bucket, self.test_key, self.checksum)
        self.assertTrue(result)

    def test_11_upload_empty_data(self):
        self._setup_mock_s3()
        result = self.bridge.upload(self.test_bucket, 'empty_file', b'')
        self.assertTrue(result)

    def tearDown(self):
        if getattr(self, '_mock_aws', None):
            self._mock_aws.stop()
            self._mock_aws = None
        from unittest.mock import patch
        patch.stopall()
        super().tearDown()
