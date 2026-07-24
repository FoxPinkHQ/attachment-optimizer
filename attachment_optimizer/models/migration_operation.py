from odoo import models, fields, api, _


class MigrationOperation(models.Model):
    _name = 'attachment.migration.operation'
    _description = 'Storage Migration Operation'
    _order = 'create_date DESC'
    _rec_name = 'attachment_id'

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

    @api.model
    def create_queue(self, attachment_ids):
        existing = self.search([
            ('attachment_id', 'in', attachment_ids),
            ('state', 'not in', ('finalized', 'failed')),
        ])
        existing_ids = existing.mapped('attachment_id').ids
        to_create = [a for a in attachment_ids if a not in existing_ids]
        now = fields.Datetime.now()
        records = []
        for att_id in to_create:
            records.append({
                'attachment_id': att_id,
                'state': 'queued',
                'queued_at': now,
            })
        return self.create(records)

    def action_retry(self):
        self.write({
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

    def action_analyze_and_queue(self, *args):
        from ..services.migration_service import MigrationService
        service = MigrationService(self.env)
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
        results = service.process_queue(len(to_process))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Upload Complete'),
                'message': _('%(ok)d success, %(fail)d failed') % {
                    'ok': results['success'],
                    'fail': results['failed'],
                },
                'sticky': False,
            },
        }

    @api.model
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
