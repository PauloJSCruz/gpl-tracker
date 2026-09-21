"""Tests for the financial calculation engine."""
import pytest
from gpl_tracker.calculations.engine import (
    calculate_refueling,
    calculate_break_even,
    calculate_financial_summary
)


def test_user_validation_example():
    """Verify the exact example requested by the user:

    Km: 450
    Preço GPL: 0.85 €/L
    Preço gasolina: 1.75 €/L
    Valor pago: 34 €
    Aumento GPL: 20%

    Expected results:
    Litros GPL = 40 L
    Consumo GPL ≈ 8.89 L/100 km
    Consumo gasolina equivalente ≈ 7.41 L/100 km (calculated as 8.8888... / 1.20)
    Custo equivalente gasolina ≈ 58.33 €
    Poupança ≈ 24.33 €
    """
    res = calculate_refueling(
        distance_km=450.0,
        amount_paid=34.0,
        lpg_price=0.85,
        petrol_price=1.75,
        lpg_increase_percent=20.0
    )

    assert res["lpg_liters"] == 40.0
    assert pytest.approx(res["lpg_consumption"], 0.01) == 8.89
    assert pytest.approx(res["equivalent_petrol_consumption"], 0.01) == 7.41
    assert pytest.approx(res["estimated_petrol_cost"], 0.02) == 58.33
    assert pytest.approx(res["savings"], 0.02) == 24.33


def test_custom_consumption_increase():
    """Ensure consumption increase is strictly customizable (e.g. 15% and 25%)."""
    # 15% increase
    res15 = calculate_refueling(
        distance_km=500.0,
        amount_paid=40.0,
        lpg_price=0.80,
        petrol_price=1.80,
        lpg_increase_percent=15.0
    )
    # 40 / 0.80 = 50 L
    # 50 / 500 * 100 = 10.0 L/100 km
    # Equiv petrol: 10.0 / 1.15 = 8.69565...
    # Cost petrol: 5.0 * 8.69565 * 1.80 = 78.26 €
    # Savings: 78.26 - 40.00 = 38.26 €
    assert res15["lpg_liters"] == 50.0
    assert res15["lpg_consumption"] == 10.0
    assert pytest.approx(res15["equivalent_petrol_consumption"], 0.01) == 8.70
    assert pytest.approx(res15["estimated_petrol_cost"], 0.02) == 78.26
    assert pytest.approx(res15["savings"], 0.02) == 38.26


def test_roi_and_cumulative_savings():
    """Verify conversion ROI and progress calculations:

    Custo da conversão: 1.800 €
    Poupança acumulada: 1.125 €
    Recuperado: 62.5%
    Falta recuperar: 675 €
    """
    refuelings = [
        {"distance_km": 500, "amount_paid": 40, "lpg_liters": 45, "estimated_petrol_cost": 90, "savings": 50, "date": "2026-01-01"},
        {"distance_km": 500, "amount_paid": 40, "lpg_liters": 45, "estimated_petrol_cost": 90, "savings": 50, "date": "2026-01-15"},
    ]
    # Let's mock a list of refuelings that total exactly 1125 € in savings
    refuelings_1125 = [
        {"distance_km": 10000, "amount_paid": 800, "lpg_liters": 900, "estimated_petrol_cost": 1925, "savings": 1125, "date": "2026-01-01"},
        {"distance_km": 5000, "amount_paid": 400, "lpg_liters": 450, "estimated_petrol_cost": 400, "savings": 0, "date": "2026-03-01"}
    ]

    summary = calculate_financial_summary(
        conversion_cost=1800.0,
        refuelings=refuelings_1125
    )

    assert summary.conversion_cost == 1800.0
    assert summary.total_savings == 1125.0
    assert summary.recovered_percent == 62.5
    assert summary.remaining_amount == 675.0
    assert summary.is_recovered is False
    assert summary.net_profit == 0.0


def test_break_even_recovered_status():
    """When savings surpass conversion cost, it should be marked as recovered."""
    refuelings = [
        {"distance_km": 20000, "amount_paid": 1200, "lpg_liters": 1400, "estimated_petrol_cost": 3000, "savings": 1800, "date": "2026-01-01"},
        {"distance_km": 5000, "amount_paid": 300, "lpg_liters": 350, "estimated_petrol_cost": 650, "savings": 350, "date": "2026-06-01"}
    ]

    summary = calculate_financial_summary(
        conversion_cost=1500.0,
        refuelings=refuelings
    )

    assert summary.is_recovered is True
    assert summary.total_savings == 2150.0
    assert summary.recovered_percent == pytest.approx(143.3, 0.1)
    assert summary.remaining_amount == 0.0
    assert summary.net_profit == 650.0
    assert summary.break_even.status == "recovered"


def test_insufficient_data_for_time_projection():
    """Ensure we do not invent projections with < 2 refuelings or time span < 7 days."""
    single_refueling = [
        {"distance_km": 450, "amount_paid": 34, "lpg_liters": 40, "estimated_petrol_cost": 58.33, "savings": 24.33, "date": "2026-09-21"}
    ]
    summary = calculate_financial_summary(
        conversion_cost=1500.0,
        refuelings=single_refueling
    )

    # Km remaining can still be estimated from observed savings/km
    assert summary.break_even.remaining_km is not None
    # But time projection must return insufficient data
    assert summary.break_even.status == "insufficient_data"
    assert summary.break_even.remaining_months is None
    assert "Dados insuficientes" in summary.break_even.message


def test_invalid_inputs():
    """Test validation errors for invalid numbers."""
    with pytest.raises(ValueError):
        calculate_refueling(distance_km=0, amount_paid=30, lpg_price=0.85, petrol_price=1.75, lpg_increase_percent=20)
    with pytest.raises(ValueError):
        calculate_refueling(distance_km=400, amount_paid=-10, lpg_price=0.85, petrol_price=1.75, lpg_increase_percent=20)

