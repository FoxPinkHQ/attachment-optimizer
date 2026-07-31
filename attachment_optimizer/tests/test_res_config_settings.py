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
