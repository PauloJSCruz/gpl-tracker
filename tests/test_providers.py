"""Tests for providers, price parsing, and fallback strategy."""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from gpl_tracker.models.database import init_db, get_connection
from gpl_tracker.providers.dgeg_provider import parse_price_string, DGEGProvider
from gpl_tracker.providers.cached_provider import CachedFuelProvider


def test_parse_price_string():
    """Verify robust parsing of Portuguese formatted price strings."""
    assert parse_price_string("0,859 €/litro") == 0.859
    assert parse_price_string("1,749 €") == 1.749
    assert parse_price_string("0.85") == 0.85
    assert parse_price_string(0.85) == 0.85
    assert parse_price_string(None) is None
    assert parse_price_string("inválido") is None


def test_dgeg_provider_parsing_fuels():
    """Verify that DGEG fuel list is correctly parsed into GPL and Petrol 95."""
    provider = DGEGProvider()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": True,
        "resultado": {
            "Nome": "Posto Exemplo",
            "Combustiveis": [
                {"TipoCombustivel": "Gasóleo simples", "Preco": "1,609 €/litro", "DataAtualizacao": "2026-09-20"},
                {"TipoCombustivel": "Gasolina simples 95", "Preco": "1,749 €/litro", "DataAtualizacao": "2026-09-21"},
                {"TipoCombustivel": "GPL Auto", "Preco": "0,849 €/litro", "DataAtualizacao": "2026-09-21"}
            ]
        }
    }

    with patch.object(provider.session, "get", return_value=mock_response):
        info = provider.get_prices("12345")
        assert info.lpg_price == 0.849
        assert info.petrol_price == 1.749
        assert info.source == "dgeg"
        assert info.is_estimated is False


def test_cached_provider_fallback(tmp_path):
    """Verify that when DGEG fails/timeouts, CachedFuelProvider falls back to cache/history."""
    db_file = tmp_path / "test_fallback.db"
    init_db(db_file)

    cached_provider = CachedFuelProvider(db_path=db_file)

    # Pick an existing seeded station id
    with get_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM fuel_stations LIMIT 1")
        station_id = cursor.fetchone()["id"]

    # Save a price to cache first
    cached_provider._save_to_cache(
        station_id=station_id,
        lpg_price=0.869,
        petrol_price=1.799,
        updated_at="2026-09-18 15:00",
        source="cache"
    )

    # Mock DGEG failure
    with patch.object(cached_provider.dgeg, "get_prices", side_effect=Exception("Timeout simulado")):
        res = cached_provider.get_prices_for_station(station_db_id=station_id, external_id="99999")
        assert res.lpg_price == 0.869
        assert res.source == "cache"
        assert res.is_estimated is True
        assert "cache" in res.message.lower()
