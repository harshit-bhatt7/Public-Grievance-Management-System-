"""
Central audit service (Step 8): the ONLY place that writes to
`audit_logs` or computes/verifies its SHA-256 hash chain. Every other
module (grievance_service, officer_service, privacy_service, routers)
calls `record_audit_event()` -- none of them touch hashing directly, per
the Step 8 requirement to centralize this rather than scatter it.

TAMPER-EVIDENT, not tamper-proof: a database administrator with direct
SQL access could still edit a row. What this guarantees is that such an
edit -- or a deleted or out-of-order-inserted record -- becomes
*detectable* by re-walking the chain with `verify_audit_chain()`.

## Canonicalization

Each record's `integrity_hash` is SHA-256 over a canonical JSON
representation of its own fields plus `previous_hash`:

    integrity_hash = SHA256(canonical_json({
        sequence_number, previous_hash, actor_id, action, entity_type,
        entity_id, grievance_id, old_value, new_value, metadata,
        ip_address, user_agent, timestamp
    }))

"Canonical JSON" here means: `json.dumps(..., sort_keys=True,
separators=(",", ":"), ensure_ascii=False)` -- sorted keys (so field
order in the dict never matters), no incidental whitespace, UTF-8, and
every non-JSON-native value (UUID, datetime, enum) converted to a fixed
string form *before* serialization so the same logical record always
produces byte-identical input to the hash, whether it was just built at
write time or re-read from the database at verify time.

## Chain scope

ONE global chronological chain -- not one per grievance or per entity --
ordered by `sequence_number` (a strictly-increasing integer, independent
of `timestamp`, which can theoretically tie under high write rates).
This makes whole-system verification a single linear walk. Filtering by
`grievance_id` (see `get_grievance_audit_trail`) reports only the
affected subset without ever using a different, weaker per-grievance
chain -- `verify_audit_chain` always walks the full global chain.

## Concurrency

`record_audit_event()` takes a PostgreSQL advisory transaction lock
(`pg_advisory_xact_lock`) scoped to a fixed key before reading the last
record and computing the next one. This serializes concurrent appenders
at the database level -- two transactions can never both read the same
"last record" and each compute a conflicting `previous_hash`/
`sequence_number`. The lock is automatically released when the
transaction commits or rolls back (that's what "xact" locks do), so no
manual unlock/cleanup code is needed. On SQLite (tests only -- this
project's single-connection, StaticPool-backed test harness never has
genuine concurrent writers), the lock call is skipped entirely, which is
safe in that context but is NOT a general concurrency guarantee for
SQLite; see docs/architecture.md for the live-PostgreSQL concurrency
verification this was tested against.
"""
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.request_context import get_ip_address, get_user_agent
from app.models.audit_log import AuditAction, AuditEntityType, AuditLog

logger = logging.getLogger(__name__)

# Explicit, deterministic genesis marker -- 64 hex zero characters, the
# same length as a real SHA-256 digest, so the column type/constraints
# never need a special case for "no previous record."
GENESIS_HASH = "0" * 64

# Arbitrary fixed key identifying "the audit chain" for pg_advisory_xact_lock.
# Any integer works; it only needs to be constant and unique to this
# purpose within the database (no other feature in this project uses
# advisory locks, so collision is not a concern).
_ADVISORY_LOCK_KEY = 8412907331224190

_MAX_USER_AGENT_LENGTH = 500


class AuditError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _json_default(value: Any) -> Any:
    """Fixed string conversion for values json.dumps can't natively
    serialize, applied identically at write time and at verify time."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (AuditAction, AuditEntityType)):
        return value.value
    raise TypeError(f"Object of type {type(value).__name__} is not canonically serializable")


def _canonical_json(value: Any) -> str:
    """Deterministic JSON serialization used as hash input: sorted keys,
    no incidental whitespace, UTF-8, stable handling of nulls/nested
    values via `default=_json_default`."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_json_default)


