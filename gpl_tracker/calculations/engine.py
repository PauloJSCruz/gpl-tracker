"""Financial calculations and ROI engine for GPL conversions."""
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
from gpl_tracker.models.schemas import BreakEvenProjection, FinancialSummary


def calculate_refueling(
    distance_km: float,
    amount_paid: float,
    lpg_price: float,
    petrol_price: float,
    lpg_increase_percent: float
) -> Dict[str, float]:
    """Calculate all financial metrics for a single refueling.

    Formulas:
        litros_gpl = valor_pago / preco_gpl
        consumo_gpl = (litros_gpl / km_percorridos) * 100
        consumo_gasolina = consumo_gpl / (1 + aumento_gpl / 100)
        custo_gasolina = (km_percorridos / 100) * consumo_gasolina * preco_gasolina
        poupanca = custo_gasolina - valor_pago

    Args:
        distance_km: Distance driven in kilometers (must be > 0)
        amount_paid: Total amount paid in EUR (must be > 0)
        lpg_price: LPG price in EUR/L (must be > 0)
        petrol_price: Petrol 95 price in EUR/L (must be > 0)
        lpg_increase_percent: Configured LPG consumption increase % (e.g. 20.0 for 20%)

    Returns:
        Dictionary containing lpg_liters, lpg_consumption, equivalent_petrol_consumption,
        estimated_petrol_cost, and savings.
    """
    if distance_km <= 0:
        raise ValueError("A distância percorrida deve ser maior que 0.")
    if amount_paid <= 0:
        raise ValueError("O valor pago deve ser maior que 0.")
    if lpg_price <= 0:
        raise ValueError("O preço do GPL deve ser maior que 0.")
    if petrol_price <= 0:
        raise ValueError("O preço da gasolina deve ser maior que 0.")
    if lpg_increase_percent < 0:
        raise ValueError("O aumento de consumo GPL não pode ser negativo.")

    # 1. Litros de GPL abastecidos
    lpg_liters = amount_paid / lpg_price

    # 2. Consumo GPL em L/100 km
    lpg_consumption = (lpg_liters / distance_km) * 100.0

    # 3. Consumo equivalente a gasolina em L/100 km
    # Regra obrigatória: consumo_gasolina = consumo_gpl / (1 + aumento_gpl / 100)
    increase_factor = 1.0 + (lpg_increase_percent / 100.0)
    equivalent_petrol_consumption = lpg_consumption / increase_factor

    # 4. Custo estimado utilizando gasolina (€)
    estimated_petrol_cost = (distance_km / 100.0) * equivalent_petrol_consumption * petrol_price

    # 5. Poupança do período (€)
    savings = estimated_petrol_cost - amount_paid

    return {
        "lpg_liters": round(lpg_liters, 3),
        "lpg_consumption": round(lpg_consumption, 2),
        "equivalent_petrol_consumption": round(equivalent_petrol_consumption, 2),
        "estimated_petrol_cost": round(estimated_petrol_cost, 2),
        "savings": round(savings, 2),
        # Raw unrounded values for high-precision accumulations if needed:
        "_raw_lpg_liters": lpg_liters,
        "_raw_lpg_consumption": lpg_consumption,
        "_raw_equivalent_petrol_consumption": equivalent_petrol_consumption,
        "_raw_estimated_petrol_cost": estimated_petrol_cost,
        "_raw_savings": savings,
    }


