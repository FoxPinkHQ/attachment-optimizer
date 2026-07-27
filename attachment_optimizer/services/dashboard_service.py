from .utils import human_size as _human_size


class DashboardService:

    def __init__(self, env):
        self.env = env

    def get_kpi_data(self):
        Attachment = self.env['ir.attachment']
        Operation = self.env['attachment.migration.operation']

        total = Attachment.search_count([
            ('type', '=', 'binary'),
            ('store_fname', '!=', False),
        ])

        migrated = Operation.search_count([('state', '=', 'finalized')])

        self.env.cr.execute("""
            SELECT COALESCE(SUM(a.file_size), 0)
            FROM attachment_migration_operation o
            JOIN ir_attachment a ON a.id = o.attachment_id
            WHERE o.state = 'finalized'
        """)
        saved_bytes = self.env.cr.fetchone()[0]

        failed = Operation.search_count([('state', '=', 'failed')])

        return {
            'total_attachments': total,
            'migrated': migrated,
            'saved_bytes': saved_bytes,
            'saved_display': _human_size(saved_bytes),
            'failed': failed,
        }

    def get_active_operation(self):
        Operation = self.env['attachment.migration.operation']
        active = Operation.search([
            ('state', 'in', ('queued', 'uploading', 'uploaded', 'verified')),
        ], limit=1, order='create_date DESC')
        if not active:
            return None

        total_ops = Operation.search_count([
            ('create_date', '>=', active.create_date),
        ])
        done_ops = Operation.search_count([
            ('create_date', '>=', active.create_date),
            ('state', 'in', ('verified', 'finalized')),
        ])

        return {
            'id': active.id,
            'progress': round(done_ops / total_ops * 100) if total_ops else 0,
            'processed': done_ops,
            'total': total_ops,
        }

    def get_recent_operations(self, limit=10):
        ops = self.env['attachment.migration.operation'].search(
            [], limit=limit, order='create_date DESC'
        )
        state_field = self.env['attachment.migration.operation']._fields['state']
        state_map = dict(state_field.selection)
        return [{
            'id': op.id,
            'attachment_name': op.attachment_id.display_name or op.attachment_id.name,
            'state': op.state,
            'state_label': state_map.get(op.state, op.state),
            'started_at': op.started_at.isoformat() if op.started_at else None,
            'completed_at': op.completed_at.isoformat() if op.completed_at else None,
            'duration': int((op.completed_at - op.started_at).total_seconds())
                if op.started_at and op.completed_at else None,
        } for op in ops]

    def get_dashboard_data(self):
        ICP = self.env['ir.config_parameter'].sudo()
        bucket = ICP.get_param('attachment_storage.s3.bucket')
        last_analysis = ICP.get_param('attachment_storage.last_analysis')

        return {
            **self.get_kpi_data(),
            'active_operation': self.get_active_operation(),
            'recent_operations': self.get_recent_operations(),
            'recent_total': self.env['attachment.migration.operation'].search_count([]),
            's3_warning': not bucket,
            'last_analysis': last_analysis or False,
        }
