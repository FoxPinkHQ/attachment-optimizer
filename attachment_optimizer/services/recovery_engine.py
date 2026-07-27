import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from hashlib import sha256
from typing import Collection, Iterable, List, Optional

from odoo import fields

_logger = logging.getLogger(__name__)


class RecoveryRule(Enum):
    HEARTBEAT_TIMEOUT = 'heartbeat_timeout'
    INVALID_OWNERSHIP = 'invalid_ownership'
    PARTIAL_UPLOAD = 'partial_upload'
    VERIFY_MISMATCH = 'verify_mismatch'
    STALE_WORKER = 'stale_worker'


class RecoveryReason(Enum):
    HEARTBEAT_TIMEOUT = 'heartbeat_timeout'
    TOKEN_MISMATCH = 'token_mismatch'
    PARTIAL_UPLOAD = 'partial_upload'
    VERIFY_FAILED = 'verify_failed'
    STALE_WORKER = 'stale_worker'
    INVALID_OWNERSHIP = 'invalid_ownership'
    MANUAL = 'manual'


class RecoveryMode(Enum):
    DETECT_ONLY = 'detect_only'
    REPAIR = 'repair'


@dataclass(frozen=True)
class RecoveryEntry:
    operation_id: int
    rule: RecoveryRule
    reason: RecoveryReason
    repaired: bool


@dataclass(frozen=True)
class RecoveryReport:
    scanned: int = 0
    recovered: int = 0
    skipped: int = 0
    heartbeat_timeouts: int = 0
    ownership_repairs: int = 0
    partial_uploads: int = 0
    verification_repairs: int = 0
    stale_workers: int = 0
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_ms: int = 0
    entries: List[RecoveryEntry] = field(default_factory=list)
    errors: List[dict] = field(default_factory=list)


class RecoveryRuleHandler:
    rule: RecoveryRule
    priority: int = 500

    def detect(self, env, limit: int, skipped: set) -> Iterable[int]:
        raise NotImplementedError

    def repair(self, env, op_ids: List[int], reason: RecoveryReason) -> List[RecoveryEntry]:
        raise NotImplementedError

    def _audit(self, env, op, reason):
        env['attachment.audit.log']._log(
            'recover', result='success',
            reason=reason.value,
            rule=self.rule.value,
            attachment_id=op.attachment_id.id,
            operation_id=op.id,
        )


class HeartbeatTimeoutRule(RecoveryRuleHandler):
    rule = RecoveryRule.HEARTBEAT_TIMEOUT
    priority = 100
    TIMEOUT_MINUTES = 10

    def detect(self, env, limit, skipped):
        self.env = env
        env.cr.execute("""
            SELECT id FROM attachment_migration_operation
            WHERE state = 'uploading'
              AND processing_token IS NOT NULL
              AND heartbeat_at < %s::timestamp - INTERVAL '%s minutes'
              AND id != ALL(%s)
            ORDER BY id
            LIMIT %s
        """, (fields.Datetime.now().isoformat(), self.TIMEOUT_MINUTES,
              list(skipped) if skipped else [0], limit))
        return [r[0] for r in env.cr.fetchall()]

    def repair(self, env, op_ids, reason):
        entries = []
        for op in env['attachment.migration.operation'].browse(op_ids):
            op.transition_state('queued')
            self._audit(env, op, reason)
            entries.append(RecoveryEntry(
                operation_id=op.id, rule=self.rule,
                reason=reason, repaired=True,
            ))
        return entries


class InvalidOwnershipRule(RecoveryRuleHandler):
    rule = RecoveryRule.INVALID_OWNERSHIP
    priority = 200

    def detect(self, env, limit, skipped):
        env.cr.execute("""
            SELECT id FROM attachment_migration_operation
            WHERE state = 'uploading'
              AND processing_token IS NOT NULL
              AND worker_id IS NULL
              AND id != ALL(%s)
            ORDER BY id
            LIMIT %s
        """, (list(skipped) if skipped else [0], limit))
        return [r[0] for r in env.cr.fetchall()]

    def repair(self, env, op_ids, reason):
        entries = []
        for op in env['attachment.migration.operation'].browse(op_ids):
            op.transition_state('queued')
            self._audit(env, op, reason)
            entries.append(RecoveryEntry(
                operation_id=op.id, rule=self.rule,
                reason=reason, repaired=True,
            ))
        return entries


