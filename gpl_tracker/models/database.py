"""SQLite database connection and schema management."""
import sqlite3
from pathlib import Path
from datetime import datetime
from gpl_tracker.config import DB_PATH, DEFAULT_CONVERSION_COST, DEFAULT_LPG_INCREASE_PERCENT, DEFAULT_PETROL_CONSUMPTION


import unicodedata


def strip_accents(text) -> str:
    """Normalize text removing accents for case and accent-insensitive search."""
    if not text:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", str(text)) if unicodedata.category(c) != "Mn").lower()


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Return a configured SQLite connection with row_factory set to sqlite3.Row."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.create_function("unaccent", 1, strip_accents)
    return conn


def init_db(db_path: Path = DB_PATH):
    """Initialize database tables and default configuration if not already present."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Vehicles table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vehicles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                make TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                engine TEXT NOT NULL DEFAULT '',
                conversion_cost REAL NOT NULL DEFAULT 1500.0,
                conversion_date TEXT NOT NULL DEFAULT '',
                conversion_odometer INTEGER NOT NULL DEFAULT 0,
                petrol_consumption REAL NOT NULL DEFAULT 7.0,
                lpg_consumption_increase REAL NOT NULL DEFAULT 20.0,
                created_at TEXT NOT NULL
            )
        """)

        # 2. Fuel stations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fuel_stations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                brand TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                municipality TEXT NOT NULL DEFAULT '',
                district TEXT NOT NULL DEFAULT '',
                latitude REAL,
                longitude REAL,
                provider TEXT NOT NULL DEFAULT 'dgeg',
                external_id TEXT UNIQUE,
                is_favorite INTEGER NOT NULL DEFAULT 0,
                use_count INTEGER NOT NULL DEFAULT 0,
                last_used_at TEXT
            )
        """)

        # 3. Station price cache table (stores last known prices with timestamp & source)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS station_price_cache (
                station_id INTEGER NOT NULL,
                lpg_price REAL,
                petrol_price REAL,
                updated_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'dgeg',
                PRIMARY KEY (station_id),
                FOREIGN KEY (station_id) REFERENCES fuel_stations(id) ON DELETE CASCADE
            )
        """)

        # 4. Refuelings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS refuelings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id INTEGER NOT NULL,
                station_id INTEGER,
                date TEXT NOT NULL,
                odometer INTEGER,
                distance_km REAL NOT NULL,
                lpg_price REAL NOT NULL,
                petrol_price REAL NOT NULL,
                amount_paid REAL NOT NULL,
                lpg_liters REAL NOT NULL,
                lpg_consumption REAL NOT NULL,
                equivalent_petrol_consumption REAL NOT NULL,
                estimated_petrol_cost REAL NOT NULL,
                savings REAL NOT NULL,
                data_source TEXT NOT NULL DEFAULT 'api',
                notes TEXT DEFAULT '',
                FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
                FOREIGN KEY (station_id) REFERENCES fuel_stations(id) ON DELETE SET NULL
            )
        """)

        # Create indices for fast querying and history
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_refuelings_date ON refuelings(date ASC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stations_favorite ON fuel_stations(is_favorite, use_count DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stations_external ON fuel_stations(external_id)")

        cursor.execute("SELECT id FROM vehicles LIMIT 1")
        if not cursor.fetchone():
            now_iso = datetime.now().strftime("%Y-%m-%d")
            cursor.execute("""
                INSERT INTO vehicles (
                    make, model, engine, conversion_cost, conversion_date,
                    conversion_odometer, petrol_consumption, lpg_consumption_increase, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "Meu Carro", "Conversão GPL", "", DEFAULT_CONVERSION_COST, now_iso,
                0, DEFAULT_PETROL_CONSUMPTION, DEFAULT_LPG_INCREASE_PERCENT, datetime.now().isoformat()
            ))

        # Check if fuel_stations needs initial seeding with official Portuguese GPL stations
        cursor.execute("SELECT COUNT(*) as cnt FROM fuel_stations")
        cnt = cursor.fetchone()["cnt"]
        if cnt < 50:
            seed_file = Path(__file__).resolve().parent.parent / "data" / "stations_seed.json"
            if seed_file.exists():
                import json
                from gpl_tracker.providers.dgeg_provider import parse_price_string
                try:
                    with open(seed_file, "r", encoding="utf-8") as f:
                        stations = json.load(f)
                    for s in stations:
                        full_address = s.get("address", "")
                        postal = s.get("postal_code", "")
                        loc = s.get("locality", "")
                        if postal and postal not in full_address:
                            full_address = f"{full_address}, {postal}".strip(", ")
                        if loc and loc not in full_address:
                            full_address = f"{full_address} {loc}".strip()

                        cursor.execute("""
                            INSERT INTO fuel_stations (
                                name, brand, address, municipality, district,
                                latitude, longitude, provider, external_id, is_favorite, use_count
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'dgeg', ?, 0, 0)
                            ON CONFLICT(external_id) DO UPDATE SET
                                name = excluded.name,
                                brand = excluded.brand,
                                address = excluded.address,
                                municipality = excluded.municipality,
                                district = excluded.district,
                                latitude = excluded.latitude,
                                longitude = excluded.longitude
                        """, (
                            s.get("name", ""),
                            s.get("brand", ""),
                            full_address,
                            s.get("municipality", ""),
                            s.get("district", ""),
                            s.get("latitude"),
                            s.get("longitude"),
                            str(s.get("external_id"))
                        ))
                        # Fetch the station ID
                        cursor.execute("SELECT id FROM fuel_stations WHERE external_id = ?", (str(s.get("external_id")),))
                        st_row = cursor.fetchone()
                        if st_row:
                            st_id = st_row["id"]
                            price_val = parse_price_string(s.get("last_lpg_price"))
                            if price_val:
                                cursor.execute("""
                                    INSERT INTO station_price_cache (station_id, lpg_price, petrol_price, updated_at, source)
                                    VALUES (?, ?, NULL, ?, 'dgeg')
                                    ON CONFLICT(station_id) DO UPDATE SET
                                        lpg_price = excluded.lpg_price,
                                        updated_at = excluded.updated_at
                                """, (st_id, price_val, s.get("last_update") or datetime.now().strftime("%Y-%m-%d")))
                except Exception:
                    pass

        conn.commit()

