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
        ]
        if res_model:
            domain.append(('res_model', '=', res_model))
        # Exclude Odoo web assets (JS/CSS bundles) to avoid FK conflicts
        domain += [
            '|',
            ('res_model', '!=', 'ir.ui.view'),
            ('name', 'not like', '/web/assets/%'),
        ]
        attachments = self.env['ir.attachment'].search(domain)
        mapped = self.env['attachment.storage.mapping'].search([
            ('attachment_id', 'in', attachments.ids),
            ('status', 'not in', ('failed', 'verification_failed')),
        ])
        mapped_ids = mapped.mapped('attachment_id').ids
        candidates = attachments.filtered(
            lambda a: a.id not in mapped_ids
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
        bucket = self._get_default_bucket()
        if not bucket:
            raise ValueError(_('Default S3 bucket is not configured'))
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

    def process_queue(self, batch_size=10):
        queue = self.env['attachment.migration.operation'].search([
            ('state', '=', 'queued'),
        ], limit=batch_size)
        results = {'success': 0, 'failed': 0}
        for op in queue:
            try:
                self._process_single(op)
                results['success'] += 1
            except Exception as e:
                op.write({
                    'state': 'failed',
                    'error_message': str(e),
                    'completed_at': fields.Datetime.now(),
                })
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
        Mapping = self.env['attachment.storage.mapping']
        attachment = operation.attachment_id.sudo()
        bucket = self._get_default_bucket()
        region = self.env['ir.config_parameter'].sudo().get_param(
            'attachment_storage.s3.region', 'us-east-1'
        )

        # 1. Uploading
        operation.write({'state': 'uploading', 'started_at': fields.Datetime.now()})
        self._log_audit(
            'upload', result='success',
            attachment_id=attachment.id,
            attachment_name=attachment.name,
            operation_id=operation.id,
        )

        # 2. Read binary and compute checksum
        binary = self._read_binary(attachment)
        checksum = hashlib.sha256(binary).hexdigest()

        # 3. Build S3 key from content checksum
        s3_key = 'objects/%s/%s' % (checksum[:2], checksum)

        # 4. Upload to S3
        self._bridge.upload(bucket, s3_key, binary)

        # 5. Create mapping record
        mapping = Mapping.create_mapping(
            attachment_id=attachment.id,
            s3_bucket=bucket,
            s3_key=s3_key,
            s3_region=region,
        )
        mapping.action_update_status('uploading')
        mapping.action_update_status('uploaded')
        operation.write({'mapping_id': mapping.id, 'state': 'uploaded'})

        # 6. Verify checksum — S3 object content matches original
        verified = self._bridge.verify(bucket, s3_key, checksum)
        if not verified:
            mapping.action_update_status(
                'verification_failed',
                error='Checksum mismatch after upload',
            )
            operation.write({
                'state': 'failed',
                'error_message': 'Checksum mismatch',
                'completed_at': fields.Datetime.now(),
            })
            self._log_audit(
                'verify', result='failure',
                attachment_id=attachment.id,
                attachment_name=attachment.name,
                operation_id=operation.id,
                mapping_id=mapping.id,
                error_message='Checksum mismatch after upload',
            )
            return

        # 7. Mark verified — checksum confirmed, mapping stores verification state
        mapping.action_update_status('verified', checksum=checksum)
        self._log_audit(
            'verify', result='success',
            attachment_id=attachment.id,
            attachment_name=attachment.name,
            operation_id=operation.id,
            mapping_id=mapping.id,
        )

        # 8. Finalize — mapping records final state, attachment remains accessible
        #    via Odoo default /web/content (store_fname and filestore unchanged).
        #    Controller extension (FPAO-004) will intercept reads for finalized
        #    mappings and serve from S3 transparently.
        mapping.action_update_status('finalized')
        operation.write({
            'state': 'finalized',
            'completed_at': fields.Datetime.now(),
        })
        self._log_audit(
            'finalize', result='success',
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