class PartialUploadRule(RecoveryRuleHandler):
    rule = RecoveryRule.PARTIAL_UPLOAD
    priority = 400

    def detect(self, env, limit, skipped):
        self.env = env
        try:
            from ..services.s3_bridge import S3Bridge
            self.s3 = S3Bridge(env)
        except Exception:
            return []
        env.cr.execute("""
            SELECT op.id, mp.s3_bucket, mp.s3_key, mp.checksum_sha256
            FROM attachment_migration_operation op
            INNER JOIN attachment_storage_mapping mp ON mp.id = op.mapping_id
            WHERE op.state = 'failed'
              AND mp.status IN ('uploaded', 'verified')
              AND mp.s3_key IS NOT NULL
              AND op.id != ALL(%s)
            ORDER BY op.id
            LIMIT %s
        """, (list(skipped) if skipped else [0], limit))
        self._pending = [(r[0], r[1], r[2], r[3]) for r in env.cr.fetchall()]
        return [r[0] for r in self._pending]

    def repair(self, env, op_ids, reason):
        entries = []
        pending = [p for p in self._pending if p[0] in op_ids]
        for op_id, bucket, key, expected_checksum in pending:
            op = env['attachment.migration.operation'].browse(op_id)
            try:
                if not self.s3.head(bucket, key):
                    entries.append(RecoveryEntry(
                        operation_id=op_id, rule=self.rule,
                        reason=RecoveryReason.PARTIAL_UPLOAD, repaired=False,
                    ))
                    continue
                raw_data = self.s3.get_object(bucket, key)
                actual_checksum = sha256(raw_data).hexdigest()
                if expected_checksum and actual_checksum != expected_checksum:
                    entries.append(RecoveryEntry(
                        operation_id=op_id, rule=self.rule,
                        reason=RecoveryReason.VERIFY_FAILED, repaired=False,
                    ))
                    continue
                op.transition_state('finalized', completed_at=fields.Datetime.now())
                if op.mapping_id:
                    op.mapping_id.transition_status('finalized')
                self._audit(env, op, RecoveryReason.PARTIAL_UPLOAD)
                entries.append(RecoveryEntry(
                    operation_id=op_id, rule=self.rule,
                    reason=RecoveryReason.PARTIAL_UPLOAD, repaired=True,
                ))
            except Exception as e:
                _logger.warning('PartialUpload repair failed for op %s: %s', op_id, e)
                entries.append(RecoveryEntry(
                    operation_id=op_id, rule=self.rule,
                    reason=RecoveryReason.PARTIAL_UPLOAD, repaired=False,
                ))
        return entries


class VerifyMismatchRule(RecoveryRuleHandler):
    rule = RecoveryRule.VERIFY_MISMATCH
    priority = 500

    def detect(self, env, limit, skipped):
        env.cr.execute("""
            SELECT op.id FROM attachment_migration_operation op
            INNER JOIN attachment_storage_mapping mp ON mp.id = op.mapping_id
            WHERE op.state = 'failed'
              AND mp.status = 'verification_failed'
              AND op.id != ALL(%s)
            ORDER BY op.id
            LIMIT %s
        """, (list(skipped) if skipped else [0], limit))
        return [r[0] for r in env.cr.fetchall()]

    def repair(self, env, op_ids, reason):
        entries = []
        for op in env['attachment.migration.operation'].browse(op_ids):
            op.transition_state('queued')
            if op.mapping_id:
                op.mapping_id.unlink()
            self._audit(env, op, reason)
            entries.append(RecoveryEntry(
                operation_id=op.id, rule=self.rule,
                reason=reason, repaired=True,
            ))
        return entries


