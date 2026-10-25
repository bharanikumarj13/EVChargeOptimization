def test_healthz_endpoint(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "EVCharge-Opt"
    assert data["database"] == "healthy"


def test_integration_health_endpoint(client):
    response = client.get("/api/v1/integration/health")
    assert response.status_code == 200
    data = response.json()
    assert data["is_mock"] is True
    assert data["provider_mode"] == "mock"
    assert "token" not in data  # No tokens exposed
