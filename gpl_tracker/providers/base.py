"""Abstract interfaces for Fuel Station, Fuel Price, and Receipt Parser providers."""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from gpl_tracker.models.schemas import StationBase, FuelPriceInfo


class FuelStationProvider(ABC):
    """Abstract interface for fuel station directory providers."""

    @abstractmethod
    def search_stations(self, query: str, district: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Search fuel stations by name, brand, or locality."""
        pass

    @abstractmethod
    def get_station_details(self, external_id: str) -> Optional[Dict[str, Any]]:
        """Get full details of a specific station by its external provider ID."""
        pass


class FuelPriceProvider(ABC):
    """Abstract interface for fuel price providers."""

    @abstractmethod
    def get_prices(self, external_id: str) -> FuelPriceInfo:
        """Fetch current prices for GPL Auto and Petrol 95 for a given station."""
        pass


class ReceiptParserProvider(ABC):
    """Abstract interface for future OCR / Receipt reading capability (Req #5)."""

    @abstractmethod
    def parse_receipt_image(self, image_bytes: bytes) -> Dict[str, Any]:
        """Extract amount paid, liters, price/L, date, and station from a receipt image."""
        pass

