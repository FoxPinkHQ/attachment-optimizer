from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

from ..services.utils import human_size

STATE_TRANSITIONS = {
    'draft': ['queued'],
    'queued': ['uploading', 'failed'],
    'uploading': ['uploaded', 'failed'],
    'uploaded': ['verified', 'failed'],
    'verified': ['finalized'],
    'finalized': [],
    'failed': ['queued'],
}

UPLOAD_BATCH_LIMIT = 100


class MigrationOperation(models.Model):
    _name = 'attachment.migration.operation'
    _description = 'Storage Migration Operation'
    _order = 'create_date DESC'
    _rec_name = 'attachment_id'

    company_id = fields.Many2one(
        'res.company', string='Company',
        required=True, default=lambda self: self.env.company,
        index=True,
    )
    attachment_id = fields.Many2one(
        'ir.attachment', string='Attachment', required=True,
        ondelete='restrict', index=True,
    )
    mapping_id = fields.Many2one(
        'attachment.storage.mapping', string='Storage Mapping',
        ondelete='set null', readonly=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('queued', 'Queued'),
        ('uploading', 'Uploading'),
        ('uploaded', 'Uploaded'),
        ('verified', 'Verified'),
        ('finalized', 'Finalized'),
        ('failed', 'Failed'),
    ], string='State', default='draft', required=True)
    error_message = fields.Text(string='Error Message', readonly=True)
    queued_at = fields.Datetime(string='Queued At', readonly=True)
    started_at = fields.Datetime(string='Started At', readonly=True)
    completed_at = fields.Datetime(string='Completed At', readonly=True)
    s3_bucket_related = fields.Char(
        string='S3 Bucket', related='mapping_id.s3_bucket', readonly=True,
    )
    s3_key_related = fields.Char(
        string='S3 Key', related='mapping_id.s3_key', readonly=True,
    )
    s3_region_related = fields.Char(
        string='S3 Region', related='mapping_id.s3_region', readonly=True,
    )
    checksum_related = fields.Char(
        string='Checksum SHA256', related='mapping_id.checksum_sha256', readonly=True,
    )
    audit_log_ids = fields.One2many(
        'attachment.audit.log', 'operation_id',
        string='Audit Events', readonly=True,
    )
    duration_display = fields.Char(
        string='Duration', compute='_compute_duration_display',
        readonly=True,
    )

    @api.depends('started_at', 'completed_at')
    def _compute_duration_display(self):
        for op in self:
            if op.started_at and op.completed_at:
                delta = op.completed_at - op.started_at
                secs = int(delta.total_seconds())
                if secs < 60:
                    op.duration_display = '%ds' % secs
                elif secs < 3600:
                    op.duration_display = '%dm %ds' % (secs // 60, secs % 60)
                else:
                    h = secs // 3600
                    m = (secs % 3600) // 60
                    op.duration_display = '%dh %dm' % (h, m)
            else:
                op.duration_display = False

    def write(self, vals):
        if 'state' in vals:
            for record in self:
                if vals['state'] not in STATE_TRANSITIONS.get(record.state, []):
                    raise ValidationError(
                        _('Invalid state transition: %s → %s') % (
                            record.state, vals['state']
                        )
                    )
        return super().write(vals)

    @api.model
    def create_queue(self, attachment_ids):
        existing = self.search([
            ('attachment_id', 'in', attachment_ids),
            ('state', 'not in', ('finalized', 'failed')),
        ])
        existing_ids = existing.mapped('attachment_id').ids
        to_create = [a for a in attachment_ids if a not in existing_ids]
        now = fields.Datetime.now()
        attachments = self.env['ir.attachment'].browse(to_create)
        company_map = {
            a.id: a.company_id.id if a.company_id else self.env.company.id
            for a in attachments
        }
        records = []
        for att_id in to_create:
            records.append({
                'attachment_id': att_id,
                'company_id': company_map.get(att_id, self.env.company.id),
                'state': 'queued',
                'queued_at': now,
            })
        return self.create(records)

    def action_view_attachment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment',
            'view_mode': 'form',
            'res_id': self.attachment_id.id,
            'target': 'current',
        }

    def action_view_config(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ir.config_parameter',
            'view_mode': 'list',
            'domain': [('key', '=ilike', 'attachment_storage%')],
            'name': 'S3 Configuration',
        }

    def action_retry(self):
        for operation in self:
            if operation.mapping_id and operation.mapping_id.status in ('failed', 'verification_failed'):
                operation.mapping_id.unlink()
        self.write({
            'mapping_id': False,
            'state': 'queued',
            'error_message': False,
            'started_at': False,
            'completed_at': False,
            'queued_at': fields.Datetime.now(),
        })
        for record in self:
            self.env['attachment.audit.log']._log(
                'retry', result='success',
                attachment_id=record.attachment_id.id,
                operation_id=record.id,
            )

    def action_cancel(self):
        self.write({'state': 'draft'})
        for record in self:
            self.env['attachment.audit.log']._log(
                'cancel', result='success',
                attachment_id=record.attachment_id.id,
                operation_id=record.id,
            )

    @api.model
    def action_get_queue_impact(self):
        from ..services.migration_service import MigrationService
        service = MigrationService(self.env)
        candidates = service.analyze_candidates()
        total_size = sum((a.file_size or 0) for a in candidates)
        count = len(candidates)
        estimated_seconds = count * 2
        if estimated_seconds < 60:
            duration = '%ds' % estimated_seconds
        elif estimated_seconds < 3600:
            duration = '%dm' % (estimated_seconds // 60)
        else:
            hours = estimated_seconds // 3600
            mins = (estimated_seconds % 3600) // 60
            duration = '%dh %dm' % (hours, mins)
        return {
            'count': count,
            'total_size': human_size(total_size),
            'estimated_duration': duration,
            'candidate_ids': candidates.ids,
        }

    def action_analyze_and_queue(self, attachment_ids=None, *args):
        from ..services.migration_service import MigrationService
        service = MigrationService(self.env)
        if attachment_ids:
            candidates = self.env['ir.attachment'].browse(attachment_ids).exists()
        else:
            candidates = service.analyze_candidates()
        ops = service.create_migration_operations(candidates.ids)
        self.env['attachment.audit.log']._log(
            'migration_queue_created', result='success',
            attachment_name='%d operations queued' % len(ops),
        )
        if ops:
            message = _('%d migration operation(s) created') % len(ops)
        else:
            message = _('No new migration candidates found')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Migration Queue'),
                'message': message,
                'sticky': False,
            },
        }

    def action_upload(self):
        from ..services.migration_service import MigrationService
        service = MigrationService(self.env)
        to_process = self.filtered(lambda o: o.state == 'queued')
        if not to_process:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Upload'),
                    'message': _('No queued operations to process'),
                    'sticky': False,
                },
            }
        batch = to_process[:UPLOAD_BATCH_LIMIT]
        results = service.process_queue(len(batch))
        total = len(to_process)
        done = len(batch)
        remaining = total - done
        msg = _('%(ok)d success, %(fail)d failed') % {
            'ok': results['success'],
            'fail': results['failed'],
        }
        if remaining:
            msg += '\n' + _('Remaining: %d — continue processing') % remaining
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Upload Complete'),
                'message': msg,
                'sticky': remaining > 0,
            },
        }

    def action_retry_all_failed(self):
        failed = self.search([('state', '=', 'failed')])
        if not failed:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Retry'),
                    'message': _('No failed operations to retry'),
                    'sticky': False,
                },
            }
        failed.action_retry()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Retry'),
                'message': _('%d operation(s) re-queued') % len(failed),
                'sticky': False,
            },
        }