def parse_refueling_date(date_str: str) -> Optional[datetime]:
    """Parse date strings in YYYY-MM-DD or ISO 8601 format."""
    if not date_str:
        return None
    cleaned = date_str.replace("Z", "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def calculate_break_even(
    remaining_amount: float,
    avg_savings_per_km: float,
    refuelings: List[Dict[str, Any]],
    conversion_date_str: Optional[str] = None
) -> BreakEvenProjection:
    """Calculate break-even projections (remaining km and remaining months).

    Requirements:
    - If investment is already recovered: return status='recovered'.
    - For remaining km: remaining_amount / avg_savings_per_km.
    - For remaining months: use observed real km/month from refuelings history.
    - If not enough historical data (< 2 refuelings or time span < 7 days):
      return status='insufficient_data', with message "Dados insuficientes para estimar o break-even."
    """
    if remaining_amount <= 0.001:
        return BreakEvenProjection(
            status="recovered",
            message="Investimento recuperado!",
            remaining_km=0.0,
            remaining_months=0.0,
            avg_km_per_month=None,
            avg_savings_per_km=round(avg_savings_per_km, 4) if avg_savings_per_km > 0 else 0.0
        )

    # If savings per km is zero or negative (impossible to break even at this rate)
    if avg_savings_per_km <= 0:
        return BreakEvenProjection(
            status="insufficient_data",
            message="Dados insuficientes para estimar o break-even (poupança média por km nula ou negativa).",
            remaining_km=None,
            remaining_months=None,
            avg_km_per_month=None,
            avg_savings_per_km=round(avg_savings_per_km, 4) if avg_savings_per_km else 0.0
        )

    remaining_km = remaining_amount / avg_savings_per_km

    # Calculate real monthly km from recorded history
    if len(refuelings) < 2:
        return BreakEvenProjection(
            status="insufficient_data",
            message="Dados insuficientes para estimar o break-even. Registe pelo menos 2 abastecimentos.",
            remaining_km=round(remaining_km, 1),
            remaining_months=None,
            avg_km_per_month=None,
            avg_savings_per_km=round(avg_savings_per_km, 4)
        )

    # Sort refuelings by date
    parsed_dates = []
    for r in refuelings:
        d = parse_refueling_date(r.get("date", ""))
        if d:
            parsed_dates.append((d, float(r.get("distance_km", 0.0))))

    parsed_dates.sort(key=lambda x: x[0])

    if len(parsed_dates) < 2:
        return BreakEvenProjection(
            status="insufficient_data",
            message="Dados insuficientes para estimar o break-even.",
            remaining_km=round(remaining_km, 1),
            remaining_months=None,
            avg_km_per_month=None,
            avg_savings_per_km=round(avg_savings_per_km, 4)
        )

    earliest_date = parsed_dates[0][0]
    latest_date = parsed_dates[-1][0]
    days_span = (latest_date - earliest_date).total_seconds() / 86400.0

    # If all refuelings were entered on the exact same day or span < 7 days
    if days_span < 7.0:
        return BreakEvenProjection(
            status="insufficient_data",
            message="Dados insuficientes para estimar o break-even. Intervalo temporal entre abastecimentos inferior a 7 dias.",
            remaining_km=round(remaining_km, 1),
            remaining_months=None,
            avg_km_per_month=None,
            avg_savings_per_km=round(avg_savings_per_km, 4)
        )

    # Total distance driven across the observed period
    total_km = sum(item[1] for item in parsed_dates)
    months_span = days_span / 30.4375  # Average days in Gregorian month
    avg_km_per_month = total_km / months_span

    if avg_km_per_month <= 0:
        return BreakEvenProjection(
            status="insufficient_data",
            message="Dados insuficientes para estimar o break-even.",
            remaining_km=round(remaining_km, 1),
            remaining_months=None,
            avg_km_per_month=None,
            avg_savings_per_km=round(avg_savings_per_km, 4)
        )

    remaining_months = remaining_km / avg_km_per_month

    return BreakEvenProjection(
        status="recovering",
        message=f"Faltam aproximadamente {round(remaining_km):,} km ({round(remaining_months, 1)} meses).".replace(",", "."),
        remaining_km=round(remaining_km, 1),
        remaining_months=round(remaining_months, 1),
        avg_km_per_month=round(avg_km_per_month, 1),
        avg_savings_per_km=round(avg_savings_per_km, 4)
    )


def calculate_financial_summary(
    conversion_cost: float,
    refuelings: List[Dict[str, Any]],
    conversion_date_str: Optional[str] = None
) -> FinancialSummary:
    """Compute overall financial accumulation, ROI percentage, and Break-Even projection."""
    total_refuelings = len(refuelings)
    total_distance_km = 0.0
    total_lpg_liters = 0.0
    total_lpg_spent = 0.0
    total_petrol_hypothetical_cost = 0.0
    total_savings = 0.0

    for r in refuelings:
        dist = float(r.get("distance_km", 0.0))
        paid = float(r.get("amount_paid", 0.0))
        liters = float(r.get("lpg_liters", 0.0))
        petrol_cost = float(r.get("estimated_petrol_cost", 0.0))
        sav = float(r.get("savings", 0.0))

        total_distance_km += dist
        total_lpg_spent += paid
        total_lpg_liters += liters
        total_petrol_hypothetical_cost += petrol_cost
        total_savings += sav

    # Averages
    avg_savings_per_km = (total_savings / total_distance_km) if total_distance_km > 0 else 0.0
    avg_savings_per_100km = avg_savings_per_km * 100.0

    avg_lpg_consumption = (total_lpg_liters / total_distance_km * 100.0) if total_distance_km > 0 else 0.0
    # Equivalent petrol consumption average
    avg_petrol_consumption = 0.0
    if refuelings and total_distance_km > 0:
        total_equiv_liters = sum(
            float(r.get("distance_km", 0.0)) * float(r.get("equivalent_petrol_consumption", 0.0)) / 100.0
            for r in refuelings
        )
        avg_petrol_consumption = (total_equiv_liters / total_distance_km) * 100.0

    # ROI
    recovered_percent = (total_savings / conversion_cost * 100.0) if conversion_cost > 0 else 100.0
    remaining_amount = max(0.0, conversion_cost - total_savings)
    is_recovered = total_savings >= conversion_cost
    net_profit = max(0.0, total_savings - conversion_cost)

    break_even = calculate_break_even(
        remaining_amount=remaining_amount,
        avg_savings_per_km=avg_savings_per_km,
        refuelings=refuelings,
        conversion_date_str=conversion_date_str
    )

    return FinancialSummary(
        total_refuelings=total_refuelings,
        total_distance_km=round(total_distance_km, 1),
        total_lpg_liters=round(total_lpg_liters, 2),
        total_lpg_spent=round(total_lpg_spent, 2),
        total_petrol_hypothetical_cost=round(total_petrol_hypothetical_cost, 2),
        total_savings=round(total_savings, 2),
        avg_savings_per_km=round(avg_savings_per_km, 4),
        avg_savings_per_100km=round(avg_savings_per_100km, 2),
        avg_lpg_consumption=round(avg_lpg_consumption, 2),
        avg_petrol_consumption=round(avg_petrol_consumption, 2),
        conversion_cost=round(conversion_cost, 2),
        recovered_percent=round(recovered_percent, 1),
        remaining_amount=round(remaining_amount, 2),
        is_recovered=is_recovered,
        net_profit=round(net_profit, 2),
        break_even=break_even
    )

