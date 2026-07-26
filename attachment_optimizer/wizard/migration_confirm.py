from odoo import models, fields, api, _


class MigrationQueueConfirm(models.TransientModel):
    _name = 'attachment.migration.queue.confirm'
    _description = 'Confirm Migration Queue Creation'

    count = fields.Integer(string='Attachments', readonly=True)
    total_size = fields.Char(string='Estimated Total Size', readonly=True)
    estimated_duration = fields.Char(string='Estimated Duration', readonly=True)
    candidate_ids = fields.Many2many(
        'ir.attachment', string='Candidates',
    )

    def action_confirm(self):
        Operation = self.env['attachment.migration.operation']
        action = Operation.action_analyze_and_queue(
            attachment_ids=self.candidate_ids.ids
        )
        return action

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}
