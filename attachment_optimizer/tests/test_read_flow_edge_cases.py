import hashlib
import os

from odoo.tests import TransactionCase



class TestReadFlowEdgeCases(TransactionCase):
    """Edge case coverage for ir.binary._get_stream_from S3 read flow.

    Batch 0 — Read Flow Hardening.
    Only tests, no production code changes.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_bucket = 'edge-test-bucket'
        cls.small_data = b'edge case test content for read flow hardening Batch 0'
        cls.checksum_small = hashlib.sha256(cls.small_data).hexdigest()
        cls.s3_key_small = 'objects/%s/%s' % (cls.checksum_small[:2], cls.checksum_small)

        cls.binary = cls.env['ir.binary']

        ICP = cls.env['ir.config_parameter'].sudo()
        ICP.set_param('attachment_storage.s3.bucket', cls.test_bucket)
        ICP.set_param('attachment_storage.s3.region', 'us-east-1')
        ICP.set_param('attachment_storage.s3.access_key_id', 'testing')
        ICP.set_param('attachment_storage.s3.secret_access_key', 'testing')
        ICP.set_param('attachment_storage.s3.endpoint_url', '')

    def _setup_mock_s3(self, data=None, key=None):
        try:
            import boto3
            from moto import mock_aws
        except ImportError:
            self.skipTest('moto or boto3 not available')
        mock = mock_aws()
        mock.start()
        self._mock_aws = mock
        client = boto3.client('s3', region_name='us-east-1')
        client.create_bucket(Bucket=self.test_bucket)
        client.put_object(
            Bucket=self.test_bucket,
            Key=key or self.s3_key_small,
            Body=data or self.small_data,
        )

    def _create_finalized_mapping(self, attachment, checksum=None, key=None):
        Mapping = self.env['attachment.storage.mapping']
        csum = checksum or self.checksum_small
        mapping = Mapping.create_mapping(
            attachment_id=attachment.id,
            s3_bucket=self.test_bucket,
            s3_key=key or self.s3_key_small,
            s3_region='us-east-1',
        )
        mapping.action_update_status('uploading')
        mapping.action_update_status('uploaded')
        mapping.action_update_status('verified', checksum=csum)
        mapping.action_update_status('finalized')
        return mapping

    # ─────────────────────────────────────────────────────────────
    # 1. Normal backend user — comprehensive read verification
    # ─────────────────────────────────────────────────────────────

    def test_01_checksum_correct(self):
        """Stream data from S3 matches original checksum."""
        self._setup_mock_s3()
        attachment = self.env['ir.attachment'].create({
            'name': 'checksum_test.bin',
            'raw': self.small_data,
            'type': 'binary',
        })
        self._create_finalized_mapping(attachment)
        stream = self.binary._get_stream_from(attachment, 'datas')
        self.assertIsNotNone(stream)
        actual = hashlib.sha256(stream.data).hexdigest()
        self.assertEqual(actual, self.checksum_small)

    def test_02_content_type_preserved(self):
        """Stream preserves original mimetype."""
        self._setup_mock_s3()
        attachment = self.env['ir.attachment'].create({
            'name': 'type_test.pdf',
            'raw': self.small_data,
            'type': 'binary',
            'mimetype': 'application/pdf',
        })
        self._create_finalized_mapping(attachment)
        stream = self.binary._get_stream_from(attachment, 'datas')
        self.assertEqual(stream.mimetype, 'application/pdf')

    def test_03_filename_custom(self):
        """Stream carries explicit filename parameter."""
        self._setup_mock_s3()
        attachment = self.env['ir.attachment'].create({
            'name': 'original_name.txt',
            'raw': self.small_data,
            'type': 'binary',
        })
        self._create_finalized_mapping(attachment)
        stream = self.binary._get_stream_from(attachment, 'datas', filename='custom.txt')
        self.assertEqual(stream.download_name, 'custom.txt')

    def test_04_filename_fallback_to_attachment_name(self):
        """Stream uses attachment name when filename not passed."""
        self._setup_mock_s3()
        attachment = self.env['ir.attachment'].create({
            'name': 'fallback_name.docx',
            'raw': self.small_data,
            'type': 'binary',
        })
        self._create_finalized_mapping(attachment)
        stream = self.binary._get_stream_from(attachment, 'datas')
        self.assertEqual(stream.download_name, 'fallback_name.docx')

    def test_05_content_length_ok(self):
        """Stream.data length matches original content."""
        self._setup_mock_s3()
        attachment = self.env['ir.attachment'].create({
            'name': 'length_test.bin',
            'raw': self.small_data,
            'type': 'binary',
        })
        self._create_finalized_mapping(attachment)
        stream = self.binary._get_stream_from(attachment, 'datas')
        self.assertEqual(len(stream.data), len(self.small_data))

    # ─────────────────────────────────────────────────────────────
    # 2. Public attachment — anonymous access safety
    # ─────────────────────────────────────────────────────────────

    def test_06_public_attachment_anonymous_read(self):
        """Public attachment finalized to S3 is readable by anonymous user."""
        self._setup_mock_s3()
        attachment = self.env['ir.attachment'].create({
            'name': 'public_read.txt',
            'raw': self.small_data,
            'type': 'binary',
            'public': True,
        })
        self._create_finalized_mapping(attachment)
        binary = self.env['ir.binary'].sudo()
        record = self.env['ir.attachment'].sudo().browse(attachment.id)
        stream = binary._get_stream_from(record, 'datas')
        self.assertIsNotNone(stream)
        self.assertEqual(stream.data, self.small_data)

    def test_07_public_attachment_no_s3_url_leak(self):
        """Stream does NOT expose S3 URL or bucket/key metadata."""
        self._setup_mock_s3()
        attachment = self.env['ir.attachment'].create({
            'name': 'no_url_leak.txt',
            'raw': self.small_data,
            'type': 'binary',
            'public': True,
        })
        self._create_finalized_mapping(attachment)
        stream = self.binary._get_stream_from(attachment, 'datas')
        self.assertEqual(stream.type, 'data',
            'Must use type=data, never redirect/URL')
        self.assertNotIn(self.test_bucket, str(stream.data[:512]))

    # ─────────────────────────────────────────────────────────────
    # 3. Portal user — access boundary verification
    # ─────────────────────────────────────────────────────────────

    def test_08_portal_user_blocked_by_acl(self):
        """Portal user receives None (no model-level ACL on ir.attachment).
        
        In Odoo 18, portal users have 0,0,0,0 ACL on ir.attachment, so
        our check_access_rule('read') correctly blocks direct _get_stream_from
        calls. Attachment access for portal goes through /web/content
        with validate_access tokens, not through the model layer."""
        self._setup_mock_s3()
        portal_user = self._create_portal_user('portal_own')
        attachment = self.env['ir.attachment'].create({
            'name': 'portal_own.pdf',
            'raw': self.small_data,
            'type': 'binary',
            'mimetype': 'application/pdf',
            'res_model': 'res.partner',
            'res_id': portal_user.partner_id.id,
        })
        self._create_finalized_mapping(attachment)
        portal_env = self.env(user=portal_user)
        record = portal_env['ir.attachment'].browse(attachment.id)
        stream = portal_env['ir.binary']._get_stream_from(record, 'datas')
        self.assertIsNone(stream)

    def test_09_portal_user_cannot_read_unowned(self):
        """Portal user without access receives None (ACL blocked)."""
        self._setup_mock_s3()
        portal_user = self._create_portal_user('portal_noaccess')
        attachment = self.env['ir.attachment'].create({
            'name': 'restricted.pdf',
            'raw': self.small_data,
            'type': 'binary',
            'mimetype': 'application/pdf',
        })
        self._create_finalized_mapping(attachment)
        portal_env = self.env(user=portal_user)
        record = portal_env['ir.attachment'].browse(attachment.id)
        stream = portal_env['ir.binary']._get_stream_from(record, 'datas')
        self.assertIsNone(stream)

    def test_10_portal_user_company_isolation(self):
        """Portal user in Company B cannot read Company A attachment."""
        self._setup_mock_s3()
        company_b = self.env['res.company'].create({'name': 'Company B'})
        portal_user = self._create_portal_user('portal_cb', company=company_b)
        attachment = self.env['ir.attachment'].create({
            'name': 'company_a_doc.pdf',
            'raw': self.small_data,
            'type': 'binary',
            'mimetype': 'application/pdf',
        })
        self._create_finalized_mapping(attachment)
        portal_env = self.env(user=portal_user)
        record = portal_env['ir.attachment'].browse(attachment.id)
        stream = portal_env['ir.binary']._get_stream_from(record, 'datas')
        self.assertIsNone(stream)

    # ─────────────────────────────────────────────────────────────
    # 4. Large file — correctness and memory baseline
    # ─────────────────────────────────────────────────────────────

    def test_11_large_file_read_ok(self):
        """10MB attachment can be read from S3 correctly.

        Note: current implementation loads entire object into RAM.
        This test verifies correctness; true streaming is a future
        enhancement (see Batch 5).
        """
        size = 10 * 1024 * 1024
        large_data = os.urandom(size)
        checksum = hashlib.sha256(large_data).hexdigest()
        s3_key = 'objects/%s/%s' % (checksum[:2], checksum)
        self._setup_mock_s3(data=large_data, key=s3_key)
        attachment = self.env['ir.attachment'].create({
            'name': 'large_10mb.bin',
            'raw': large_data,
            'type': 'binary',
        })
        self._create_finalized_mapping(attachment, checksum=checksum, key=s3_key)
        stream = self.binary._get_stream_from(attachment, 'datas')
        self.assertIsNotNone(stream)
        self.assertEqual(len(stream.data), size)
        self.assertEqual(hashlib.sha256(stream.data).hexdigest(), checksum)
        self.assertEqual(stream.type, 'data')

    def test_12_large_file_filestore_preserved(self):
        """store_fname unchanged after S3 read of large attachment."""
        self._setup_mock_s3()
        large_data = b'X' * (2 * 1024 * 1024)
        checksum = hashlib.sha256(large_data).hexdigest()
        s3_key = 'objects/%s/%s' % (checksum[:2], checksum)
        self._setup_mock_s3(data=large_data, key=s3_key)
        attachment = self.env['ir.attachment'].create({
            'name': 'large_fname.bin',
            'raw': large_data,
            'type': 'binary',
        })
        original_fname = attachment.store_fname
        self._create_finalized_mapping(attachment, checksum=checksum, key=s3_key)
        self.binary._get_stream_from(attachment, 'datas')
        attachment.invalidate_cache()
        self.assertEqual(attachment.store_fname, original_fname)

    # ─────────────────────────────────────────────────────────────
    # 5. State boundary — non-finalized must not attempt S3
    # ─────────────────────────────────────────────────────────────

    def test_13_verified_not_finalized_falls_through(self):
        """Mapping in 'verified' state does NOT attempt S3 read."""
        attachment = self.env['ir.attachment'].create({
            'name': 'verified_only.txt',
            'raw': self.small_data,
            'type': 'binary',
        })
        Mapping = self.env['attachment.storage.mapping']
        mapping = Mapping.create_mapping(
            attachment_id=attachment.id,
            s3_bucket=self.test_bucket,
            s3_key=self.s3_key_small,
            s3_region='us-east-1',
        )
        mapping.action_update_status('uploading')
        mapping.action_update_status('uploaded')
        mapping.action_update_status('verified', checksum=self.checksum_small)
        # No S3 mock — should fall through, NOT raise MissingExternalObjectError
        # In Odoo 19, _get_stream_from requires HTTP request context for filestore reads
        stream = self.binary._get_stream_from(attachment, 'datas')
        self.assertIsNone(stream)

    def test_14_uploading_mapping_falls_through(self):
        """Mapping in 'uploading' state does NOT attempt S3 read."""
        attachment = self.env['ir.attachment'].create({
            'name': 'uploading_state.txt',
            'raw': self.small_data,
            'type': 'binary',
        })
        Mapping = self.env['attachment.storage.mapping']
        mapping = Mapping.create_mapping(
            attachment_id=attachment.id,
            s3_bucket=self.test_bucket,
            s3_key=self.s3_key_small,
            s3_region='us-east-1',
        )
        mapping.action_update_status('uploading')
        stream = self.binary._get_stream_from(attachment, 'datas')
        self.assertIsNone(stream)

    def test_15_failed_mapping_falls_through(self):
        """Mapping in 'failed' state does NOT attempt S3 read."""
        attachment = self.env['ir.attachment'].create({
            'name': 'failed_state.txt',
            'raw': self.small_data,
            'type': 'binary',
        })
        Mapping = self.env['attachment.storage.mapping']
        mapping = Mapping.create_mapping(
            attachment_id=attachment.id,
            s3_bucket=self.test_bucket,
            s3_key=self.s3_key_small,
            s3_region='us-east-1',
        )
        mapping.action_update_status('uploading')
        mapping.action_update_status('uploaded')
        mapping.action_mark_failed('test failure')
        stream = self.binary._get_stream_from(attachment, 'datas')
        self.assertIsNone(stream)

    # ─────────────────────────────────────────────────────────────
    # 6. Missing S3 object — error contract
    # ─────────────────────────────────────────────────────────────

    def test_16_finalized_missing_s3_falls_back(self):
        """Finalized mapping without S3 object falls back to filestore."""
        attachment = self.env['ir.attachment'].create({
            'name': 'missing_s3.txt',
            'raw': self.small_data,
            'type': 'binary',
        })
        self._create_finalized_mapping(attachment)
        stream = self.binary._get_stream_from(attachment, 'datas')
        self.assertEqual(stream.data, self.small_data)

    def test_17_missing_s3_fallback_preserves_attachment(self):
        """S3 fallback leaves the original attachment intact."""
        attachment = self.env['ir.attachment'].create({
            'name': 'debug_err.txt',
            'raw': self.small_data,
            'type': 'binary',
        })
        self._create_finalized_mapping(attachment)
        stream = self.binary._get_stream_from(attachment, 'datas')
        self.assertEqual(stream.data, self.small_data)
        self.assertTrue(attachment.exists())

    # ─────────────────────────────────────────────────────────────
    # 7. Regression — filestore unchanged
    # ─────────────────────────────────────────────────────────────

    def test_18_store_fname_unchanged_after_read(self):
        """store_fname preserved after S3 read when db_datas exists."""
        self._setup_mock_s3()
        attachment = self.env['ir.attachment'].create({
            'name': 'preserve_fname.txt',
            'raw': self.small_data,
            'type': 'binary',
        })
        original_fname = attachment.store_fname
        self._create_finalized_mapping(attachment)
        self.binary._get_stream_from(attachment, 'datas')
        attachment.invalidate_cache()
        self.assertEqual(attachment.store_fname, original_fname)

    def test_19_db_datas_not_cleared(self):
        """db_datas is preserved after S3 read."""
        self._setup_mock_s3()
        attachment = self.env['ir.attachment'].create({
            'name': 'preserve_datas.txt',
            'raw': self.small_data,
            'type': 'binary',
        })
        self.assertIsNot(False, attachment.db_datas or attachment.store_fname)
        self._create_finalized_mapping(attachment)
        self.binary._get_stream_from(attachment, 'datas')
        attachment.invalidate_cache()
        self.assertIsNot(False, attachment.db_datas or attachment.store_fname,
            'Either db_datas or store_fname must remain after read')

    # ─────────────────────────────────────────────────────────────
    # 8. Non-attachment pass-through
    # ─────────────────────────────────────────────────────────────

    def test_20_attachment_without_mapping_passthrough(self):
        """_get_stream_from on attachment without S3 mapping falls through to super."""
        attachment = self.env['ir.attachment'].create({
            'name': 'passthrough.txt',
            'raw': b'passthrough data',
            'type': 'binary',
        })
        stream = self.binary._get_stream_from(attachment, 'raw')
        self.assertIsNone(stream,
            'Attachment without S3 mapping returns None without HTTP context')

    # ─────────────────────────────────────────────────────────────
    # 9. Helper
    # ─────────────────────────────────────────────────────────────

    def _create_portal_user(self, login, company=None):
        groups = [(6, 0, [self.env.ref('base.group_portal').id])]
        vals = {
            'name': login,
            'login': '%s@test.com' % login,
            'groups_id': groups,
        }
        if company:
            vals['company_id'] = company.id
            vals['company_ids'] = [(6, 0, [company.id])]
        return self.env['res.users'].create(vals)

    def tearDown(self):
        if getattr(self, '_mock_aws', None):
            self._mock_aws.stop()
            self._mock_aws = None
        from unittest.mock import patch
        patch.stopall()
        super().tearDown()
