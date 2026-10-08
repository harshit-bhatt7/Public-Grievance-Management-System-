"""Step 13 public statistics regression and privacy tests."""
from datetime import datetime, timedelta, timezone
import uuid

from app.models.category import Category
from app.models.department import Department
from app.models.grievance import Grievance, GrievanceStatus, PrivacyMode
from app.models.grievance_status_history import GrievanceStatusHistory
from app.models.public_statistics import CivicRankingConfig
from app.models.resolution import Resolution, ResolutionDispute, ResolutionFeedback
from app.models.user import User, UserType


def _seed(db, *, count=5, location="Pune", submitted_at=None, resolution_days=5):
    user = db.query(User).first()
    if user is None:
        user = User(name="Test Citizen", email=f"citizen-{uuid.uuid4()}@example.com", password_hash="x", user_type=UserType.CITIZEN)
        db.add(user)
    category = db.query(Category).first()
    if category is None:
        category = Category(name=f"Roads {uuid.uuid4()}", is_active=True)
        db.add(category)
    department = db.query(Department).filter(Department.name != "General Grievance Cell").first()
    if department is None:
        department = Department(name=f"PWD {uuid.uuid4()}", is_active=True)
        db.add(department)
    db.flush()
    submitted_at = submitted_at or datetime.now(timezone.utc) - timedelta(days=10)
    for i in range(count):
        g = Grievance(
            grievance_number=f"STEP13-{uuid.uuid4().hex[:20]}",
            citizen_id=user.id,
            category_id=category.id,
            department_id=department.id,
            title="Test grievance",
            description="Test data only",
            status=GrievanceStatus.RESOLVED,
            privacy_mode=PrivacyMode.IDENTITY_PROTECTED,
            state="Maharashtra",
            district=location,
            taluka="Haveli",
            village=f"Village {i}",
            submitted_at=submitted_at,
            created_at=submitted_at,
        )
        db.add(g)
        db.flush()
        db.add(GrievanceStatusHistory(grievance_id=g.id, old_status=None, new_status=GrievanceStatus.SUBMITTED, changed_at=submitted_at))
        resolution = Resolution(
            grievance_id=g.id,
            resolution_summary="Resolved",
            actions_taken="Completed",
            resolution_date=submitted_at + timedelta(days=resolution_days),
        )
        db.add(resolution)
        db.flush()
        db.add(ResolutionFeedback(resolution_id=resolution.id, grievance_id=g.id, accepted=True, rating=4))
    db.commit()
    return category


def test_public_summary_exposes_pending_and_dispute_rates(client, db_session):
    _seed(db_session, count=5)
    response = client.get("/api/public/statistics/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["pending_rate"] == 0
    assert body["dispute_rate"] == 0


def test_malformed_category_and_department_ids_return_400(client):
    assert client.get("/api/public/statistics/summary?category_id=bad").status_code == 400
    assert client.get("/api/public/statistics/summary?department_id=bad").status_code == 400


def test_trend_buckets_below_threshold_are_suppressed(client, db_session):
    _seed(db_session, count=5)
    # A single older record creates a bucket below the default threshold.
    user = db_session.query(User).first()
    category = db_session.query(Category).first()
    old = datetime.now(timezone.utc) - timedelta(days=100)
    g = Grievance(
        grievance_number=f"STEP13-{uuid.uuid4().hex[:20]}", citizen_id=user.id, category_id=category.id,
        title="Old", description="Old", status=GrievanceStatus.SUBMITTED,
        privacy_mode=PrivacyMode.IDENTITY_PROTECTED, state="Maharashtra", district="Pune",
        submitted_at=old, created_at=old,
    )
    db_session.add(g); db_session.commit()
    body = client.get("/api/public/statistics/trends?period=monthly").json()
    assert all(item["total"] >= body["minimum_sample_size"] for item in body["items"])


def test_category_leaderboard_and_most_improved_are_public(client, db_session):
    now = datetime.now(timezone.utc)
    category = _seed(db_session, count=5, location="Pune", submitted_at=now - timedelta(days=10), resolution_days=3)
    _seed(db_session, count=5, location="Pune", submitted_at=now - timedelta(days=40), resolution_days=20)
    response = client.get(f"/api/public/statistics/rankings/district/category/{category.id}")
    assert response.status_code == 200
    assert response.json()["leaderboard_type"] == "category"
    improved = client.get("/api/public/statistics/most-improved?level=district&period=monthly")
    assert improved.status_code == 200
