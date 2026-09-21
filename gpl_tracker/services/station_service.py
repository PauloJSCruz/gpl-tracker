"""Service for managing fuel stations, favorites, and usage patterns."""
import math
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime

from gpl_tracker.config import DB_PATH
from gpl_tracker.models.database import get_connection
from gpl_tracker.models.schemas import StationOut, StationCreate, FuelPriceInfo
from gpl_tracker.providers.cached_provider import CachedFuelProvider
from gpl_tracker.providers.dgeg_provider import DGEGProvider


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance between two points in kilometers."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


class StationService:
    """Manages stations, favorites, habits, and search."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.price_provider = CachedFuelProvider(db_path=db_path)
        self.dgeg_provider = DGEGProvider()

    def list_stations(self, limit: int = 50) -> List[StationOut]:
        """List stations sorted by favorite and frequency of use."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.*, c.lpg_price, c.petrol_price, c.updated_at as cache_date, c.source as cache_source
                FROM fuel_stations s
                LEFT JOIN station_price_cache c ON s.id = c.station_id
                ORDER BY s.is_favorite DESC, s.use_count DESC, s.last_used_at DESC, s.name ASC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [self._row_to_station_out(r) for r in rows]

    def get_habitual_and_favorites(self) -> List[StationOut]:
        """Get the most frequent stations and favorites for quick selection."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.*, c.lpg_price, c.petrol_price, c.updated_at as cache_date, c.source as cache_source
                FROM fuel_stations s
                LEFT JOIN station_price_cache c ON s.id = c.station_id
                WHERE s.is_favorite = 1 OR s.use_count > 0
                ORDER BY s.is_favorite DESC, s.use_count DESC, s.last_used_at DESC
                LIMIT 10
            """)
            rows = cursor.fetchall()
            return [self._row_to_station_out(r) for r in rows]

    def get_municipalities(self) -> List[str]:
        """Get distinct municipalities with stations in the database."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT municipality FROM fuel_stations WHERE municipality != '' ORDER BY municipality ASC")
            return [r["municipality"] for r in cursor.fetchall()]

    def get_districts(self) -> List[str]:
        """Get distinct districts with stations in the database."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT district FROM fuel_stations WHERE district != '' ORDER BY district ASC")
            return [r["district"] for r in cursor.fetchall()]

    def search_stations(
        self,
        query: str,
        municipality: Optional[str] = None,
        district: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        limit: int = 50
    ) -> List[StationOut]:
        """Multi-token intelligent search across name, brand, address, municipality, and district."""
        query_clean = query.strip()
        local_results = self._search_local(
            query=query_clean,
            municipality=municipality,
            district=district,
            limit=limit
        )

        # If coordinates provided, sort by distance
        if lat is not None and lon is not None:
            def distance_key(st: StationOut):
                if st.latitude is not None and st.longitude is not None:
                    return haversine_distance_km(lat, lon, st.latitude, st.longitude)
                return 99999.0
            local_results.sort(key=distance_key)

        return local_results

    def get_station_by_id(self, station_id: int) -> Optional[StationOut]:
        """Get station by local DB ID."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.*, c.lpg_price, c.petrol_price, c.updated_at as cache_date, c.source as cache_source
                FROM fuel_stations s
                LEFT JOIN station_price_cache c ON s.id = c.station_id
                WHERE s.id = ?
            """, (station_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_station_out(row)

    def get_station_prices(self, station_id: int) -> FuelPriceInfo:
        """Fetch automatic prices for a given station using the fallback hierarchy."""
        st = self.get_station_by_id(station_id)
        if not st:
            return FuelPriceInfo(
                station_id=station_id,
                source="manual",
                is_estimated=True,
                message="Posto não encontrado."
            )
        return self.price_provider.get_prices_for_station(
            station_db_id=station_id,
            external_id=st.external_id
        )

    def toggle_favorite(self, station_id: int) -> bool:
        """Toggle favorite status of a station."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_favorite FROM fuel_stations WHERE id = ?", (station_id,))
            row = cursor.fetchone()
            if not row:
                return False
            new_val = 0 if row["is_favorite"] else 1
            cursor.execute("UPDATE fuel_stations SET is_favorite = ? WHERE id = ?", (new_val, station_id))
            conn.commit()
            return bool(new_val)

    def record_usage(self, station_id: int):
        """Increment station usage counter and set last_used_at timestamp."""
        with get_connection(self.db_path) as conn:
            now_iso = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute("""
                UPDATE fuel_stations
                SET use_count = use_count + 1, last_used_at = ?
                WHERE id = ?
            """, (now_iso, station_id))
            conn.commit()

    def add_custom_station(self, station: StationCreate) -> StationOut:
        """Create a new manual/custom station."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO fuel_stations (
                    name, brand, address, municipality, district,
                    latitude, longitude, provider, external_id, is_favorite
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                station.name, station.brand, station.address, station.municipality,
                station.district, station.latitude, station.longitude,
                station.provider, station.external_id, 1 if station.is_favorite else 0
            ))
            new_id = cursor.lastrowid
            conn.commit()
        return self.get_station_by_id(new_id)

    def _search_local(
        self,
        query: str,
        municipality: Optional[str] = None,
        district: Optional[str] = None,
        limit: int = 50
    ) -> List[StationOut]:
        """Search local fuel_stations table using multi-token matching and unaccent."""
        from gpl_tracker.models.database import strip_accents

        where_clauses = ["1=1"]
        params = []

        if query:
            tokens = [strip_accents(t) for t in query.split() if t.strip()]
            for token in tokens:
                where_clauses.append(
                    "unaccent(s.name || ' ' || s.brand || ' ' || s.address || ' ' || s.municipality || ' ' || s.district) LIKE ?"
                )
                params.append(f"%{token}%")

        if municipality:
            where_clauses.append("unaccent(s.municipality) = unaccent(?)")
            params.append(municipality)

        if district:
            where_clauses.append("unaccent(s.district) = unaccent(?)")
            params.append(district)

        sql = f"""
            SELECT s.*, c.lpg_price, c.petrol_price, c.updated_at as cache_date, c.source as cache_source
            FROM fuel_stations s
            LEFT JOIN station_price_cache c ON s.id = c.station_id
            WHERE {' AND '.join(where_clauses)}
            ORDER BY s.is_favorite DESC, s.use_count DESC, s.name ASC
            LIMIT ?
        """
        params.append(limit)

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            return [self._row_to_station_out(r) for r in rows]

    def _upsert_station_from_dgeg(self, st_data: Dict[str, Any]):
        """Insert or ignore station fetched from DGEG into local SQLite DB."""
        ext_id = st_data.get("external_id")
        if not ext_id:
            return
        try:
            with get_connection(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO fuel_stations (
                        name, brand, address, municipality, district,
                        latitude, longitude, provider, external_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'dgeg', ?)
                    ON CONFLICT(external_id) DO UPDATE SET
                        name = excluded.name,
                        brand = excluded.brand,
                        address = excluded.address,
                        municipality = excluded.municipality,
                        district = excluded.district,
                        latitude = excluded.latitude,
                        longitude = excluded.longitude
                """, (
                    st_data.get("name", ""),
                    st_data.get("brand", ""),
                    st_data.get("address", ""),
                    st_data.get("municipality", ""),
                    st_data.get("district", ""),
                    st_data.get("latitude"),
                    st_data.get("longitude"),
                    str(ext_id)
                ))
                conn.commit()
        except Exception:
            pass

    def _row_to_station_out(self, row: Any) -> StationOut:
        """Convert a database row to a StationOut schema."""
        return StationOut(
            id=row["id"],
            name=row["name"],
            brand=row["brand"] or "",
            address=row["address"] or "",
            municipality=row["municipality"] or "",
            district=row["district"] or "",
            latitude=row["latitude"],
            longitude=row["longitude"],
            provider=row["provider"] or "dgeg",
            external_id=row["external_id"],
            is_favorite=bool(row["is_favorite"]),
            use_count=int(row["use_count"] or 0),
            last_used_at=row["last_used_at"],
            last_lpg_price=row["lpg_price"],
            last_petrol_price=row["petrol_price"],
            last_price_date=row["cache_date"],
            last_price_source=row["cache_source"]
        )

