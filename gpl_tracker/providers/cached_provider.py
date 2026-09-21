"""Hybrid cached provider managing the fallback hierarchy: DGEG -> Local Cache -> Last Known -> Manual."""
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

from gpl_tracker.models.database import get_connection
from gpl_tracker.models.schemas import FuelPriceInfo
from gpl_tracker.providers.dgeg_provider import DGEGProvider
from gpl_tracker.providers.apiaberta_provider import APIAbertaProvider
from gpl_tracker.config import DB_PATH

logger = logging.getLogger(__name__)


class CachedFuelProvider:
    """Orchestrates station lookup and fuel prices with a multi-tier fallback strategy."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.dgeg = DGEGProvider()
        self.api_aberta = APIAbertaProvider()

    def get_prices_for_station(self, station_db_id: int, external_id: Optional[str] = None) -> FuelPriceInfo:
        """Fetch prices adhering to the hierarchy: DGEG -> Local Cache -> Last Known -> Manual.

        1. If external_id exists, try DGEG.
        2. If DGEG returns prices, save to local cache table and return with source='dgeg'.
        3. If DGEG fails/timeouts or lacks prices:
           a. Check station_price_cache table.
           b. Check last refueling recorded for this station.
           c. Check last refueling recorded across any station.
           d. Check API Aberta national average.
        4. If still nothing found, return empty with source='manual'.
        """
        # Step 1: Try DGEG if external_id is provided
        if external_id:
            try:
                dgeg_info = self.dgeg.get_prices(external_id)
                if dgeg_info.lpg_price is not None:
                    # Update local cache in SQLite
                    self._save_to_cache(
                        station_id=station_db_id,
                        lpg_price=dgeg_info.lpg_price,
                        petrol_price=dgeg_info.petrol_price,
                        updated_at=dgeg_info.updated_at or datetime.now().strftime("%Y-%m-%d %H:%M"),
                        source="dgeg"
                    )
                    return dgeg_info
            except Exception as e:
                logger.warning("DGEG lookup failed for station %s: %s", external_id, e)

        # Step 2: Check SQLite station_price_cache for this specific station
        cached = self._get_from_cache(station_db_id)
        if cached and cached.get("lpg_price") is not None:
            return FuelPriceInfo(
                station_id=station_db_id,
                lpg_price=cached["lpg_price"],
                petrol_price=cached.get("petrol_price"),
                updated_at=cached.get("updated_at", ""),
                source="cache",
                is_estimated=True,
                message=f"Preço obtido da cache local (atualizado em: {cached.get('updated_at', 'anteriormente')})."
            )

        # Step 3: Check last recorded refueling for this station
        last_station_price = self._get_last_refueling_price(station_id=station_db_id)
        if last_station_price:
            return FuelPriceInfo(
                station_id=station_db_id,
                lpg_price=last_station_price["lpg_price"],
                petrol_price=last_station_price.get("petrol_price"),
                updated_at=last_station_price.get("date", ""),
                source="cache",
                is_estimated=True,
                message=f"Último preço registado neste posto ({last_station_price.get('date', '')})."
            )

        # Step 4: Check last recorded refueling globally (any station)
        global_last_price = self._get_last_refueling_price(station_id=None)
        if global_last_price:
            return FuelPriceInfo(
                station_id=station_db_id,
                lpg_price=global_last_price["lpg_price"],
                petrol_price=global_last_price.get("petrol_price"),
                updated_at=global_last_price.get("date", ""),
                source="cache",
                is_estimated=True,
                message=f"Último preço conhecido de abastecimentos anteriores ({global_last_price.get('date', '')})."
            )

        # Step 5: Fallback to API Aberta national benchmark
        try:
            aberta_info = self.api_aberta.get_national_average_prices()
            if aberta_info.lpg_price is not None:
                aberta_info.station_id = station_db_id
                return aberta_info
        except Exception:
            pass

        # Step 6: Pure manual fallback
        return FuelPriceInfo(
            station_id=station_db_id,
            lpg_price=None,
            petrol_price=None,
            updated_at="",
            source="manual",
            is_estimated=True,
            message="Sem histórico de preços disponível. Por favor introduza o preço manualmente."
        )

    def _save_to_cache(self, station_id: int, lpg_price: float, petrol_price: Optional[float], updated_at: str, source: str):
        """Upsert price into SQLite station_price_cache."""
        try:
            with get_connection(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO station_price_cache (station_id, lpg_price, petrol_price, updated_at, source)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(station_id) DO UPDATE SET
                        lpg_price = excluded.lpg_price,
                        petrol_price = excluded.petrol_price,
                        updated_at = excluded.updated_at,
                        source = excluded.source
                """, (station_id, lpg_price, petrol_price, updated_at, source))
                conn.commit()
        except Exception as e:
            logger.warning("Failed to save price to cache: %s", e)

    def _get_from_cache(self, station_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve price from SQLite station_price_cache."""
        try:
            with get_connection(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT lpg_price, petrol_price, updated_at, source
                    FROM station_price_cache
                    WHERE station_id = ?
                """, (station_id,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
        except Exception as e:
            logger.warning("Failed to read price from cache: %s", e)
        return None

    def _get_last_refueling_price(self, station_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Retrieve the price from the most recent refueling record."""
        try:
            with get_connection(self.db_path) as conn:
                cursor = conn.cursor()
                if station_id:
                    cursor.execute("""
                        SELECT lpg_price, petrol_price, date
                        FROM refuelings
                        WHERE station_id = ?
                        ORDER BY date DESC, id DESC
                        LIMIT 1
                    """, (station_id,))
                else:
                    cursor.execute("""
                        SELECT lpg_price, petrol_price, date
                        FROM refuelings
                        ORDER BY date DESC, id DESC
                        LIMIT 1
                    """)
                row = cursor.fetchone()
                if row:
                    return dict(row)
        except Exception as e:
            logger.warning("Failed to read last refueling price: %s", e)
        return None

