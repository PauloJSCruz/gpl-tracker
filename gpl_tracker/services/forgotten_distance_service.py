"""Service for managing forgotten distance (late odometer reset compensation)."""
from typing import List, Optional
from pathlib import Path
from datetime import datetime

from gpl_tracker.config import DB_PATH
from gpl_tracker.models.database import get_connection
from gpl_tracker.models.schemas import (
    ForgottenDistanceCreate,
    ForgottenDistanceUpdate,
    ForgottenDistanceOut,
    ForgottenDistanceSummary
)


class ForgottenDistanceService:
    """Manages forgotten distance records and their application to refuelings."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    def add_forgotten_distance(
        self,
        data: ForgottenDistanceCreate,
        vehicle_id: int = 1
    ) -> ForgottenDistanceOut:
        """Register distance traveled before a late odometer reset."""
        if data.distance_km <= 0:
            raise ValueError("Os quilómetros esquecidos devem ser superiores a 0.")

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO forgotten_distance_logs (
                    vehicle_id, distance_km, notes, created_at, status, applied_refueling_id
                ) VALUES (?, ?, ?, ?, 'pending', NULL)
            """, (vehicle_id, round(data.distance_km, 1), data.notes or "", now_str))
            new_id = cursor.lastrowid
            conn.commit()

        return self.get_record(new_id)

    def get_record(self, record_id: int) -> Optional[ForgottenDistanceOut]:
        """Fetch a single forgotten distance record."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, vehicle_id, distance_km, notes, created_at, status, applied_refueling_id
                FROM forgotten_distance_logs
                WHERE id = ?
            """, (record_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ForgottenDistanceOut(
                id=row["id"],
                vehicle_id=row["vehicle_id"],
                distance_km=float(row["distance_km"]),
                notes=row["notes"] or "",
                created_at=row["created_at"],
                status=row["status"],
                applied_refueling_id=row["applied_refueling_id"]
            )

    def get_pending_summary(self, vehicle_id: int = 1) -> ForgottenDistanceSummary:
        """Get summary of all pending forgotten distance records for a vehicle."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, vehicle_id, distance_km, notes, created_at, status, applied_refueling_id
                FROM forgotten_distance_logs
                WHERE vehicle_id = ? AND status = 'pending'
                ORDER BY created_at ASC, id ASC
            """, (vehicle_id,))
            rows = cursor.fetchall()

        items = [
            ForgottenDistanceOut(
                id=r["id"],
                vehicle_id=r["vehicle_id"],
                distance_km=float(r["distance_km"]),
                notes=r["notes"] or "",
                created_at=r["created_at"],
                status=r["status"],
                applied_refueling_id=r["applied_refueling_id"]
            )
            for r in rows
        ]
        total_km = sum(item.distance_km for item in items)
        return ForgottenDistanceSummary(
            pending_total_km=round(total_km, 1),
            items=items
        )

    def update_record(
        self,
        record_id: int,
        data: ForgottenDistanceUpdate
    ) -> Optional[ForgottenDistanceOut]:
        """Update a pending forgotten distance record."""
        rec = self.get_record(record_id)
        if not rec:
            return None
        if rec.status != "pending":
            raise ValueError("Não é possível editar quilómetros que já foram aplicados a um abastecimento.")

        new_km = data.distance_km if data.distance_km is not None else rec.distance_km
        if new_km <= 0:
            raise ValueError("A distância deve ser superior a 0.")
        new_notes = data.notes if data.notes is not None else rec.notes

        with get_connection(self.db_path) as conn:
            conn.execute("""
                UPDATE forgotten_distance_logs
                SET distance_km = ?, notes = ?
                WHERE id = ?
            """, (round(new_km, 1), new_notes, record_id))
            conn.commit()

        return self.get_record(record_id)

    def delete_record(self, record_id: int) -> bool:
        """Delete a pending forgotten distance record."""
        rec = self.get_record(record_id)
        if not rec:
            return False
        if rec.status != "pending":
            raise ValueError("Não é possível eliminar quilómetros que já foram aplicados a um abastecimento.")

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM forgotten_distance_logs WHERE id = ?", (record_id,))
            conn.commit()
            return cursor.rowcount > 0

    def apply_pending_to_refueling(
        self,
        refueling_id: int,
        vehicle_id: int = 1,
        custom_km: Optional[float] = None,
        apply_pending: bool = True
    ) -> float:
        """Mark pending records as applied to this refueling, or create an immediate applied entry.

        Returns total forgotten km applied.
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Case 1: Custom inline forgotten km entered directly on refueling form
        if custom_km is not None and custom_km > 0:
            with get_connection(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO forgotten_distance_logs (
                        vehicle_id, distance_km, notes, created_at, status, applied_refueling_id
                    ) VALUES (?, ?, 'Introduzido diretamente no abastecimento', ?, 'applied', ?)
                """, (vehicle_id, round(custom_km, 1), now_str, refueling_id))
                conn.commit()
            return round(custom_km, 1)

        # Case 2: Apply accumulated pending records
        if apply_pending:
            with get_connection(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, distance_km FROM forgotten_distance_logs
                    WHERE vehicle_id = ? AND status = 'pending'
                """, (vehicle_id,))
                rows = cursor.fetchall()
                if not rows:
                    return 0.0

                total_km = sum(float(r["distance_km"]) for r in rows)
                cursor.execute("""
                    UPDATE forgotten_distance_logs
                    SET status = 'applied', applied_refueling_id = ?
                    WHERE vehicle_id = ? AND status = 'pending'
                """, (refueling_id, vehicle_id))
                conn.commit()
                return round(total_km, 1)

        return 0.0

    def release_by_refueling(self, refueling_id: int) -> int:
        """Revert applied forgotten distance logs back to pending when a refueling is deleted.

        This ensures forgotten km are NEVER lost when deleting or fixing a refueling!
        """
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE forgotten_distance_logs
                SET status = 'pending', applied_refueling_id = NULL
                WHERE applied_refueling_id = ?
            """, (refueling_id,))
            conn.commit()
            return cursor.rowcount
