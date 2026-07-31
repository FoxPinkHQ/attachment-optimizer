import base64
import hashlib
import logging

from odoo import fields, _

from .s3_bridge import S3Bridge

_logger = logging.getLogger(__name__)


class MigrationService:

    def __init__(self, env):
        self.env = env
        self._bridge = S3Bridge(env)

    def _get_default_bucket(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'attachment_storage.s3.bucket', ''
        )

    def _log_audit(self, action, result='success', attachment_id=None,
                   attachment_name=None, res_model=None, operation_id=None,
                   mapping_id=None, error_message=None):
        self.env['attachment.audit.log']._log(
            action=action, result=result, attachment_id=attachment_id,
            attachment_name=attachment_name, res_model=res_model,
            operation_id=operation_id, mapping_id=mapping_id,
            error_message=error_message,
        )

    def analyze_candidates(self, res_model=None, size_min_kb=0):
        domain = [
            ('type', '=', 'binary'),
            ('store_fname', '!=', False),
            ('company_id', 'in', [False] + self.env.companies.ids),
        ]
        if res_model:
            domain.append(('res_model', '=', res_model))
        domain.append(('res_model', '!=', 'ir.ui.view'))
        attachments = self.env['ir.attachment'].sudo().search(domain)
        mapped = self.env['attachment.storage.mapping'].search([
            ('attachment_id', 'in', attachments.ids),
            ('status', 'not in', ('failed', 'verification_failed')),
        ])
        mapped_ids = mapped.mapped('attachment_id').ids
        previously_processed = self.env['attachment.migration.operation'].search([
            ('attachment_id', 'in', attachments.ids),
        ])
        processed_ids = previously_processed.mapped('attachment_id').ids
        exclude_ids = set(mapped_ids) | set(processed_ids)
        candidates = attachments.filtered(
            lambda a: a.id not in exclude_ids
        )
        if size_min_kb > 0:
            candidates = candidates.filtered(
                lambda a: (a.file_size or 0) >= size_min_kb * 1024
            )
        self._log_audit(
            'analyze', result='success',
            attachment_name='%d candidates found' % len(candidates),
        )
        return candidates

    def create_migration_operations(self, attachment_ids):
        ops = self.env['attachment.migration.operation'].create_queue(
            attachment_ids
        )
        if not ops:
            _logger.info('No new migration operations created')
        for op in ops:
            self._log_audit(
                'queue', result='success',
                attachment_id=op.attachment_id.id,
                attachment_name=op.attachment_id.name,
                operation_id=op.id,
            )
        return ops

    def process_queue(self, batch_size=10, worker_id=None, operation_ids=None):
        claimed = self.env['attachment.migration.operation'].claim_batch(
            limit=batch_size, worker_id=worker_id, operation_ids=operation_ids,
        )
        results = {'success': 0, 'failed': 0}
        for op in claimed:
            try:
                self._process_single(op)
                results['success'] += 1
            except Exception as e:
                op.transition_state(
                    'failed',
                    error_message=str(e),
                    completed_at=fields.Datetime.now(),
                )
                if op.mapping_id:
                    op.mapping_id.action_update_status('failed', error=str(e))
                self._log_audit(
                    'upload', result='failure',
                    attachment_id=op.attachment_id.id,
                    attachment_name=op.attachment_id.name,
                    operation_id=op.id,
                    error_message=str(e),
                )
                results['failed'] += 1
                _logger.error('Migration failed for attachment %s: %s',
                              op.attachment_id.id, e)
        return results

    def _process_single(self, operation):
        if operation.state == 'queued':
            operation.transition_state('uploading', started_at=fields.Datetime.now())
        Mapping = self.env['attachment.storage.mapping']
        attachment = operation.attachment_id.sudo()
        bucket = self._get_default_bucket()
        region = self.env['ir.config_parameter'].sudo().get_param(
            'attachment_storage.s3.region', 'us-east-1'
        )

        binary = self._read_binary(attachment)
        checksum = hashlib.sha256(binary).hexdigest()
        s3_key = 'objects/%s/%s' % (checksum[:2], checksum)

        # HEAD before PUT for idempotent upload
        if self._bridge.head(bucket, s3_key):
            _logger.info('S3 object already exists, reusing: %s/%s', bucket, s3_key)
        else:
            self._bridge.upload(bucket, s3_key, binary)

        self._log_audit(
            'upload', result='success',
            attachment_id=attachment.id,
            attachment_name=attachment.name,
            operation_id=operation.id,
        )

        mapping = Mapping.create_mapping(
            attachment_id=attachment.id,
            s3_bucket=bucket,
            s3_key=s3_key,
            s3_region=region,
        )
        mapping.action_update_status('uploading')
        mapping.action_update_status('uploaded')
        operation.transition_state('uploaded', mapping_id=mapping.id)

        verified = self._bridge.verify(bucket, s3_key, checksum)
        if not verified:
            mapping.action_update_status(
                'verification_failed',
                error='Checksum mismatch after upload',
            )
            operation.transition_state(
                'failed',
                error_message='Checksum mismatch',
                completed_at=fields.Datetime.now(),
            )
            self._log_audit(
                'verify', result='failure',
                attachment_id=attachment.id,
                attachment_name=attachment.name,
                operation_id=operation.id,
                mapping_id=mapping.id,
                error_message='Checksum mismatch after upload',
            )
            return

        mapping.action_update_status('verified', checksum=checksum)
        operation.transition_state('verified')

        mapping.action_update_status('finalized')
        operation.transition_state('finalized', completed_at=fields.Datetime.now())
        self._log_audit(
            'verify_finalize', result='success',
            attachment_id=attachment.id,
            attachment_name=attachment.name,
            operation_id=operation.id,
            mapping_id=mapping.id,
        )

    def _read_binary(self, attachment):
        self = attachment.sudo()
        if self.datas:
            return base64.b64decode(self.datas)
        raise ValueError(
            _('Attachment %s has no binary data') % attachment.id
        )
