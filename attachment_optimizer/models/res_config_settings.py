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
        string='Access Key',
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
            msg = str(e)
            if 'NoSuchBucket' in msg:
                raise UserError(
                    'Cannot connect.\n\nBucket "%s" does not exist.\nCreate it first in S3.' % bucket
                )
            raise UserError(
                'Cannot connect.\n\n%s' % msg
            )

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