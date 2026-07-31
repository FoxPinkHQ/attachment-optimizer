import hashlib
import time
import logging

from odoo import _

_logger = logging.getLogger(__name__)

S3_CONFIG_KEYS = [
    'attachment_storage.s3.endpoint_url',
    'attachment_storage.s3.region',
    'attachment_storage.s3.access_key_id',
    'attachment_storage.s3.secret_access_key',
]

MAX_RETRIES = 3
RETRY_BACKOFF = 2.0


class S3BridgeError(Exception):
    pass


class S3Bridge:

    def __init__(self, env):
        self.env = env

    def _get_config(self):
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'endpoint_url': ICP.get_param('attachment_storage.s3.endpoint_url'),
            'region': ICP.get_param('attachment_storage.s3.region', 'us-east-1'),
            'access_key_id': ICP.get_param('attachment_storage.s3.access_key_id'),
            'secret_access_key': ICP.get_param('attachment_storage.s3.secret_access_key'),
        }

    def _get_client(self, config=None):
        try:
            import boto3
            from botocore.config import Config
        except ImportError:
            raise S3BridgeError(_('boto3 is not installed'))
        cfg = config or self._get_config()
        params = {
            'aws_access_key_id': cfg['access_key_id'],
            'aws_secret_access_key': cfg['secret_access_key'],
            'region_name': cfg['region'],
            'config': Config(
                connect_timeout=2,
                read_timeout=5,
                retries={'max_attempts': 1, 'mode': 'standard'},
            ),
        }
        if cfg.get('endpoint_url'):
            params['endpoint_url'] = cfg['endpoint_url']
        try:
            return boto3.client('s3', **params)
        except Exception as e:
            raise S3BridgeError(_('Failed to create S3 client: %s') % str(e))

    def _retry_call(self, fn, *args, **kwargs):
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return fn(*args, **kwargs)
            except S3BridgeError:
                raise
            except Exception as e:
                error_msg = str(e)
                if 'AccessDenied' in error_msg or 'InvalidAccessKeyId' in error_msg:
                    raise S3BridgeError(
                        _('S3 access denied — check credentials: %s') % error_msg
                    )
                last_error = e
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF ** attempt
                    _logger.warning(
                        'S3 attempt %d/%d failed, retrying in %.1fs: %s',
                        attempt, MAX_RETRIES, wait, error_msg,
                    )
                    time.sleep(wait)
        raise S3BridgeError(
            _('S3 operation failed after %d retries: %s') % (
                MAX_RETRIES, str(last_error)
            )
        )

    def head(self, bucket, key):
        def _do_head():
            client = self._get_client()
            client.head_object(Bucket=bucket, Key=key)
            return True
        try:
            return self._retry_call(_do_head)
        except S3BridgeError:
            return False

    def upload(self, bucket, key, data, checksum=None):
        def _do_upload():
            client = self._get_client()
            client.put_object(Bucket=bucket, Key=key, Body=data)
        self._retry_call(_do_upload)
        if checksum:
            return self.verify(bucket, key, checksum)
        return True

    def verify(self, bucket, key, expected_checksum):
        def _do_verify():
            client = self._get_client()
            obj = client.get_object(Bucket=bucket, Key=key)
            actual = hashlib.sha256(obj['Body'].read()).hexdigest()
            return actual == expected_checksum
        return self._retry_call(_do_verify)

    def get_object(self, bucket, key):
        try:
            client = self._get_client()
            obj = client.get_object(Bucket=bucket, Key=key)
            return obj['Body'].read()
        except S3BridgeError:
            raise
        except Exception as e:
            raise S3BridgeError(_('S3 read failed: %s') % str(e))

    def delete(self, bucket, key):
        def _do_delete():
            client = self._get_client()
            client.delete_object(Bucket=bucket, Key=key)
        self._retry_call(_do_delete)

    @staticmethod
    def compute_fingerprint(config):
        import json
        canonical = json.dumps(config, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def get_config_fingerprint(self, config=None, bucket=None):
        """Fingerprint the exact connection settings that were verified.

        The secret is represented only by its SHA-256 digest. This makes a
        credential rotation invalidate the verified state without putting the
        plaintext secret in the fingerprint payload.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        cfg = config or self._get_config()
        bucket = (
            bucket
            if bucket is not None
            else ICP.get_param('attachment_storage.s3.bucket', '')
        )
        secret = cfg.get('secret_access_key') or ''
        fingerprint_config = {
            'endpoint_url': cfg.get('endpoint_url') or '',
            'bucket': bucket or '',
            'region': cfg.get('region') or 'us-east-1',
            'access_key_id': cfg.get('access_key_id') or '',
            'secret_access_key_sha256': hashlib.sha256(
                secret.encode()
            ).hexdigest(),
        }
        return self.compute_fingerprint(fingerprint_config)

    def test_connection(self, config=None, bucket=None):
        ICP = self.env['ir.config_parameter'].sudo()
        cfg = config or self._get_config()
        bucket = bucket or ICP.get_param('attachment_storage.s3.bucket')

        if not bucket:
            return {
                'status': 'error',
                'error': 'S3 bucket is not configured.',
                'latency_ms': 0,
                'checks': [],
            }

        start = time.time()
        checks = []

        try:
            client = self._get_client(cfg)

            try:
                client.head_bucket(Bucket=bucket)
                checks.append({'name': 'Bucket Access', 'status': 'ok', 'detail': bucket})
            except Exception as e:
                err = str(e)
                checks.append({'name': 'Bucket Access', 'status': 'error', 'detail': err})
                return {
                    'status': 'error',
                    'error': err,
                    'latency_ms': int((time.time() - start) * 1000),
                    'checks': checks,
                }

            test_key = '.ao_health_check'
            try:
                client.put_object(Bucket=bucket, Key=test_key, Body=b'ok')
                client.delete_object(Bucket=bucket, Key=test_key)
                checks.append({'name': 'Write Permission', 'status': 'ok', 'detail': ''})
            except Exception as e:
                err = str(e)
                checks.append({'name': 'Write Permission', 'status': 'error', 'detail': err})

            latency = int((time.time() - start) * 1000)
            all_ok = all(c['status'] == 'ok' for c in checks)
            return {
                'status': 'ok' if all_ok else 'warning',
                'latency_ms': latency,
                'checks': checks,
                'error': '' if all_ok else checks[-1].get('detail', 'Unknown error'),
            }
        except Exception as e:
            return {
                'status': 'error',
                'latency_ms': int((time.time() - start) * 1000),
                'checks': checks,
                'error': str(e),
            }
