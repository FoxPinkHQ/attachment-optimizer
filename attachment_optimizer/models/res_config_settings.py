from odoo import models, fields, api
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    s3_bucket = fields.Char(
        string='Bucket',
        config_parameter='attachment_storage.s3.bucket',
    )
    s3_region = fields.Char(
        string='Region',
        config_parameter='attachment_storage.s3.region',
    )
    s3_endpoint_url = fields.Char(
        string='Endpoint URL',
        config_parameter='attachment_storage.s3.endpoint_url',
    )
    s3_access_key_id = fields.Char(
        string='S3 Access Key',
        config_parameter='attachment_storage.s3.access_key_id',
    )
    s3_secret_access_key = fields.Char(
        string='Secret Key',
        config_parameter='attachment_storage.s3.secret_access_key',
    )
    recovery_enabled = fields.Boolean(
        string='Enable Auto-Recovery',
        config_parameter='attachment_storage.recovery.enabled',
        default=True,
    )
    recovery_limit = fields.Integer(
        string='Recovery Batch Limit',
        config_parameter='attachment_storage.recovery.limit',
        default=500,
    )

    @staticmethod
    def _format_s3_connection_error(error, bucket):
        """Return an actionable message without exposing provider internals."""
        normalized = str(error).lower()

        authentication_markers = (
            '403',
            'accessdenied',
            'forbidden',
            'invalidaccesskeyid',
            'signaturedoesnotmatch',
            'invalidtoken',
            'expiredtoken',
        )
        if any(marker in normalized for marker in authentication_markers):
            return (
                'Authentication or access failed.\n\n'
                'Verify the Access Key, Secret Key, and permissions for '
                'bucket "%s".' % bucket
            )

        if 'nosuchbucket' in normalized or 'not found' in normalized or '404' in normalized:
            return (
                'Bucket "%s" was not found.\n\n'
                'Verify the bucket name and region, or create the bucket first.'
                % bucket
            )

        network_markers = (
            'endpointconnectionerror',
            'could not connect',
            'connection refused',
            'name or service not known',
            'timed out',
            'timeout',
        )
        if any(marker in normalized for marker in network_markers):
            return (
                'Cannot reach the S3 endpoint.\n\n'
                'Verify the Endpoint URL and network connectivity from the '
                'Odoo server.'
            )

        return (
            'The S3 connection test failed.\n\n'
            'Verify the storage configuration and check the Odoo server log '
            'for technical details.'
        )

    def action_test_s3_connection(self):
        self.ensure_one()
        bucket = self.s3_bucket
        config = {
            'endpoint_url': self.s3_endpoint_url or '',
            'region': self.s3_region or 'us-east-1',
            'access_key_id': self.s3_access_key_id or '',
            'secret_access_key': self.s3_secret_access_key or '',
        }

        ICP = self.env['ir.config_parameter'].sudo()
        if not bucket:
            raise UserError('Bucket is required.')

        try:
            from ..services.s3_bridge import S3Bridge
            bridge = S3Bridge(self.env)
            result = bridge.test_connection(config=config, bucket=bucket)
            if result['status'] != 'ok':
                raise UserError(result['error'] or 'S3 connection check failed.')
            ICP = self.env['ir.config_parameter'].sudo()
            ICP.set_param('attachment_storage.connection_verified_at', fields.Datetime.now().isoformat())
            ICP.set_param('attachment_storage.connection_verified_digest', bridge.get_config_fingerprint())
        except Exception as e:
            raise UserError(self._format_s3_connection_error(e, bucket))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'S3 Connection OK',
                'message': 'Connected to bucket "%s" at %s' % (
                    bucket, config['endpoint_url'] or 'default endpoint'
                ),
                'sticky': False,
                'type': 'success',
            },
        }