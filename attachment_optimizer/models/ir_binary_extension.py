import base64
import logging

from odoo import models
from odoo.http import Stream

from ..services.s3_bridge import S3Bridge, S3BridgeError

_logger = logging.getLogger(__name__)


class MissingExternalObjectError(Exception):
    """Raised when a finalized storage mapping points to a non-existent S3 object."""


class IrBinaryExtension(models.AbstractModel):
    _inherit = 'ir.binary'

    def _get_stream_from(
        self, record, field_name='raw', filename=None, filename_field='name',
        mimetype=None, default_mimetype='application/octet-stream',
    ):
        if record._name == 'ir.attachment':
            try:
                record.check_access('read')
            except Exception:
                return
            mapping = self.env['attachment.storage.mapping'].sudo().search([
                ('attachment_id', '=', record.id),
                ('status', '=', 'finalized'),
                ('company_id', '=', record.company_id.id),
            ], limit=1)
            if mapping:
                bridge = S3Bridge(self.env)
                try:
                    content = bridge.get_object(
                        mapping.s3_bucket, mapping.s3_key
                    )
                except S3BridgeError as e:
                    _logger.error(
                        'S3 object missing for finalized mapping '
                        'attachment=%s bucket=%s key=%s: %s',
                        record.id, mapping.s3_bucket, mapping.s3_key, e,
                    )
                    # The original filestore data is retained. Fall back to
                    # it on S3 failures so a transient outage is not an
                    # attachment outage.
                    try:
                        return super()._get_stream_from(
                            record, field_name=field_name, filename=filename,
                            filename_field=filename_field, mimetype=mimetype,
                            default_mimetype=default_mimetype,
                        )
                    except RuntimeError:
                        return None
                return Stream(
                    data=content,
                    mimetype=record.mimetype or default_mimetype,
                    download_name=filename or record.name,
                    type='data',
                )
        try:
            return super()._get_stream_from(
                record, field_name=field_name, filename=filename,
                filename_field=filename_field, mimetype=mimetype,
                default_mimetype=default_mimetype,
            )
        except RuntimeError:
            return None
