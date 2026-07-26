from .utils import human_size as _human_size


class DashboardService:

    def __init__(self, env):
        self.env = env

    def get_kpi_data(self):
        Attachment = self.env['ir.attachment']
        Mapping = self.env['attachment.storage.mapping']
        Operation = self.env['attachment.migration.operation']

        total = Attachment.search_count([
            ('type', '=', 'binary'),
            ('store_fname', '!=', False),
        ])

        migrated = Mapping.search_count([('status', '=', 'finalized')])

        self.env.cr.execute("""
            SELECT COALESCE(SUM(a.file_size), 0)
            FROM attachment_storage_mapping m
            JOIN ir_attachment a ON a.id = m.attachment_id
            WHERE m.status = 'finalized'
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
        Operation = self.env['attachment.migration.operation']
        ops = Operation.search([], limit=limit, order='create_date DESC')
        result = []
        for op in ops:
            duration = False
            if op.started_at and op.completed_at:
                delta = op.completed_at - op.started_at
                duration = int(delta.total_seconds())
            result.append({
                'id': op.id,
                'attachment_name': op.attachment_id.display_name or op.attachment_id.name,
                'state': op.state,
                'started_at': op.started_at.isoformat() if op.started_at else None,
                'completed_at': op.completed_at.isoformat() if op.completed_at else None,
                'has_error': bool(op.error_message),
                'duration': duration,
            })
        return result

    def get_dashboard_data(self):
        ICP = self.env['ir.config_parameter'].sudo()
        bucket = ICP.get_param('attachment_storage.s3.bucket')
        last_analysis = ICP.get_param('attachment_storage.last_analysis')

        return {
            **self.get_kpi_data(),
            'active_operation': self.get_active_operation(),
            'recent_operations': self.get_recent_operations(),
            's3_warning': not bucket,
            'last_analysis': last_analysis or False,
        }
