"""Tests for database connectivity and a basic model operation."""
from app.models.role import Role


def test_database_health_endpoint(client):
    response = client.get("/api/health/db")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["database"] == "connected"


def test_create_and_query_role(db_session):
    role = Role(name="citizen", description="A registered citizen user")
    db_session.add(role)
    db_session.commit()

    fetched = db_session.query(Role).filter_by(name="citizen").first()
    assert fetched is not None
    assert fetched.description == "A registered citizen user"
