"""Tests for FastAPI HTTP endpoints for forgotten distance management."""
import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from gpl_tracker.models.database import init_db
from gpl_tracker.web.api import app, refueling_service


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    """Fixture providing a FastAPI TestClient configured with a temporary SQLite database."""
    test_db = tmp_path / "test_api_forgotten.db"
    init_db(test_db)

    # Re-point refueling_service to use test_db
    refueling_service.db_path = test_db
    refueling_service.vehicle_service.db_path = test_db
    refueling_service.station_service.db_path = test_db
    refueling_service.forgotten_service.db_path = test_db

    with TestClient(app) as client:
        yield client


def test_api_forgotten_distance_flow(client_with_db):
    """Test full HTTP API lifecycle for forgotten distance:

    1. GET /api/forgotten-km -> starts empty
    2. POST /api/forgotten-km -> creates entry
    3. PUT /api/forgotten-km/{id} -> updates entry
    4. POST /api/refuelings -> consumes pending km
    5. GET /api/forgotten-km -> empty again
    6. DELETE /api/refuelings/{id} -> releases forgotten km back to pending
    """
    client = client_with_db

    # 1. Initially empty
    res = client.get("/api/forgotten-km")
    assert res.status_code == 200
    data = res.json()
    assert data["pending_total_km"] == 0.0
    assert len(data["items"]) == 0

    # 2. Create entry (50 km)
    res = client.post("/api/forgotten-km", json={
        "distance_km": 50.0,
        "notes": "Reset tardio após abastecimento A"
    })
    assert res.status_code == 200
    entry = res.json()
    entry_id = entry["id"]
    assert entry["distance_km"] == 50.0
    assert entry["status"] == "pending"

    # Verify summary
    res = client.get("/api/forgotten-km")
    assert res.json()["pending_total_km"] == 50.0

    # 3. Update entry (change to 55 km)
    res = client.put(f"/api/forgotten-km/{entry_id}", json={
        "distance_km": 55.0,
        "notes": "Corrigido para 55 km"
    })
    assert res.status_code == 200
    assert res.json()["distance_km"] == 55.0

    # 4. Create refueling with entered 400 km
    # Total effective distance should be 400 + 55 = 455 km
    refuel_res = client.post("/api/refuelings", json={
        "date": "2026-09-25 14:00",
        "distance_km": 400.0,
        "amount_paid": 35.0,
        "lpg_price": 0.85,
        "petrol_price": 1.75,
        "apply_forgotten_km": True
    })
    assert refuel_res.status_code == 200
    refuel_data = refuel_res.json()
    refuel_id = refuel_data["id"]
    assert refuel_data["entered_distance_km"] == 400.0
    assert refuel_data["forgotten_distance_km"] == 55.0
    assert refuel_data["distance_km"] == 455.0

    # 5. Check forgotten km are now consumed/applied
    res = client.get("/api/forgotten-km")
    assert res.json()["pending_total_km"] == 0.0
    assert len(res.json()["items"]) == 0

    # 6. Delete refueling -> forgotten km must return to pending
    del_res = client.delete(f"/api/refuelings/{refuel_id}")
    assert del_res.status_code == 200

    res = client.get("/api/forgotten-km")
    assert res.json()["pending_total_km"] == 55.0
    assert len(res.json()["items"]) == 1
    assert res.json()["items"][0]["status"] == "pending"

    # 7. Delete forgotten km directly
    del_entry_res = client.delete(f"/api/forgotten-km/{entry_id}")
    assert del_entry_res.status_code == 200
    assert client.get("/api/forgotten-km").json()["pending_total_km"] == 0.0
