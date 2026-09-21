"""Service for exporting refueling history and financial reports to CSV and Excel."""
import io
import pandas as pd
from typing import Tuple
from pathlib import Path

from gpl_tracker.services.refueling_service import RefuelingService
from gpl_tracker.services.vehicle_service import VehicleService
from gpl_tracker.config import DB_PATH


class ExportService:
    """Exports financial reports and history records."""

    def __init__(self, db_path: Path = DB_PATH):
        self.refueling_service = RefuelingService(db_path=db_path)
        self.vehicle_service = VehicleService(db_path=db_path)

    def _get_export_dataframe(self, vehicle_id: int = 1) -> pd.DataFrame:
        """Create a cleanly formatted pandas DataFrame of the refuelings history."""
        refuelings = self.refueling_service.list_refuelings(vehicle_id)
        # Reverse to chronological order for export
        chronological = list(reversed(refuelings))

        data = []
        for r in chronological:
            data.append({
                "ID": r.id,
                "Data": r.date,
                "Posto": r.station_name,
                "Marca": r.station_brand,
                "Km Percorridos": r.distance_km,
                "Odómetro (km)": r.odometer,
                "Preço GPL (€/L)": r.lpg_price,
                "Preço Gasolina (€/L)": r.petrol_price,
                "Valor Pago (€)": r.amount_paid,
                "Litros GPL": r.lpg_liters,
                "Consumo GPL (L/100km)": r.lpg_consumption,
                "Consumo Gasolina Eq. (L/100km)": r.equivalent_petrol_consumption,
                "Custo Gasolina Estimado (€)": r.estimated_petrol_cost,
                "Poupança (€)": r.savings,
                "Poupança Acumulada (€)": r.cumulative_savings,
                "Origem dos Dados": r.data_source,
                "Notas": r.notes or ""
            })

        return pd.DataFrame(data)

    def export_csv(self, vehicle_id: int = 1) -> bytes:
        """Export history to CSV encoded in UTF-8 with BOM for Portuguese character support in Excel."""
        df = self._get_export_dataframe(vehicle_id)
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False, sep=";", decimal=",", encoding="utf-8-sig")
        return csv_buffer.getvalue().encode("utf-8-sig")

    def export_excel(self, vehicle_id: int = 1) -> bytes:
        """Export history and financial summary to Excel (.xlsx) with two sheets."""
        df_history = self._get_export_dataframe(vehicle_id)
        summary = self.refueling_service.get_dashboard_summary(vehicle_id)
        vehicle = self.vehicle_service.get_vehicle(vehicle_id)

        df_summary = pd.DataFrame([
            {"Indicador": "Veículo", "Valor": f"{vehicle.make} {vehicle.model} {vehicle.engine}".strip() if vehicle else ""},
            {"Indicador": "Custo da Conversão", "Valor": f"{summary.conversion_cost:.2f} €"},
            {"Indicador": "Poupança Acumulada", "Valor": f"{summary.total_savings:.2f} €"},
            {"Indicador": "Percentagem Recuperada", "Valor": f"{summary.recovered_percent:.1f} %"},
            {"Indicador": "Falta Recuperar", "Valor": f"{summary.remaining_amount:.2f} €"},
            {"Indicador": "Lucro Líquido", "Valor": f"{summary.net_profit:.2f} €"},
            {"Indicador": "Total Km Percorridos", "Valor": f"{summary.total_distance_km:.1f} km"},
            {"Indicador": "Total Litros GPL", "Valor": f"{summary.total_lpg_liters:.2f} L"},
            {"Indicador": "Total Gasto em GPL", "Valor": f"{summary.total_lpg_spent:.2f} €"},
            {"Indicador": "Custo Hipotético Gasolina", "Valor": f"{summary.total_petrol_hypothetical_cost:.2f} €"},
            {"Indicador": "Poupança Média por Km", "Valor": f"{summary.avg_savings_per_km:.4f} €/km"},
            {"Indicador": "Poupança Média por 100 Km", "Valor": f"{summary.avg_savings_per_100km:.2f} €/100km"},
            {"Indicador": "Consumo Médio GPL", "Valor": f"{summary.avg_lpg_consumption:.2f} L/100km"},
            {"Indicador": "Consumo Médio Gasolina Eq.", "Valor": f"{summary.avg_petrol_consumption:.2f} L/100km"},
            {"Indicador": "Km Restantes para Break-even", "Valor": f"{summary.break_even.remaining_km:.1f} km" if summary.break_even.remaining_km is not None else "N/A"},
            {"Indicador": "Meses Restantes para Break-even", "Valor": f"{summary.break_even.remaining_months:.1f} meses" if summary.break_even.remaining_months is not None else "N/A"},
            {"Indicador": "Estado Break-even", "Valor": summary.break_even.message},
        ])

        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            df_summary.to_excel(writer, sheet_name="Resumo Financeiro", index=False)
            df_history.to_excel(writer, sheet_name="Histórico Abastecimentos", index=False)

        return excel_buffer.getvalue()

