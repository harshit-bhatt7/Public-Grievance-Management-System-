"""
Shared pytest fixtures.

Uses an in-memory SQLite database for tests so the test suite doesn't
require a running PostgreSQL instance. Production code still uses
PostgreSQL — this is purely a lightweight test double for Step 1.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.utils.rate_limit import reset_rate_limits

TEST_DATABASE_URL = "sqlite:///:memory:"

# StaticPool ensures every connection (including ones made from the
# TestClient's background threadpool) shares the same in-memory database,
# rather than each getting its own empty :memory: database.
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Each test gets a clean rate-limit slate so tests don't interfere with each other."""
    reset_rate_limits()
    yield
    reset_rate_limits()


@pytest.fixture(autouse=True)
def _tmp_upload_dir(tmp_path, monkeypatch):
    """Redirect attachment storage to a pytest tmp directory instead of backend/uploads."""
    import app.utils.file_storage as file_storage

    monkeypatch.setattr(file_storage, "get_upload_root", lambda: tmp_path)
    yield


@pytest.fixture(scope="function")
def db_session():
    import app.models  # noqa: F401 ensures models are registered
    from app.models.department import Department
    from app.services.routing_service import GENERAL_GRIEVANCE_CELL_NAME

    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()

    # Every real environment guarantees a "General Grievance Cell" exists
    # (seeded by migration 0006) so routing always has a fallback — mirror
    # that guarantee here rather than making every test file responsible
    # for creating it.
    session.add(Department(name=GENERAL_GRIEVANCE_CELL_NAME, is_active=True))
    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _disable_external_notification_delivery(monkeypatch):
    import app.services.notification_service as notification_service
    monkeypatch.setattr(notification_service, "_queue_delivery", lambda notification_id: None)
    monkeypatch.setattr(notification_service, "SessionLocal", TestingSessionLocal)
    yield
