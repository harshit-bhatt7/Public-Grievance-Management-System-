"""
Live-PostgreSQL concurrency verification for the Step 8 audit hash chain.

Spins up N real OS threads, each with its OWN SQLAlchemy Session bound to
the actual running PostgreSQL database (not the SQLite test harness,
which uses a single shared connection and can't represent genuine
concurrent writers). Each thread independently calls
audit_service.record_audit_event() + commits, racing against the others.

If pg_advisory_xact_lock() is working correctly, the chain must remain
perfectly valid afterward: no two records with the same sequence_number,
no gaps, every previous_hash correctly linking to the prior record's
integrity_hash, regardless of the order the OS scheduled the threads in.
"""
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.audit_log import AuditAction, AuditEntityType
from app.services import audit_service

THREAD_COUNT = 20
errors = []


def worker(index: int):
    db = SessionLocal()
    try:
        audit_service.record_audit_event(
            db,
            action=AuditAction.GRIEVANCE_VIEWED,
            entity_type=AuditEntityType.GRIEVANCE,
            event_metadata={"concurrency_test_worker": index},
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        errors.append((index, str(exc)))
        db.rollback()
    finally:
        db.close()


def main():
    db = SessionLocal()
    before_count = db.query(audit_service.AuditLog).count()
    db.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(THREAD_COUNT)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"Spawned {THREAD_COUNT} concurrent threads, each writing one audit event.")
    print(f"Errors during concurrent writes: {len(errors)}")
    for idx, err in errors:
        print(f"  thread {idx}: {err}")

    db = SessionLocal()
    after_count = db.query(audit_service.AuditLog).count()
    sequence_numbers = [
        row[0] for row in db.query(audit_service.AuditLog.sequence_number).order_by(audit_service.AuditLog.sequence_number).all()
    ]
    unique_sequences = set(sequence_numbers)

    print(f"Records before: {before_count}, after: {after_count} (expected +{THREAD_COUNT})")
    print(f"Total records: {len(sequence_numbers)}, unique sequence_numbers: {len(unique_sequences)}")
    print(f"No duplicate sequence numbers: {len(sequence_numbers) == len(unique_sequences)}")

    result = audit_service.verify_audit_chain(db)
    print(f"Chain verification result: {result}")
    db.close()

    assert after_count == before_count + THREAD_COUNT, "Some concurrent writes were lost!"
    assert len(sequence_numbers) == len(unique_sequences), "Duplicate sequence numbers detected!"
    assert result["valid"] is True, "Chain is INVALID after concurrent writes!"
    print("\n✅ CONCURRENCY VERIFICATION PASSED: all concurrent writes present, "
          "no duplicate sequence numbers, chain remains fully valid.")


if __name__ == "__main__":
    main()
