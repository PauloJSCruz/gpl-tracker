"""Tests for vehicle, station, and refueling services."""
import pytest
from pathlib import Path
from gpl_tracker.models.database import init_db
from gpl_tracker.models.schemas import RefuelingCreate, VehicleCreate, RefuelingUpdate
from gpl_tracker.services.vehicle_service import VehicleService
from gpl_tracker.services.station_service import StationService
from gpl_tracker.services.refueling_service import RefuelingService


@pytest.fixture
def temp_db(tmp_path):
    """Fixture providing a clean temporary SQLite database."""
    db_file = tmp_path / "test_tracker.db"
    init_db(db_file)
    return db_file


def test_vehicle_service(temp_db):
    """Test getting and updating vehicle configuration."""
    v_service = VehicleService(db_path=temp_db)
    veh = v_service.get_vehicle(1)
    assert veh is not None
    assert veh.conversion_cost == 1500.0

    # Update vehicle
    updated = v_service.update_vehicle(1, VehicleCreate(
        make="Renault",
        model="Megane",
        engine="1.6 16V",
        conversion_cost=1650.0,
        conversion_date="2026-01-10",
        conversion_odometer=120000,
        petrol_consumption=7.5,
        lpg_consumption_increase=22.0
    ))
    assert updated.make == "Renault"
    assert updated.conversion_cost == 1650.0
    assert updated.lpg_consumption_increase == 22.0


def test_station_and_refueling_flow(temp_db):
    """Test complete flow: create station, add refueling, verify calculations and accumulations."""
    v_service = VehicleService(db_path=temp_db)
    s_service = StationService(db_path=temp_db)
    r_service = RefuelingService(db_path=temp_db)

    # 1. Search/Add station
    stations = s_service.search_stations("")
    assert isinstance(stations, list)

    # 2. Add first refueling
    # Scenario: Km: 450, GPL: 0.85, Gasolina: 1.75, Pago: 34.0, Aumento: 20%
    ref1 = r_service.add_refueling(RefuelingCreate(
        station_name="Galp Sintra",
        date="2026-09-01 10:00",
        distance_km=450.0,
        amount_paid=34.0,
        lpg_price=0.85,
        petrol_price=1.75,
        data_source="api"
    ))

    assert ref1.lpg_liters == 40.0
    assert pytest.approx(ref1.lpg_consumption, 0.01) == 8.89
    assert pytest.approx(ref1.equivalent_petrol_consumption, 0.01) == 7.41
    assert pytest.approx(ref1.savings, 0.02) == 24.33
    assert ref1.cumulative_savings == ref1.savings

    # Verify station was assigned and usage incremented
    st = s_service.get_station_by_id(ref1.station_id)
    assert st is not None
    assert st.use_count == 1

    # 3. Add second refueling
    ref2 = r_service.add_refueling(RefuelingCreate(
        station_id=ref1.station_id,
        date="2026-09-15 11:00",
        distance_km=500.0,
        amount_paid=38.0,
        lpg_price=0.85,
        petrol_price=1.75,
        data_source="api"
    ))
    # 38 / 0.85 = 44.7058 L -> 44.7058 / 500 * 100 = 8.941 L/100km
    # Equiv petrol: 8.941 / 1.20 = 7.451 L/100km
    # Cost petrol: 5 * 7.451 * 1.75 = 65.20 €
    # Savings: 65.20 - 38 = 27.20 €
    assert ref2.cumulative_savings == pytest.approx(ref1.savings + ref2.savings, 0.02)

    # 4. Check summary
    summary = r_service.get_dashboard_summary()
    assert summary.total_refuelings == 2
    assert summary.total_distance_km == 950.0
    assert summary.total_savings == pytest.approx(ref1.savings + ref2.savings, 0.02)
    # Span is 14 days, which is >= 7 days, so break-even time projection should be calculated
    assert summary.break_even.status == "recovering"
    assert summary.break_even.remaining_km is not None
    assert summary.break_even.remaining_months is not None


def test_refueling_crud_and_duplicate(temp_db):
    """Test updating, duplicating, and deleting refuelings."""
    r_service = RefuelingService(db_path=temp_db)

    # Add initial refueling
    ref = r_service.add_refueling(RefuelingCreate(
        station_name="Repsol Cascais",
        date="2026-08-01",
        distance_km=400.0,
        amount_paid=30.0,
        lpg_price=0.80,
        petrol_price=1.70,
        data_source="api"
    ))

    # Duplicate
    dup = r_service.duplicate_refueling(ref.id)
    assert dup is not None
    assert dup.id != ref.id
    assert dup.distance_km == ref.distance_km

    # Update
    updated = r_service.update_refueling(ref.id, RefuelingUpdate(
        amount_paid=32.0
    ))
    assert updated.amount_paid == 32.0

    # Delete
    deleted = r_service.delete_refueling(dup.id)
    assert deleted is True
    assert r_service.get_refueling(dup.id) is None


def test_station_search_intelligence(temp_db):
    """Test multi-token, unaccented, and municipality station search."""
    s_service = StationService(db_path=temp_db)

    # Search with Sintra
    sintra = s_service.search_stations("Sintra")
    assert len(sintra) > 0

    # Search with Repsol Cascais (multi-token matching brand + municipality)
    repsol_cascais = s_service.search_stations("Repsol Cascais")
    assert len(repsol_cascais) > 0
    assert all("repsol" in s.brand.lower() for s in repsol_cascais)

    # Search with accent normalization (Algueirao without tilde)
    algueirao = s_service.search_stations("Algueirao")
    assert len(algueirao) > 0

    # Filter by municipality
    filtered = s_service.search_stations("", municipality="Cascais")
    assert len(filtered) > 0
    assert all(s.municipality == "Cascais" for s in filtered)

