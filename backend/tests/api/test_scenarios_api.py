def test_list_scenarios(client):
    resp = client.get("/api/v1/scenarios")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "scenario_id" in data[0]
    assert "name" in data[0]
    assert "selected_forecast_id" in data[0]


def test_create_and_get_scenario(client):
    new_scenario = {
        "scenario_id": "SCN-TEST-API",
        "name": "API Test Scenario",
        "description": "Created for scenario API test suite",
        "selected_forecast_id": "FC-001",
        "objective_code": "PROPORTIONAL_CONSTRAINED",
        "active_station_ids": ["STN-01", "STN-02"],
        "max_iterations": 5,
    }
    create_resp = client.post("/api/v1/scenarios", json=new_scenario)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    assert created_data["scenario_id"] == "SCN-TEST-API"
    assert created_data["name"] == "API Test Scenario"
    assert created_data["allocation_count"] == 0

    # Retrieve by ID
    get_resp = client.get("/api/v1/scenarios/SCN-TEST-API")
    assert get_resp.status_code == 200
    assert get_resp.json()["scenario_id"] == "SCN-TEST-API"


def test_create_scenario_duplicate_conflict(client):
    dup = {
        "scenario_id": "SCN-TEST-01",  # Pre-existing in test DB fixture
        "name": "Duplicate Scenario",
        "description": "Should fail with conflict",
        "selected_forecast_id": "FC-001",
        "objective_code": "PROPORTIONAL_CONSTRAINED",
    }
    resp = client.post("/api/v1/scenarios", json=dup)
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


def test_get_nonexistent_scenario(client):
    resp = client.get("/api/v1/scenarios/SCN-NONEXISTENT-999")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_scenario_iterations_trace(client):
    # Existing seeded scenario
    resp = client.get("/api/v1/scenarios/SCN-TEST-01/iterations")
    assert resp.status_code == 200
    iterations = resp.json()
    assert isinstance(iterations, list)

    # Nonexistent scenario iterations
    err_resp = client.get("/api/v1/scenarios/SCN-NONEXISTENT-999/iterations")
    assert err_resp.status_code == 404