class StaleWorkerRule(RecoveryRuleHandler):
    rule = RecoveryRule.STALE_WORKER
    priority = 300

    def detect(self, env, limit, skipped):
        env.cr.execute("""
            SELECT id FROM attachment_migration_operation
            WHERE state = 'uploading'
              AND processing_token IS NOT NULL
              AND (worker_id IS NULL OR claimed_at IS NULL)
              AND id != ALL(%s)
            ORDER BY id
            LIMIT %s
        """, (list(skipped) if skipped else [0], limit))
        return [r[0] for r in env.cr.fetchall()]

    def repair(self, env, op_ids, reason):
        entries = []
        for op in env['attachment.migration.operation'].browse(op_ids):
            op.transition_state('queued')
            self._audit(env, op, reason)
            entries.append(RecoveryEntry(
                operation_id=op.id, rule=self.rule,
                reason=reason, repaired=True,
            ))
        return entries


_HANDLERS = {
    RecoveryRule.HEARTBEAT_TIMEOUT: HeartbeatTimeoutRule(),
    RecoveryRule.INVALID_OWNERSHIP: InvalidOwnershipRule(),
    RecoveryRule.PARTIAL_UPLOAD: PartialUploadRule(),
    RecoveryRule.VERIFY_MISMATCH: VerifyMismatchRule(),
    RecoveryRule.STALE_WORKER: StaleWorkerRule(),
}

_RULE_REASONS = {
    RecoveryRule.HEARTBEAT_TIMEOUT: RecoveryReason.HEARTBEAT_TIMEOUT,
    RecoveryRule.INVALID_OWNERSHIP: RecoveryReason.INVALID_OWNERSHIP,
    RecoveryRule.PARTIAL_UPLOAD: RecoveryReason.PARTIAL_UPLOAD,
    RecoveryRule.VERIFY_MISMATCH: RecoveryReason.VERIFY_FAILED,
    RecoveryRule.STALE_WORKER: RecoveryReason.STALE_WORKER,
}

_SORTED_RULES = sorted(
    RecoveryRule,
    key=lambda r: _HANDLERS[r].priority,
)


class RecoveryEngine:
    def __init__(self, env):
        self.env = env

    def recover(
        self,
        rules: Optional[Collection[RecoveryRule]] = None,
        limit: Optional[int] = None,
        mode: RecoveryMode = RecoveryMode.REPAIR,
    ) -> RecoveryReport:
        started_at = datetime.utcnow()
        active_rules = rules or _SORTED_RULES
        remaining = limit or 2**31
        all_entries = []
        scanned = 0
        errors = []
        counter = defaultdict(int)

        for rule_enum in _SORTED_RULES:
            if rule_enum not in active_rules or remaining <= 0:
                continue
            handler = _HANDLERS[rule_enum]
            try:
                op_ids = list(handler.detect(self.env, remaining, set()))
                scanned += len(op_ids)
                if not op_ids:
                    continue
                if mode == RecoveryMode.REPAIR:
                    skipped_ids = set()
                    entries = handler.repair(
                        self.env, op_ids,
                        reason=_RULE_REASONS[rule_enum],
                    )
                    for e in entries:
                        if e.repaired:
                            counter[rule_enum] += 1
                            remaining -= 1
                        else:
                            skipped_ids.add(e.operation_id)
                    all_entries.extend(entries)
            except Exception as e:
                _logger.exception('Rule %s failed', rule_enum.value)
                errors.append({
                    'rule': rule_enum.value,
                    'reason': str(e),
                })

        completed_at = datetime.utcnow()
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)
        report_kwargs = {
            'scanned': scanned,
            'recovered': sum(counter.values()),
            'skipped': scanned - sum(counter.values()),
            'heartbeat_timeouts': counter.get(RecoveryRule.HEARTBEAT_TIMEOUT, 0),
            'ownership_repairs': counter.get(RecoveryRule.INVALID_OWNERSHIP, 0),
            'partial_uploads': counter.get(RecoveryRule.PARTIAL_UPLOAD, 0),
            'verification_repairs': counter.get(RecoveryRule.VERIFY_MISMATCH, 0),
            'stale_workers': counter.get(RecoveryRule.STALE_WORKER, 0),
            'started_at': started_at,
            'completed_at': completed_at,
            'duration_ms': duration_ms,
            'entries': all_entries,
            'errors': errors,
        }
        return RecoveryReport(**report_kwargs)
