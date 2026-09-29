"""Tests for forgotten distance (late odometer reset compensation) lifecycle and calculations."""
import pytest
from pathlib import Path
from gpl_tracker.models.database import init_db
from gpl_tracker.models.schemas import (
    ForgottenDistanceCreate,
    ForgottenDistanceUpdate,
    RefuelingCreate,
    RefuelingUpdate
)
from gpl_tracker.services.vehicle_service import VehicleService
from gpl_tracker.services.refueling_service import RefuelingService
from gpl_tracker.services.forgotten_distance_service import ForgottenDistanceService
from gpl_tracker.services.export_service import ExportService


@pytest.fixture
def temp_db(tmp_path):
    """Fixture providing a clean temporary SQLite database."""
    db_file = tmp_path / "test_forgotten.db"
    init_db(db_file)
    return db_file


def test_forgotten_distance_crud(temp_db):
    """Test adding, listing, updating, and deleting forgotten distance entries."""
    f_service = ForgottenDistanceService(db_path=temp_db)

    # 1. Add forgotten distance
    log = f_service.add_forgotten_distance(ForgottenDistanceCreate(
        distance_km=50.0,
        notes="Reset tardio após abastecer na Galp"
    ))
    assert log is not None
    assert log.distance_km == 50.0
    assert log.status == "pending"
    assert log.notes == "Reset tardio após abastecer na Galp"

    # 2. Check pending summary
    summary = f_service.get_pending_summary(vehicle_id=1)
    assert summary.pending_total_km == 50.0
    assert len(summary.items) == 1

    # 3. Add second entry
    log2 = f_service.add_forgotten_distance(ForgottenDistanceCreate(
        distance_km=25.5,
        notes="Outro esquecimento"
    ))
    summary2 = f_service.get_pending_summary(vehicle_id=1)
    assert summary2.pending_total_km == 75.5
    assert len(summary2.items) == 2

    # 4. Update entry
    updated = f_service.update_record(log.id, ForgottenDistanceUpdate(
        distance_km=60.0,
        notes="Corrigido: 60 km percorridos"
    ))
    assert updated.distance_km == 60.0
    assert updated.notes == "Corrigido: 60 km percorridos"

    summary3 = f_service.get_pending_summary(vehicle_id=1)
    assert summary3.pending_total_km == 85.5

    # 5. Delete entry
    deleted = f_service.delete_record(log2.id)
    assert deleted is True

    summary4 = f_service.get_pending_summary(vehicle_id=1)
    assert summary4.pending_total_km == 60.0
    assert len(summary4.items) == 1


def test_forgotten_distance_applied_to_next_refueling(temp_db):
    """Test the complete user problem flow:

    1. Abastecimento A -> 300 km
    2. Esquece-se de fazer reset, conduz 50 km, e faz reset.
    3. Regista 50 km esquecidos.
    4. No Abastecimento B, conta-quilómetros indica 400 km.
    5. A aplicação calcula com base em 450 km efetivos (400 + 50).
    6. Os 50 km deixam de estar pendentes.
    7. No Abastecimento C, não são aplicados novamente.
    """
    r_service = RefuelingService(db_path=temp_db)
    f_service = ForgottenDistanceService(db_path=temp_db)

    # 1. Abastecimento A
    ref_a = r_service.add_refueling(RefuelingCreate(
        date="2026-09-01 10:00",
        distance_km=300.0,
        amount_paid=25.0,
        lpg_price=0.85,
        petrol_price=1.75
    ))
    assert ref_a.distance_km == 300.0
    assert ref_a.entered_distance_km == 300.0
    assert ref_a.forgotten_distance_km == 0.0

    # 2. Utilizador regista 50 km esquecidos
    f_log = f_service.add_forgotten_distance(ForgottenDistanceCreate(
        distance_km=50.0,
        notes="Reset esquecido após abastecimento A"
    ))
    assert f_log.status == "pending"

    # Verificar que o dashboard e abastecimento A não foram alterados retroativamente!
    dash1 = r_service.get_dashboard_summary()
    assert dash1.total_distance_km == 300.0

    # 3. Abastecimento B: utilizador introduz 400 km
    # Parâmetros: 400 km introduzidos, 34 € pagos, GPL 0.85 €, Gasolina 1.75 €
    # Com 50 km esquecidos compensados:
    # Km efetivos: 450 km
    # Litros: 34 / 0.85 = 40.0 L
    # Consumo GPL: (40 / 450) * 100 = 8.89 L/100 km (em vez de 40 / 400 = 10.0!)
    ref_b = r_service.add_refueling(RefuelingCreate(
        date="2026-09-10 12:00",
        distance_km=400.0,
        amount_paid=34.0,
        lpg_price=0.85,
        petrol_price=1.75,
        apply_forgotten_km=True
    ))

    assert ref_b.entered_distance_km == 400.0
    assert ref_b.forgotten_distance_km == 50.0
    assert ref_b.distance_km == 450.0
    assert pytest.approx(ref_b.lpg_consumption, 0.01) == 8.89
    assert pytest.approx(ref_b.savings, 0.02) == 24.33

    # 4. Verificar que os km esquecidos agora estão aplicados e NÃO pendentes
    pending_after_b = f_service.get_pending_summary()
    assert pending_after_b.pending_total_km == 0.0
    assert len(pending_after_b.items) == 0

    log_check = f_service.get_record(f_log.id)
    assert log_check.status == "applied"
    assert log_check.applied_refueling_id == ref_b.id

    # 5. Abastecimento C: verificar que os 50 km NÃO são consumidos novamente!
    ref_c = r_service.add_refueling(RefuelingCreate(
        date="2026-09-20 15:00",
        distance_km=350.0,
        amount_paid=30.0,
        lpg_price=0.85,
        petrol_price=1.75,
        apply_forgotten_km=True
    ))
    assert ref_c.entered_distance_km == 350.0
    assert ref_c.forgotten_distance_km == 0.0
    assert ref_c.distance_km == 350.0


