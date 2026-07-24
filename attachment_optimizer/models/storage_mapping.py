from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class StorageMapping(models.Model):
    _name = 'attachment.storage.mapping'
    _description = 'Attachment Storage Mapping'
    _rec_name = 'attachment_id'
    _order = 'create_date DESC'
    _sql_constraints = [
        ('unique_attachment', 'UNIQUE(attachment_id)',
         'Each attachment can have only one storage mapping.'),
    ]

    attachment_id = fields.Many2one(
        'ir.attachment', string='Attachment', required=True,
        ondelete='cascade', index=True,
    )
    s3_bucket = fields.Char(string='S3 Bucket', required=True)
    s3_key = fields.Char(string='S3 Object Key', required=True)
    s3_region = fields.Char(string='S3 Region', required=True)
    status = fields.Selection([
        ('pending', 'Pending'),
        ('uploading', 'Uploading'),
        ('uploaded', 'Uploaded'),
        ('verified', 'Verified'),
        ('finalized', 'Finalized'),
        ('failed', 'Failed'),
        ('verification_failed', 'Verification Failed'),
    ], string='Status', default='pending', required=True)
    checksum_sha256 = fields.Char(string='SHA-256 Checksum', readonly=True)
    verification_timestamp = fields.Datetime(
        string='Verification Timestamp', readonly=True,
    )
    error_message = fields.Text(string='Error Message', readonly=True)
    active = fields.Boolean(string='Active', default=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ICP = self.env['ir.config_parameter'].sudo()
        if 's3_bucket' in fields_list and not res.get('s3_bucket'):
            res['s3_bucket'] = ICP.get_param('attachment_storage_s3_bucket', 'attachment-storage-test')
        if 's3_region' in fields_list and not res.get('s3_region'):
            res['s3_region'] = ICP.get_param('attachment_storage_s3_region', 'us-east-1')
        return res

    @api.model
    def create_mapping(self, attachment_id, s3_bucket, s3_key, s3_region):
        existing = self.search([('attachment_id', '=', attachment_id)])
        if existing:
            raise ValidationError(
                _('Mapping already exists for attachment %s') % attachment_id
            )
        return self.create({
            'attachment_id': attachment_id,
            's3_bucket': s3_bucket,
            's3_key': s3_key,
            's3_region': s3_region,
            'status': 'pending',
        })

    @api.model
    def lookup_by_attachment(self, attachment_id):
        return self.search([('attachment_id', '=', attachment_id)], limit=1)

    @api.model
    def get_external_location(self, attachment_id):
        mapping = self.lookup_by_attachment(attachment_id)
        if not mapping or mapping.status not in ('verified', 'finalized'):
            return None
        return {
            'bucket': mapping.s3_bucket,
            'key': mapping.s3_key,
            'region': mapping.s3_region,
            'checksum': mapping.checksum_sha256,
        }

    def action_update_status(self, new_status, checksum=None, error=None):
        valid_transitions = {
            'pending': ['uploading'],
            'uploading': ['uploaded', 'failed'],
            'uploaded': ['verified', 'verification_failed'],
            'verified': ['finalized'],
            'failed': ['pending'],
            'verification_failed': ['pending'],
        }
        for record in self:
            allowed = valid_transitions.get(record.status, [])
            if new_status not in allowed:
                raise ValidationError(
                    _('Invalid status transition from %(from)s to %(to)s') % {
                        'from': record.status,
                        'to': new_status,
                    }
                )
            vals = {'status': new_status}
            if checksum:
                vals['checksum_sha256'] = checksum
            if new_status == 'verified':
                vals['verification_timestamp'] = fields.Datetime.now()
            if error:
                vals['error_message'] = error
            record.write(vals)

    def action_reset(self):
        self.write({
            'status': 'pending',
            'checksum_sha256': False,
            'verification_timestamp': False,
            'error_message': False,
        })

    def action_mark_failed(self, error_message):
        self.write({
            'status': 'failed',
            'error_message': error_message,
        })
