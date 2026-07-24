from odoo import models, fields, api, _
from odoo.exceptions import AccessError


class AuditLog(models.Model):
    _name = 'attachment.audit.log'
    _description = 'Storage Migration Audit Log'
    _order = 'create_date DESC, id DESC'
    _rec_name = 'display_name'

    display_name = fields.Char(compute='_compute_display_name', store=False)
    user_id = fields.Many2one(
        'res.users', string='User', required=True,
        default=lambda self: self.env.user, index=True,
    )
    action = fields.Selection([
        ('analyze', 'Analyze'),
        ('migration_queue_created', 'Migration Queue Created'),
        ('queue', 'Queue'),
        ('upload', 'Upload'),
        ('verify', 'Verify'),
        ('finalize', 'Finalize'),
        ('retry', 'Retry'),
        ('cancel', 'Cancel'),
    ], string='Action', required=True, index=True)
    attachment_id = fields.Many2one(
        'ir.attachment', string='Attachment', index=True,
    )
    attachment_name = fields.Char(string='Attachment Name')
    res_model = fields.Char(string='Related Document Model')
    operation_id = fields.Many2one(
        'attachment.migration.operation', string='Migration Operation',
    )
    mapping_id = fields.Many2one(
        'attachment.storage.mapping', string='Storage Mapping',
    )
    result = fields.Selection([
        ('success', 'Success'),
        ('failure', 'Failure'),
    ], string='Result', required=True, default='success')
    error_message = fields.Text(string='Error Message')
    create_date = fields.Datetime(string='Timestamp', readonly=True)

    @api.depends('action', 'attachment_name', 'create_date')
    def _compute_display_name(self):
        for rec in self:
            parts = []
            if rec.action:
                parts.append(dict(rec._fields['action'].selection).get(
                    rec.action, rec.action
                ))
            if rec.attachment_name:
                parts.append(rec.attachment_name)
            if rec.create_date:
                parts.append(rec.create_date.strftime('%Y-%m-%d %H:%M'))
            rec.display_name = ' — '.join(parts) if parts else 'Audit Log'

    @api.model
    def _log(self, action, result='success', attachment_id=None,
             attachment_name=None, res_model=None, operation_id=None,
             mapping_id=None, error_message=None):
        vals = {
            'user_id': self.env.user.id,
            'action': action,
            'result': result,
            'attachment_id': attachment_id,
            'attachment_name': attachment_name,
            'res_model': res_model,
            'operation_id': operation_id,
            'mapping_id': mapping_id,
            'error_message': error_message,
        }
        return self.create(vals)

    def write(self, vals):
        raise AccessError(_('Audit log records are read-only'))

    def unlink(self):
        raise AccessError(_('Audit log records cannot be deleted'))