def _compute_integrity_hash(
    *,
    sequence_number: int,
    previous_hash: str,
    actor_id,
    action,
    entity_type,
    entity_id,
    grievance_id,
    old_value,
    new_value,
    event_metadata,
    ip_address,
    user_agent,
    timestamp: datetime,
) -> str:
    # Every timestamp in this system is always UTC (set via
    # datetime.now(timezone.utc) at write time). SQLite's
    # DateTime(timezone=True) does not reliably round-trip tzinfo on
    # SELECT — a value hashed as tz-aware at write time can come back
    # naive at verify time, changing its isoformat() string and therefore
    # its hash even with zero tampering. Normalizing any naive value back
    # to UTC here is a no-op for already-aware values (PostgreSQL) and
    # the correct fix for the SQLite round-trip case.
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    canonical = {
        "sequence_number": sequence_number,
        "previous_hash": previous_hash,
        "actor_id": actor_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "grievance_id": grievance_id,
        "old_value": old_value,
        "new_value": new_value,
        "metadata": event_metadata,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "timestamp": timestamp,
    }
    payload = _canonical_json(canonical).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def record_audit_event(
    db: Session,
    *,
    action: AuditAction,
    entity_type: AuditEntityType,
    actor_id=None,
    entity_id=None,
    grievance_id=None,
    old_value: dict | None = None,
    new_value: dict | None = None,
    event_metadata: dict | None = None,
) -> AuditLog:
    """
    Appends one record to the global audit hash chain, as part of the
    CALLER's existing transaction -- this function does not commit. If
    the caller's transaction later rolls back, the audit event rolls
    back with it, so an audit record can never describe an action that
    didn't actually happen (see grievance_service.create_grievance and
    update_grievance_status for the call sites this matters most for).

    `actor_id` is None for system-generated events (e.g. automatic
    department routing) -- never a fabricated user id. Never accepts
    `previous_hash` or `integrity_hash` as parameters at all: both are
    always computed here, server-side, from the current chain state --
    there is no code path by which a caller (and therefore no code path
    by which an HTTP client) could ever supply either value.
    """
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ADVISORY_LOCK_KEY})

    last = db.query(AuditLog).order_by(AuditLog.sequence_number.desc()).first()
    previous_hash = last.integrity_hash if last is not None else GENESIS_HASH
    next_sequence = (last.sequence_number + 1) if last is not None else 1

    timestamp = datetime.now(timezone.utc)
    ip_address = get_ip_address()
    user_agent = get_user_agent()
    if user_agent and len(user_agent) > _MAX_USER_AGENT_LENGTH:
        user_agent = user_agent[:_MAX_USER_AGENT_LENGTH]

    integrity_hash = _compute_integrity_hash(
        sequence_number=next_sequence,
        previous_hash=previous_hash,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        grievance_id=grievance_id,
        old_value=old_value,
        new_value=new_value,
        event_metadata=event_metadata,
        ip_address=ip_address,
        user_agent=user_agent,
        timestamp=timestamp,
    )

    record = AuditLog(
        sequence_number=next_sequence,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        grievance_id=grievance_id,
        old_value=old_value,
        new_value=new_value,
        event_metadata=event_metadata,
        ip_address=ip_address,
        user_agent=user_agent,
        timestamp=timestamp,
        previous_hash=previous_hash,
        integrity_hash=integrity_hash,
    )
    db.add(record)
    db.flush()  # assigns record.id; keeps sequence_number visible to any
    # subsequent record_audit_event call in the same transaction

    logger.info("Audit event recorded: seq=%s action=%s", next_sequence, action.value)
    return record


def verify_audit_chain(db: Session) -> dict:
    """
    Walks the ENTIRE global chain in sequence order (never a filtered
    subset -- filtering would let a gap outside the filter hide
    tampering) and recomputes every hash.

    Returns {"valid": True, "records_checked": N} or
    {"valid": False, "records_checked": N, "first_invalid_record": seq,
    "reason": "..."} -- the reason is a short category, never raw record
    content, so this is safe to return from a semi-restricted endpoint.
    """
    records = db.query(AuditLog).order_by(AuditLog.sequence_number.asc()).all()

    expected_previous = GENESIS_HASH
    expected_sequence = 1
    records_checked = 0

    for record in records:
        records_checked += 1

        if record.sequence_number != expected_sequence:
            return {
                "valid": False,
                "records_checked": records_checked,
                "first_invalid_record": record.sequence_number,
                "reason": "Missing or out-of-order sequence number.",
            }

        if record.previous_hash != expected_previous:
            return {
                "valid": False,
                "records_checked": records_checked,
                "first_invalid_record": record.sequence_number,
                "reason": "previous_hash does not match the prior record's integrity_hash.",
            }

        recomputed = _compute_integrity_hash(
            sequence_number=record.sequence_number,
            previous_hash=record.previous_hash,
            actor_id=record.actor_id,
            action=record.action,
            entity_type=record.entity_type,
            entity_id=record.entity_id,
            grievance_id=record.grievance_id,
            old_value=record.old_value,
            new_value=record.new_value,
            event_metadata=record.event_metadata,
            ip_address=record.ip_address,
            user_agent=record.user_agent,
            timestamp=record.timestamp,
        )
        if recomputed != record.integrity_hash:
            return {
                "valid": False,
                "records_checked": records_checked,
                "first_invalid_record": record.sequence_number,
                "reason": "Integrity hash mismatch.",
            }

        expected_previous = record.integrity_hash
        expected_sequence += 1

    return {"valid": True, "records_checked": records_checked}


def get_grievance_audit_trail(db: Session, grievance_id: uuid.UUID) -> list[AuditLog]:
    """Ownership/role authorization is the caller's responsibility (see
    routers/audit.py) -- this is a plain, restricted-by-caller-only query."""
    return (
        db.query(AuditLog)
        .filter(AuditLog.grievance_id == grievance_id)
        .order_by(AuditLog.sequence_number.asc())
        .all()
    )
