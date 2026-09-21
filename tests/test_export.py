"""Tests for CSV and Excel export services."""
import io
import pytest
import pandas as pd
from pathlib import Path
from gpl_tracker.models.database import init_db
from gpl_tracker.models.schemas import RefuelingCreate
from gpl_tracker.services.refueling_service import RefuelingService
from gpl_tracker.services.export_service import ExportService


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_export.db"
    init_db(db_file)
    return db_file


def test_export_csv_and_excel(temp_db):
    """Test generating both CSV and Excel exports from refueling records."""
    r_service = RefuelingService(db_path=temp_db)
    export_service = ExportService(db_path=temp_db)

    # Add sample refueling with unique name
    ref = r_service.add_refueling(RefuelingCreate(
        station_name="Posto Especial Teste",
        date="2026-09-10",
        distance_km=420.0,
        amount_paid=35.0,
        lpg_price=0.86,
        petrol_price=1.78,
        data_source="api"
    ))

    # Test CSV
    csv_bytes = export_service.export_csv()
    assert isinstance(csv_bytes, bytes)
    assert len(csv_bytes) > 0
    csv_text = csv_bytes.decode("utf-8-sig")
    assert "Posto Especial Teste" in csv_text
    assert "Poupança" in csv_text

    # Test Excel
    excel_bytes = export_service.export_excel()
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0

    # Parse excel bytes to ensure valid sheets
    excel_io = io.BytesIO(excel_bytes)
    excel_file = pd.ExcelFile(excel_io, engine="openpyxl")
    assert "Resumo Financeiro" in excel_file.sheet_names
    assert "Histórico Abastecimentos" in excel_file.sheet_names

    df_hist = pd.read_excel(excel_file, sheet_name="Histórico Abastecimentos")
    assert len(df_hist) == 1
    assert df_hist.iloc[0]["Posto"] == "Posto Especial Teste"

