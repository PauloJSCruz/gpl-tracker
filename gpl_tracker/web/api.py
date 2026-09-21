"""FastAPI REST API routes and application setup for GPL Tracker."""
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from gpl_tracker.models.database import init_db
from gpl_tracker.models.schemas import (
    VehicleCreate, VehicleOut, StationOut, StationCreate,
    RefuelingCreate, RefuelingUpdate, RefuelingOut,
    FinancialSummary, FuelPriceInfo
)
from gpl_tracker.services.vehicle_service import VehicleService
from gpl_tracker.services.station_service import StationService
from gpl_tracker.services.refueling_service import RefuelingService
from gpl_tracker.services.export_service import ExportService
from gpl_tracker.config import DB_PATH

# Initialize database schema
init_db(DB_PATH)

app = FastAPI(
    title="GPL Tracker",
    description="Contador Financeiro Inteligente & ROI de Conversão para GPL",
    version="1.0.0"
)

# CORS middleware for local usage
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instantiate services
vehicle_service = VehicleService(db_path=DB_PATH)
station_service = StationService(db_path=DB_PATH)
refueling_service = RefuelingService(db_path=DB_PATH)
export_service = ExportService(db_path=DB_PATH)

# Path to static frontend files
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve the single-page application dashboard."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return HTMLResponse("<h1>GPL Tracker</h1><p>Frontend em carregamento...</p>")


# --- Vehicle Endpoints ---

@app.get("/api/vehicle", response_model=VehicleOut)
def get_vehicle():
    """Get the active vehicle configuration."""
    veh = vehicle_service.get_vehicle(1)
    if not veh:
        raise HTTPException(status_code=404, detail="Veículo não encontrado.")
    return veh


@app.put("/api/vehicle", response_model=VehicleOut)
def update_vehicle(data: VehicleCreate):
    """Update vehicle configuration parameters."""
    veh = vehicle_service.update_vehicle(1, data)
    if not veh:
        raise HTTPException(status_code=400, detail="Erro ao atualizar veículo.")
    return veh


# --- Station Endpoints ---

@app.get("/api/stations", response_model=List[StationOut])
def list_stations(limit: int = 50):
    """List stations with habitual and favorites ordered first."""
    return station_service.list_stations(limit=limit)


@app.get("/api/stations/quick", response_model=List[StationOut])
def get_quick_stations():
    """Get habitual and favorite stations for fast one-click selection."""
    return station_service.get_habitual_and_favorites()


@app.get("/api/stations/municipalities", response_model=List[str])
def get_municipalities():
    """Get list of municipalities (concelhos) with GPL stations."""
    return station_service.get_municipalities()


@app.get("/api/stations/districts", response_model=List[str])
def get_districts():
    """Get list of districts with GPL stations."""
    return station_service.get_districts()


@app.get("/api/stations/search", response_model=List[StationOut])
def search_stations(
    q: str = Query(default="", description="Search query string"),
    municipality: Optional[str] = Query(default=None, description="Concelho / Município filter"),
    district: Optional[str] = Query(default=None, description="Distrito filter"),
    lat: Optional[float] = Query(default=None, description="Latitude for distance sorting"),
    lon: Optional[float] = Query(default=None, description="Longitude for distance sorting")
):
    """Search stations in local database with multi-token matching."""
    return station_service.search_stations(
        query=q,
        municipality=municipality,
        district=district,
        lat=lat,
        lon=lon
    )


@app.post("/api/stations", response_model=StationOut)
def create_station(station: StationCreate):
    """Create a manual / custom fuel station."""
    return station_service.add_custom_station(station)


@app.post("/api/stations/{station_id}/favorite")
def toggle_station_favorite(station_id: int):
    """Toggle favorite status of a station."""
    is_fav = station_service.toggle_favorite(station_id)
    return {"station_id": station_id, "is_favorite": is_fav}


@app.get("/api/stations/{station_id}/prices", response_model=FuelPriceInfo)
def get_station_prices(station_id: int):
    """Automatically retrieve LPG and Petrol prices for a station with fallback strategy."""
    return station_service.get_station_prices(station_id)


# --- Refueling Endpoints ---

@app.get("/api/refuelings", response_model=List[RefuelingOut])
def list_refuelings():
    """List all refueling records in reverse chronological order."""
    return refueling_service.list_refuelings(vehicle_id=1)


@app.post("/api/refuelings", response_model=RefuelingOut)
def create_refueling(data: RefuelingCreate):
    """Create a new refueling record and auto-calculate all metrics."""
    try:
        return refueling_service.add_refueling(data, vehicle_id=1)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/refuelings/last", response_model=Optional[RefuelingOut])
def get_last_refueling():
    """Retrieve the most recent refueling record (for '+ Abasteci novamente')."""
    return refueling_service.get_last_refueling(vehicle_id=1)


@app.get("/api/refuelings/{refueling_id}", response_model=RefuelingOut)
def get_refueling(refueling_id: int):
    """Retrieve a specific refueling record."""
    item = refueling_service.get_refueling(refueling_id)
    if not item:
        raise HTTPException(status_code=404, detail="Registo não encontrado.")
    return item


@app.put("/api/refuelings/{refueling_id}", response_model=RefuelingOut)
def update_refueling(refueling_id: int, data: RefuelingUpdate):
    """Update a refueling record and recalculate metrics."""
    try:
        updated = refueling_service.update_refueling(refueling_id, data)
        if not updated:
            raise HTTPException(status_code=404, detail="Registo não encontrado.")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/refuelings/{refueling_id}")
def delete_refueling(refueling_id: int):
    """Delete a refueling record."""
    success = refueling_service.delete_refueling(refueling_id)
    if not success:
        raise HTTPException(status_code=404, detail="Registo não encontrado.")
    return {"status": "deleted", "id": refueling_id}


@app.post("/api/refuelings/{refueling_id}/duplicate", response_model=RefuelingOut)
def duplicate_refueling(refueling_id: int):
    """Duplicate a refueling record with today's date."""
    dup = refueling_service.duplicate_refueling(refueling_id)
    if not dup:
        raise HTTPException(status_code=404, detail="Registo não encontrado.")
    return dup


# --- Dashboard & Financial Summary ---

@app.get("/api/dashboard", response_model=FinancialSummary)
def get_dashboard_summary():
    """Get complete financial summary, cumulative savings, ROI, and break-even."""
    return refueling_service.get_dashboard_summary(vehicle_id=1)


# --- Export Endpoints ---

@app.get("/api/export/csv")
def export_csv():
    """Export history to CSV file."""
    csv_bytes = export_service.export_csv(vehicle_id=1)
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=gpl_historico.csv"}
    )


@app.get("/api/export/excel")
def export_excel():
    """Export history and financial summary to Excel (.xlsx) file."""
    excel_bytes = export_service.export_excel(vehicle_id=1)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=gpl_relatorio_financeiro.xlsx"}
    )

