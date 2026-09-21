"""Data schemas and Pydantic models for GPL Tracker."""
from typing import Optional, List
from pydantic import BaseModel, Field


class VehicleBase(BaseModel):
    make: str = Field(default="", description="Marca do veículo (ex: Renault, Dacia, Fiat)")
    model: str = Field(default="", description="Modelo do veículo (ex: Clio, Duster, Punto)")
    engine: str = Field(default="", description="Motorização (ex: 0.9 TCe, 1.2 16V)")
    conversion_cost: float = Field(default=1500.0, ge=0.0, description="Custo da conversão (€)")
    conversion_date: str = Field(default="", description="Data da conversão (AAAA-MM-DD)")
    conversion_odometer: int = Field(default=0, ge=0, description="Quilometragem no momento da conversão (km)")
    petrol_consumption: float = Field(default=7.0, ge=0.0, description="Consumo de referência a gasolina (L/100 km)")
    lpg_consumption_increase: float = Field(
        default=20.0,
        ge=0.0,
        le=100.0,
        description="Aumento percentual de consumo em GPL relativamente à gasolina (ex: 20.0 para 20%)"
    )


class VehicleCreate(VehicleBase):
    pass


class VehicleOut(VehicleBase):
    id: int
    created_at: str


class StationBase(BaseModel):
    name: str
    brand: str = ""
    address: str = ""
    municipality: str = ""
    district: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    provider: str = "dgeg"
    external_id: Optional[str] = None
    is_favorite: bool = False


class StationCreate(StationBase):
    pass


class StationOut(StationBase):
    id: int
    use_count: int = 0
    last_used_at: Optional[str] = None
    last_lpg_price: Optional[float] = None
    last_petrol_price: Optional[float] = None
    last_price_date: Optional[str] = None
    last_price_source: Optional[str] = None


class FuelPriceInfo(BaseModel):
    station_id: Optional[int] = None
    station_name: Optional[str] = None
    lpg_price: Optional[float] = None
    petrol_price: Optional[float] = None
    updated_at: str = ""
    source: str = "manual"  # 'dgeg', 'cache', 'apiaberta', 'manual'
    is_estimated: bool = False
    message: str = ""


class RefuelingCreate(BaseModel):
    station_id: Optional[int] = None
    station_name: Optional[str] = None  # Para permitir posto ad-hoc se necessário
    date: str  # YYYY-MM-DD or YYYY-MM-DDTHH:MM
    distance_km: float = Field(..., gt=0.0, description="Km percorridos desde o último abastecimento")
    amount_paid: float = Field(..., gt=0.0, description="Valor pago pelo abastecimento em GPL (€)")
    lpg_price: float = Field(..., gt=0.0, description="Preço do GPL (€/L)")
    petrol_price: float = Field(..., gt=0.0, description="Preço de referência da gasolina 95 (€/L)")
    odometer: Optional[int] = None
    data_source: str = "api"  # 'api', 'cache', 'user'
    notes: Optional[str] = ""


class RefuelingUpdate(BaseModel):
    station_id: Optional[int] = None
    date: Optional[str] = None
    distance_km: Optional[float] = None
    amount_paid: Optional[float] = None
    lpg_price: Optional[float] = None
    petrol_price: Optional[float] = None
    odometer: Optional[int] = None
    data_source: Optional[str] = None
    notes: Optional[str] = None


class RefuelingOut(BaseModel):
    id: int
    vehicle_id: int
    station_id: Optional[int] = None
    station_name: str = ""
    station_brand: str = ""
    date: str
    odometer: Optional[int] = None
    distance_km: float
    lpg_price: float
    petrol_price: float
    amount_paid: float
    lpg_liters: float
    lpg_consumption: float
    equivalent_petrol_consumption: float
    estimated_petrol_cost: float
    savings: float
    cumulative_savings: float = 0.0
    data_source: str
    notes: Optional[str] = ""


class BreakEvenProjection(BaseModel):
    status: str  # 'insufficient_data', 'recovering', 'recovered'
    message: str
    remaining_km: Optional[float] = None
    remaining_months: Optional[float] = None
    avg_km_per_month: Optional[float] = None
    avg_savings_per_km: Optional[float] = None


class FinancialSummary(BaseModel):
    total_refuelings: int
    total_distance_km: float
    total_lpg_liters: float
    total_lpg_spent: float
    total_petrol_hypothetical_cost: float
    total_savings: float
    avg_savings_per_km: float
    avg_savings_per_100km: float
    avg_lpg_consumption: float
    avg_petrol_consumption: float
    conversion_cost: float
    recovered_percent: float
    remaining_amount: float
    is_recovered: bool
    net_profit: float
    break_even: BreakEvenProjection

