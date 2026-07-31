from unittest.mock import patch

from ..services.s3_bridge import S3Bridge
from odoo.tests import TransactionCase


class TestResConfigSettings(TransactionCase):

    def test_01_formats_forbidden_as_credentials_or_permissions(self):
        message = self.env['res.config.settings']._format_s3_connection_error(
            'An error occurred (403) when calling HeadBucket: Forbidden',
            'attachments',
        )
        self.assertIn('Authentication or access failed', message)
        self.assertIn('Access Key, Secret Key', message)
        self.assertIn('attachments', message)
        self.assertNotIn('HeadBucket', message)

    def test_02_formats_missing_bucket(self):
        message = self.env['res.config.settings']._format_s3_connection_error(
            'An error occurred (NoSuchBucket)',
            'missing-bucket',
        )
        self.assertIn('was not found', message)
        self.assertIn('missing-bucket', message)

    def test_03_formats_endpoint_failure(self):
        message = self.env['res.config.settings']._format_s3_connection_error(
            'EndpointConnectionError: Could not connect',
            'attachments',
        )
        self.assertIn('Cannot reach the S3 endpoint', message)
        self.assertIn('Endpoint URL', message)

    def test_04_unknown_error_does_not_leak_provider_details(self):
        message = self.env['res.config.settings']._format_s3_connection_error(
            'provider-internal-secret-detail',
            'attachments',
        )
        self.assertIn('check the Odoo server log', message)
        self.assertNotIn('provider-internal-secret-detail', message)

    def test_05_verification_fingerprints_exact_form_values(self):
        settings = self.env['res.config.settings'].create({
            's3_bucket': 'unsaved-bucket',
            's3_region': 'eu-west-1',
            's3_endpoint_url': 'https://s3.example.test',
            's3_access_key_id': 'unsaved-access',
            's3_secret_access_key': 'unsaved-secret',
        })
        expected_config = {
            'endpoint_url': 'https://s3.example.test',
            'region': 'eu-west-1',
            'access_key_id': 'unsaved-access',
            'secret_access_key': 'unsaved-secret',
        }
        with patch.object(
            S3Bridge, 'test_connection',
            return_value={'status': 'ok', 'error': None},
        ), patch.object(
            S3Bridge, 'get_config_fingerprint', return_value='verified-digest',
        ) as fingerprint:
            settings.action_test_s3_connection()

        fingerprint.assert_called_once_with(
            config=expected_config, bucket='unsaved-bucket',
        )
        self.assertEqual(
            self.env['ir.config_parameter'].sudo().get_param(
                'attachment_storage.connection_verified_digest'
            ),
            'verified-digest',
        )
