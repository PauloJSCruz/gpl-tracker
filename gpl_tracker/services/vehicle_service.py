"""Service for vehicle profile and settings management."""
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime

from gpl_tracker.config import DB_PATH
from gpl_tracker.models.database import get_connection
from gpl_tracker.models.schemas import VehicleOut, VehicleCreate


class VehicleService:
    """Manages vehicle configuration and conversion parameters."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    def get_vehicle(self, vehicle_id: int = 1) -> Optional[VehicleOut]:
        """Fetch vehicle details by ID."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return VehicleOut(
                id=row["id"],
                make=row["make"],
                model=row["model"],
                engine=row["engine"],
                conversion_cost=float(row["conversion_cost"]),
                conversion_date=row["conversion_date"],
                conversion_odometer=int(row["conversion_odometer"]),
                petrol_consumption=float(row["petrol_consumption"]),
                lpg_consumption_increase=float(row["lpg_consumption_increase"]),
                created_at=row["created_at"]
            )

    def update_vehicle(self, vehicle_id: int, data: VehicleCreate) -> Optional[VehicleOut]:
        """Update vehicle parameters."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE vehicles SET
                    make = ?,
                    model = ?,
                    engine = ?,
                    conversion_cost = ?,
                    conversion_date = ?,
                    conversion_odometer = ?,
                    petrol_consumption = ?,
                    lpg_consumption_increase = ?
                WHERE id = ?
            """, (
                data.make,
                data.model,
                data.engine,
                data.conversion_cost,
                data.conversion_date,
                data.conversion_odometer,
                data.petrol_consumption,
                data.lpg_consumption_increase,
                vehicle_id
            ))
            conn.commit()
        return self.get_vehicle(vehicle_id)

