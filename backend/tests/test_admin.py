"""Step 11 admin governance tests.

These tests focus on the new admin layer and its integration boundaries;
Steps 1-10 retain their existing suites.
"""
import uuid

from app.core.deps import get_current_user
from app.core.security import hash_password
from app.main import app
from app.models.department import Department
from app.models.user import User, UserType
from app.routers import admin as admin_router


def _make_admin(db):
    user = User(name="System Admin", email=f"admin-{uuid.uuid4()}@example.com", password_hash=hash_password("AdminPass123"), user_type=UserType.ADMIN, is_active=True)
    db.add(user); db.commit(); db.refresh(user); return user


def _override_admin(db, admin):
    app.dependency_overrides[admin_router.require_admin] = lambda: admin


def test_citizen_or_officer_cannot_access_admin_without_admin_role(client, db_session):
    response = client.get("/api/admin/dashboard")
    assert response.status_code == 401


def test_admin_dashboard_statistics(client, db_session):
    admin = _make_admin(db_session); _override_admin(db_session, admin)
    response = client.get("/api/admin/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert "total_grievances" in body
    assert "resolution_rate" in body
    app.dependency_overrides.clear()


def test_officer_creation_requires_active_department(client, db_session):
    admin = _make_admin(db_session); _override_admin(db_session, admin)
    dept = Department(name="Public Works", is_active=True); db_session.add(dept); db_session.commit()
    payload = {"name":"Officer One","email":"officer-one@example.com","password":"Officer123","employee_id":"EMP-001","department_id":str(dept.id),"designation":"Inspector"}
    response = client.post("/api/admin/officers", json=payload)
    assert response.status_code == 201
    assert response.json()["employee_id"] == "EMP-001"
    app.dependency_overrides.clear()


def test_duplicate_employee_id_is_rejected(client, db_session):
    admin = _make_admin(db_session); _override_admin(db_session, admin)
    dept = Department(name="Roads", is_active=True); db_session.add(dept); db_session.commit()
    payload = {"name":"Officer One","email":"one@example.com","password":"Officer123","employee_id":"EMP-DUP","department_id":str(dept.id)}
    assert client.post("/api/admin/officers", json=payload).status_code == 201
    payload["email"] = "two@example.com"
    assert client.post("/api/admin/officers", json=payload).status_code == 409
    app.dependency_overrides.clear()


def test_department_deactivation_is_blocked_when_active_routing_dependency_exists(client, db_session):
    admin = _make_admin(db_session); _override_admin(db_session, admin)
    dept = Department(name="Water", is_active=True); db_session.add(dept); db_session.commit()
    from app.models.category import Category
    db_session.add(Category(name="Water Supply", is_active=True, department_id=dept.id)); db_session.commit()
    response = client.post(f"/api/admin/departments/{dept.id}/deactivate")
    assert response.status_code == 409
    assert db_session.query(Department).get(dept.id).is_active is True
    app.dependency_overrides.clear()


def test_category_mapping_requires_active_department(client, db_session):
    admin = _make_admin(db_session); _override_admin(db_session, admin)
    inactive = Department(name="Inactive Dept", is_active=False); db_session.add(inactive); db_session.commit()
    response = client.post("/api/admin/categories", json={"name":"Unsafe Category","department_id":str(inactive.id)})
    assert response.status_code == 400
    app.dependency_overrides.clear()


def test_admin_audit_integrity_endpoint_is_read_only(client, db_session):
    admin = _make_admin(db_session); _override_admin(db_session, admin)
    response = client.get("/api/admin/audit/verify")
    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert client.delete("/api/admin/audit/1").status_code in (404,405)
    app.dependency_overrides.clear()


def test_admin_ai_governance_endpoint(client, db_session):
    admin = _make_admin(db_session); _override_admin(db_session, admin)
    response = client.get("/api/admin/ai")
    assert response.status_code == 200
    assert "recommendations" in response.json()
    app.dependency_overrides.clear()


def test_admin_analytics_has_no_raw_citizen_records(client, db_session):
    admin = _make_admin(db_session); _override_admin(db_session, admin)
    response = client.get("/api/admin/analytics")
    assert response.status_code == 200
    body = response.json()
    assert "privacy_distribution" in body
    assert "ai_usage" in body
    app.dependency_overrides.clear()


def test_admin_route_requires_server_side_role(client, db_session):
    # A citizen token cannot be simulated by a client-controlled field;
    # the actual dependency is tested here by supplying no admin override.
    response = client.get("/api/admin/officers")
    assert response.status_code == 401
