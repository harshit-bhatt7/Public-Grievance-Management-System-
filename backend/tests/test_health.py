"""Tests for the root and health-check endpoints."""


def test_read_root(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
