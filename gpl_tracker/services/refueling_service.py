"""Service for refueling records, financial accumulation, and history."""
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime

from gpl_tracker.config import DB_PATH
from gpl_tracker.models.database import get_connection
from gpl_tracker.models.schemas import (
    RefuelingCreate,
    RefuelingUpdate,
    RefuelingOut,
    FinancialSummary
)
from gpl_tracker.calculations.engine import calculate_refueling, calculate_financial_summary
from gpl_tracker.services.vehicle_service import VehicleService
from gpl_tracker.services.station_service import StationService


class RefuelingService:
    """Manages refueling records, history calculations, and dashboard data."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.vehicle_service = VehicleService(db_path=db_path)
        self.station_service = StationService(db_path=db_path)

    def add_refueling(self, data: RefuelingCreate, vehicle_id: int = 1) -> RefuelingOut:
        """Create a new refueling record with automatic metric calculations and odometer tracking."""
        vehicle = self.vehicle_service.get_vehicle(vehicle_id)
        if not vehicle:
            raise ValueError(f"Veículo {vehicle_id} não encontrado.")

        # If station_id is not given but station_name is provided, find or create custom station
        station_id = data.station_id
        if not station_id and data.station_name:
            st = self.station_service.search_stations(data.station_name)
            if st:
                station_id = st[0].id
            else:
                from gpl_tracker.models.schemas import StationCreate
                new_st = self.station_service.add_custom_station(StationCreate(
                    name=data.station_name,
                    brand="Independente",
                    provider="manual"
                ))
                station_id = new_st.id

        # Calculate metrics using engine
        metrics = calculate_refueling(
            distance_km=data.distance_km,
            amount_paid=data.amount_paid,
            lpg_price=data.lpg_price,
            petrol_price=data.petrol_price,
            lpg_increase_percent=vehicle.lpg_consumption_increase
        )

        # Automatic odometer estimation if omitted
        odometer = data.odometer
        if odometer is None or odometer <= 0:
            last_odometer = self._get_latest_odometer(vehicle_id=vehicle_id)
            if last_odometer is not None:
                odometer = int(last_odometer + data.distance_km)
            else:
                odometer = int(vehicle.conversion_odometer + data.distance_km)

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO refuelings (
                    vehicle_id, station_id, date, odometer, distance_km,
                    lpg_price, petrol_price, amount_paid, lpg_liters,
                    lpg_consumption, equivalent_petrol_consumption,
                    estimated_petrol_cost, savings, data_source, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                vehicle_id,
                station_id,
                data.date,
                odometer,
                data.distance_km,
                data.lpg_price,
                data.petrol_price,
                data.amount_paid,
                metrics["lpg_liters"],
                metrics["lpg_consumption"],
                metrics["equivalent_petrol_consumption"],
                metrics["estimated_petrol_cost"],
                metrics["savings"],
                data.data_source,
                data.notes or ""
            ))
            new_id = cursor.lastrowid
            conn.commit()

        # Update station usage statistics and price cache
        if station_id:
            self.station_service.record_usage(station_id)
            # Update price cache with this confirmed refueling price
            self.station_service.price_provider._save_to_cache(
                station_id=station_id,
                lpg_price=data.lpg_price,
                petrol_price=data.petrol_price,
                updated_at=data.date,
                source=data.data_source
            )

        return self.get_refueling(new_id)

    def list_refuelings(self, vehicle_id: int = 1) -> List[RefuelingOut]:
        """List all refuelings with cumulative savings calculated chronologically."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT r.*, s.name as station_name, s.brand as station_brand
                FROM refuelings r
                LEFT JOIN fuel_stations s ON r.station_id = s.id
                WHERE r.vehicle_id = ?
                ORDER BY r.date ASC, r.id ASC
            """, (vehicle_id,))
            rows = cursor.fetchall()

        # Compute running cumulative savings chronologically
        cum_savings = 0.0
        results = []
        for r in rows:
            sav = float(r["savings"])
            cum_savings += sav
            results.append(RefuelingOut(
                id=r["id"],
                vehicle_id=r["vehicle_id"],
                station_id=r["station_id"],
                station_name=r["station_name"] or "Posto Desconhecido",
                station_brand=r["station_brand"] or "",
                date=r["date"],
                odometer=r["odometer"],
                distance_km=float(r["distance_km"]),
                lpg_price=float(r["lpg_price"]),
                petrol_price=float(r["petrol_price"]),
                amount_paid=float(r["amount_paid"]),
                lpg_liters=float(r["lpg_liters"]),
                lpg_consumption=float(r["lpg_consumption"]),
                equivalent_petrol_consumption=float(r["equivalent_petrol_consumption"]),
                estimated_petrol_cost=float(r["estimated_petrol_cost"]),
                savings=round(sav, 2),
                cumulative_savings=round(cum_savings, 2),
                data_source=r["data_source"],
                notes=r["notes"] or ""
            ))

        # Return latest first for the UI view
        results.reverse()
        return results

    def get_refueling(self, refueling_id: int) -> Optional[RefuelingOut]:
        """Retrieve a specific refueling record by ID."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT r.*, s.name as station_name, s.brand as station_brand
                FROM refuelings r
                LEFT JOIN fuel_stations s ON r.station_id = s.id
                WHERE r.id = ?
            """, (refueling_id,))
            r = cursor.fetchone()
            if not r:
                return None

            # Calculate cumulative savings up to this record
            cursor.execute("""
                SELECT SUM(savings) as cum
                FROM refuelings
                WHERE vehicle_id = ? AND (date < ? OR (date = ? AND id <= ?))
            """, (r["vehicle_id"], r["date"], r["date"], r["id"]))
            cum_row = cursor.fetchone()
            cum_sav = float(cum_row["cum"]) if cum_row and cum_row["cum"] is not None else float(r["savings"])

            return RefuelingOut(
                id=r["id"],
                vehicle_id=r["vehicle_id"],
                station_id=r["station_id"],
                station_name=r["station_name"] or "Posto Desconhecido",
                station_brand=r["station_brand"] or "",
                date=r["date"],
                odometer=r["odometer"],
                distance_km=float(r["distance_km"]),
                lpg_price=float(r["lpg_price"]),
                petrol_price=float(r["petrol_price"]),
                amount_paid=float(r["amount_paid"]),
                lpg_liters=float(r["lpg_liters"]),
                lpg_consumption=float(r["lpg_consumption"]),
                equivalent_petrol_consumption=float(r["equivalent_petrol_consumption"]),
                estimated_petrol_cost=float(r["estimated_petrol_cost"]),
                savings=round(float(r["savings"]), 2),
                cumulative_savings=round(cum_sav, 2),
                data_source=r["data_source"],
                notes=r["notes"] or ""
            )

    def update_refueling(self, refueling_id: int, data: RefuelingUpdate) -> Optional[RefuelingOut]:
        """Update an existing refueling record and recalculate metrics."""
        current = self.get_refueling(refueling_id)
        if not current:
            return None

        vehicle = self.vehicle_service.get_vehicle(current.vehicle_id)
        if not vehicle:
            return None

        new_dist = data.distance_km if data.distance_km is not None else current.distance_km
        new_paid = data.amount_paid if data.amount_paid is not None else current.amount_paid
        new_lpg = data.lpg_price if data.lpg_price is not None else current.lpg_price
        new_petrol = data.petrol_price if data.petrol_price is not None else current.petrol_price
        new_date = data.date if data.date is not None else current.date
        new_station_id = data.station_id if data.station_id is not None else current.station_id
        new_odometer = data.odometer if data.odometer is not None else current.odometer
        new_source = data.data_source if data.data_source is not None else current.data_source
        new_notes = data.notes if data.notes is not None else current.notes

        metrics = calculate_refueling(
            distance_km=new_dist,
            amount_paid=new_paid,
            lpg_price=new_lpg,
            petrol_price=new_petrol,
            lpg_increase_percent=vehicle.lpg_consumption_increase
        )

        with get_connection(self.db_path) as conn:
            conn.execute("""
                UPDATE refuelings SET
                    station_id = ?,
                    date = ?,
                    odometer = ?,
                    distance_km = ?,
                    lpg_price = ?,
                    petrol_price = ?,
                    amount_paid = ?,
                    lpg_liters = ?,
                    lpg_consumption = ?,
                    equivalent_petrol_consumption = ?,
                    estimated_petrol_cost = ?,
                    savings = ?,
                    data_source = ?,
                    notes = ?
                WHERE id = ?
            """, (
                new_station_id,
                new_date,
                new_odometer,
                new_dist,
                new_lpg,
                new_petrol,
                new_paid,
                metrics["lpg_liters"],
                metrics["lpg_consumption"],
                metrics["equivalent_petrol_consumption"],
                metrics["estimated_petrol_cost"],
                metrics["savings"],
                new_source,
                new_notes,
                refueling_id
            ))
            conn.commit()

        return self.get_refueling(refueling_id)

    def delete_refueling(self, refueling_id: int) -> bool:
        """Delete a refueling record."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM refuelings WHERE id = ?", (refueling_id,))
            conn.commit()
            return cursor.rowcount > 0

    def duplicate_refueling(self, refueling_id: int) -> Optional[RefuelingOut]:
        """Duplicate an existing refueling record with today's date for fast entry."""
        current = self.get_refueling(refueling_id)
        if not current:
            return None

        today_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        create_data = RefuelingCreate(
            station_id=current.station_id,
            date=today_str,
            distance_km=current.distance_km,
            amount_paid=current.amount_paid,
            lpg_price=current.lpg_price,
            petrol_price=current.petrol_price,
            data_source=current.data_source,
            notes=f"Cópia do abastecimento #{current.id}"
        )
        return self.add_refueling(create_data, vehicle_id=current.vehicle_id)

    def get_last_refueling(self, vehicle_id: int = 1) -> Optional[RefuelingOut]:
        """Retrieve the latest refueling record (used by '+ Abasteci novamente')."""
        items = self.list_refuelings(vehicle_id)
        return items[0] if items else None

    def get_dashboard_summary(self, vehicle_id: int = 1) -> FinancialSummary:
        """Calculate complete financial summary and break-even projections."""
        vehicle = self.vehicle_service.get_vehicle(vehicle_id)
        conversion_cost = vehicle.conversion_cost if vehicle else 1500.0
        conversion_date = vehicle.conversion_date if vehicle else ""

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT distance_km, amount_paid, lpg_liters, estimated_petrol_cost,
                       savings, date, equivalent_petrol_consumption
                FROM refuelings
                WHERE vehicle_id = ?
                ORDER BY date ASC, id ASC
            """, (vehicle_id,))
            rows = cursor.fetchall()
            dict_rows = [dict(r) for r in rows]

        return calculate_financial_summary(
            conversion_cost=conversion_cost,
            refuelings=dict_rows,
            conversion_date_str=conversion_date
        )

    def _get_latest_odometer(self, vehicle_id: int) -> Optional[int]:
        """Get the highest recorded odometer reading."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT odometer FROM refuelings
                WHERE vehicle_id = ? AND odometer IS NOT NULL
                ORDER BY odometer DESC, date DESC LIMIT 1
            """, (vehicle_id,))
            row = cursor.fetchone()
            if row and row["odometer"]:
                return int(row["odometer"])
        return None

