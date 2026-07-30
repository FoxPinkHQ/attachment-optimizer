import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

from ..services.utils import human_size

_logger = logging.getLogger(__name__)

STATE_TRANSITIONS = {
    'draft': ['queued'],
    'queued': ['uploading', 'failed'],
    'uploading': ['uploaded', 'failed', 'queued'],
    'uploaded': ['verified', 'failed'],
    'verified': ['finalized'],
    'finalized': [],
    'failed': ['queued'],
}

ACTIVE_STATES = {'draft', 'queued', 'uploading', 'uploaded', 'verified'}
TERMINAL_STATES = {'finalized', 'failed'}
CLEAR_OWNERSHIP_STATES = {'finalized', 'failed', 'queued'}

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
    is_active = fields.Boolean(
        string='Active', default=True, index=True,
        help="Controlled by state machine — true for non-terminal states",
    )
    processing_token = fields.Char(
        string='Processing Token', readonly=True, copy=False,
        help="UUID assigned when a worker claims this operation",
    )
    worker_id = fields.Char(
        string='Worker ID', readonly=True, copy=False,
        help="Identifier of the worker processing this operation",
    )
    claimed_at = fields.Datetime(
        string='Claimed At', readonly=True, copy=False,
    )
    heartbeat_at = fields.Datetime(
        string='Heartbeat', readonly=True, copy=False,
    )
    retry_of = fields.Many2one(
        'attachment.migration.operation', string='Retry Of',
        readonly=True, copy=False,
        help="Previous operation that was retried to create this one",
    )
    root_operation_id = fields.Many2one(
        'attachment.migration.operation', string='Root Operation',
        readonly=True, copy=False, index=True,
        help="Earliest operation in the retry chain",
    )
    attempt = fields.Integer(
        string='Attempt', default=1, readonly=True,
        help="Retry attempt number (1 = original)",
    )
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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'state' in vals and 'is_active' not in vals:
                vals['is_active'] = vals['state'] in ACTIVE_STATES
        return super().create(vals_list)

    def init(self):
        super().init()
        self.env.cr.execute("""
            SELECT 1 FROM pg_class WHERE relname = 'uq_attachment_active_operation'
        """)
        if not self.env.cr.fetchone():
            self.env.cr.execute("""
                CREATE UNIQUE INDEX uq_attachment_active_operation
                ON attachment_migration_operation (attachment_id)
                WHERE is_active = TRUE
            """)
            _logger.info('Created partial unique index uq_attachment_active_operation')

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
        if 'state' in vals:
            vals['is_active'] = vals['state'] in ACTIVE_STATES
        return super().write(vals)

    @api.model
    def create_queue(self, attachment_ids):
        now = fields.Datetime.now()
        created = self.browse()
        atts = self.env['ir.attachment'].browse(attachment_ids)
        company_map = {
            a.id: a.company_id.id if a.company_id else self.env.company.id
            for a in atts
        }
        for att_id in attachment_ids:
            existing = self.search_count([
                ('attachment_id', '=', att_id),
                ('state', 'not in', ('finalized', 'failed')),
            ])
            if existing:
                continue
            op = self.create({
                'attachment_id': att_id,
                'company_id': company_map.get(att_id, self.env.company.id),
                'state': 'queued',
                'queued_at': now,
            })
            created += op
        return created

    @api.model
    def claim_batch(self, limit=10, worker_id=None, operation_ids=None):
        import uuid
        token = str(uuid.uuid4())
        worker = worker_id or ('worker-%s' % token[:8])
        operation_ids = list(operation_ids or [])
        selection_clause = 'AND id = ANY(%s)' if operation_ids else ''
        query = f"""
            WITH claimed AS (
                SELECT id
                FROM attachment_migration_operation
                WHERE state = 'queued'
                {selection_clause}
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT %s
            )
            UPDATE attachment_migration_operation
            SET
                state = 'uploading',
                processing_token = %s,
                worker_id = %s,
                claimed_at = NOW(),
                heartbeat_at = NOW(),
                started_at = NOW()
            WHERE id IN (SELECT id FROM claimed)
            RETURNING id
        """
        self.env.cr.execute(query, ([operation_ids] if operation_ids else []) + [limit, token, worker])
        ids = [r[0] for r in self.env.cr.fetchall()]
        claimed = self.browse(ids)
        claimed.invalidate_recordset()
        for op in claimed:
            self.env['attachment.audit.log']._log(
                'claim', result='success',
                attachment_id=op.attachment_id.id,
                operation_id=op.id,
            )
        return claimed

    @api.model
    def heartbeat(self, operation_id, processing_token):
        self.env.cr.execute("""
            UPDATE attachment_migration_operation
            SET heartbeat_at = NOW()
            WHERE id = %s AND processing_token = %s AND state = 'uploading'
            RETURNING id
        """, (operation_id, processing_token))
        if not self.env.cr.fetchone():
            raise ValidationError(
                _('Heartbeat rejected: token mismatch or operation is not uploading')
            )

    def transition_state(self, target_state, **kwargs):
        for record in self:
            allowed = STATE_TRANSITIONS.get(record.state, [])
            if target_state not in allowed:
                raise ValidationError(
                    _('Invalid state transition: %s → %s') % (
                        record.state, target_state
                    )
                )
            vals = {'state': target_state}
            if target_state in CLEAR_OWNERSHIP_STATES:
                vals.update({
                    'processing_token': False,
                    'worker_id': False,
                    'claimed_at': False,
                    'heartbeat_at': False,
                })
            for key in ('error_message', 'started_at', 'completed_at', 'queued_at',
                        'mapping_id', 'processing_token', 'worker_id', 'claimed_at',
                        'heartbeat_at'):
                if key in kwargs:
                    vals[key] = kwargs[key]
            record.write(vals)

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
            'res_model': 'res.config.settings',
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'new',
            'name': 'Attachment Optimizer Settings',
        }

    def action_retry(self):
        created = self.env['attachment.migration.operation']
        active_attachment_ids = set(
            self.env.cr.execute("""
                SELECT DISTINCT attachment_id FROM attachment_migration_operation
                WHERE is_active = TRUE
            """) or self.env.cr.fetchall()
        )
        active_attachments = {r[0] for r in active_attachment_ids} if active_attachment_ids else set()
        for operation in self:
            if operation.attachment_id.id in active_attachments:
                _logger.info('Retry skipped for attachment %s: already active',
                             operation.attachment_id.id)
                continue
            if operation.mapping_id and operation.mapping_id.status in ('failed', 'verification_failed'):
                operation.mapping_id.unlink()
            root_id = operation.root_operation_id.id or operation.id
            new_op = self.create({
                'attachment_id': operation.attachment_id.id,
                'company_id': operation.company_id.id,
                'state': 'queued',
                'queued_at': fields.Datetime.now(),
                'retry_of': operation.id,
                'root_operation_id': root_id,
                'attempt': operation.attempt + 1,
            })
            created += new_op
            self.env['attachment.audit.log']._log(
                'retry', result='success',
                attachment_id=operation.attachment_id.id,
                operation_id=new_op.id,
            )
        return created

    def action_cancel(self):
        self.transition_state('draft')
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

    @api.model
    def action_analyze_and_queue(self, attachment_ids=None):
        from ..services.migration_service import MigrationService
        from ..services.s3_bridge import S3Bridge
        service = MigrationService(self.env)
        if attachment_ids:
            candidates = self.env['ir.attachment'].browse(attachment_ids).exists()
        else:
            candidates = service.analyze_candidates()
        ops = service.create_migration_operations(candidates.ids)
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('attachment_storage.last_analysis',
                      fields.Datetime.now().isoformat())
        ICP.set_param('attachment_storage.analysis_digest',
                      S3Bridge(self.env).get_config_fingerprint())
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
        results = service.process_queue(len(batch), operation_ids=batch.ids)
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

    @api.model
    def action_process_queue(self):
        ops = self.search([('state', '=', 'queued')])
        if not ops:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Process Queue'),
                    'message': _('No queued operations to process'),
                    'sticky': False,
                },
            }
        return ops.action_upload()

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
        created = failed.action_retry()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Retry'),
                'message': _('%d operation(s) re-queued') % len(created),
                'sticky': False,
            },
        }

    @api.model
    def action_recovery(self):
        """Called by cron — no import needed (safe_eval restriction)."""
        from ..services.recovery_engine import RecoveryEngine, RecoveryMode
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('attachment_storage.recovery.enabled', 'True') != 'True':
            return
        limit = int(ICP.get_param('attachment_storage.recovery.limit', '500'))
        engine = RecoveryEngine(self.env)
        report = engine.recover(mode=RecoveryMode.REPAIR, limit=limit)
        _logger.info(
            'Recovery complete: scanned=%d recovered=%d errors=%d duration=%dms',
            report.scanned, report.recovered,
            len(report.errors), report.duration_ms,
        )