def test_delete_refueling_restores_forgotten_km(temp_db):
    """Test rule: if refueling is deleted, forgotten km are NOT lost and return to pending."""
    r_service = RefuelingService(db_path=temp_db)
    f_service = ForgottenDistanceService(db_path=temp_db)

    # Register 45 km forgotten
    f_log = f_service.add_forgotten_distance(ForgottenDistanceCreate(
        distance_km=45.0,
        notes="Esqueci-me na Autoestrada"
    ))

    # Add refueling applying these 45 km
    ref = r_service.add_refueling(RefuelingCreate(
        date="2026-09-05 10:00",
        distance_km=300.0,
        amount_paid=25.0,
        lpg_price=0.85,
        petrol_price=1.75
    ))
    assert ref.distance_km == 345.0
    assert ref.forgotten_distance_km == 45.0

    # Ensure no pending km
    assert f_service.get_pending_summary().pending_total_km == 0.0

    # Delete refueling
    success = r_service.delete_refueling(ref.id)
    assert success is True

    # VERIFY: forgotten km restored to pending!
    restored_summary = f_service.get_pending_summary()
    assert restored_summary.pending_total_km == 45.0
    assert len(restored_summary.items) == 1
    assert restored_summary.items[0].status == "pending"
    assert restored_summary.items[0].applied_refueling_id is None


def test_duplicate_refueling_does_not_duplicate_forgotten_km(temp_db):
    """Test rule: duplicating a refueling must NOT duplicate past forgotten km."""
    r_service = RefuelingService(db_path=temp_db)
    f_service = ForgottenDistanceService(db_path=temp_db)

    f_service.add_forgotten_distance(ForgottenDistanceCreate(distance_km=50.0))
    ref = r_service.add_refueling(RefuelingCreate(
        date="2026-09-01",
        distance_km=400.0,
        amount_paid=34.0,
        lpg_price=0.85,
        petrol_price=1.75
    ))
    assert ref.distance_km == 450.0
    assert ref.entered_distance_km == 400.0
    assert ref.forgotten_distance_km == 50.0

    # Duplicate
    dup = r_service.duplicate_refueling(ref.id)
    assert dup is not None
    # Duplicate should take the entered 400 km, NOT 450 km, and have 0 forgotten km
    assert dup.entered_distance_km == 400.0
    assert dup.forgotten_distance_km == 0.0
    assert dup.distance_km == 400.0


def test_inline_custom_forgotten_km_on_refueling(temp_db):
    """Test entering forgotten km directly on the refueling form."""
    r_service = RefuelingService(db_path=temp_db)
    f_service = ForgottenDistanceService(db_path=temp_db)

    ref = r_service.add_refueling(RefuelingCreate(
        date="2026-09-08",
        distance_km=370.0,
        amount_paid=32.0,
        lpg_price=0.85,
        petrol_price=1.75,
        custom_forgotten_km=30.0
    ))

    assert ref.entered_distance_km == 370.0
    assert ref.forgotten_distance_km == 30.0
    assert ref.distance_km == 400.0

    all_logs = f_service.get_pending_summary()
    assert all_logs.pending_total_km == 0.0


def test_export_includes_forgotten_km(temp_db):
    """Test that CSV and Excel exports cleanly distinguish entered and forgotten distance."""
    r_service = RefuelingService(db_path=temp_db)
    f_service = ForgottenDistanceService(db_path=temp_db)
    export_service = ExportService(db_path=temp_db)

    f_service.add_forgotten_distance(ForgottenDistanceCreate(distance_km=50.0))
    r_service.add_refueling(RefuelingCreate(
        station_name="Posto Teste Export",
        date="2026-09-10",
        distance_km=400.0,
        amount_paid=34.0,
        lpg_price=0.85,
        petrol_price=1.75
    ))

    # Test CSV output
    csv_bytes = export_service.export_csv()
    csv_text = csv_bytes.decode("utf-8-sig")
    assert "Km Introduzidos" in csv_text
    assert "Km Esquecidos" in csv_text
    assert "Km Percorridos" in csv_text
    assert "400" in csv_text
    assert "50" in csv_text
    assert "450" in csv_text


def test_invalid_forgotten_distance_raises_error(temp_db):
    """Test validation errors for non-positive distance."""
    f_service = ForgottenDistanceService(db_path=temp_db)
    with pytest.raises(ValueError):
        f_service.add_forgotten_distance(ForgottenDistanceCreate(distance_km=0.0))
    with pytest.raises(ValueError):
        f_service.add_forgotten_distance(ForgottenDistanceCreate(distance_km=-10.0))
