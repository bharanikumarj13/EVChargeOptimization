def test_list_and_create_stations(client):
    # List initial
    resp = client.get("/api/v1/stations")
    assert resp.status_code == 200
    initial_count = len(resp.json())
    assert initial_count >= 2

    # Create new station
    new_station = {
        "station_id": "STN-NEW-01",
        "station_name": "New Test Station",
        "charger_count": 6,
        "available_chargers": 6,
        "charger_power_kw_per_charger": 50.0,
        "station_power_limit_kw": 250.0,
        "avg_session_minutes": 45.0,
        "grid_group_id": "GRID-METRO",
        "is_active": True,
    }
    create_resp = client.post("/api/v1/stations", json=new_station)
    assert create_resp.status_code == 201
    assert create_resp.json()["station_id"] == "STN-NEW-01"

    # Deactivate
    deact_resp = client.post("/api/v1/stations/STN-NEW-01/deactivate")
    assert deact_resp.status_code == 200
    assert deact_resp.json()["is_active"] is False


def test_station_creation_invalid_chargers(client):
    invalid = {
        "station_id": "STN-ERR",
        "station_name": "Err Station",
        "charger_count": 4,
        "available_chargers": 8,  # available > count
        "charger_power_kw_per_charger": 50.0,
        "station_power_limit_kw": 200.0,
        "avg_session_minutes": 45.0,
        "grid_group_id": "GRID-METRO",
        "is_active": True,
    }
    resp = client.post("/api/v1/stations", json=invalid)
    assert resp.status_code == 422


def test_station_partial_update_validation(client):
    # STN-01 has charger_count=8, available_chargers=8
    # Partial update: increase available_chargers above existing charger_count
    resp1 = client.put("/api/v1/stations/STN-01", json={"available_chargers": 12})
    assert resp1.status_code == 422
    assert "cannot exceed charger_count" in resp1.json()["detail"]

    # Partial update: lower charger_count below existing available_chargers
    resp2 = client.put("/api/v1/stations/STN-01", json={"charger_count": 4})
    assert resp2.status_code == 422
    assert "cannot exceed charger_count" in resp2.json()["detail"]

    # Valid partial update: lower available_chargers safely
    resp3 = client.put("/api/v1/stations/STN-01", json={"available_chargers": 5})
    assert resp3.status_code == 200
    assert resp3.json()["available_chargers"] == 5
    assert resp3.json()["charger_count"] == 8
