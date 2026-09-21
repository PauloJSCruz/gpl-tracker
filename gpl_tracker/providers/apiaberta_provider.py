"""Secondary provider using API Aberta for national average fuel prices in Portugal."""
import logging
from typing import Optional, Dict, Any
import requests

from gpl_tracker.config import API_ABERTA_URL, DGEG_TIMEOUT_SECONDS
from gpl_tracker.models.schemas import FuelPriceInfo

logger = logging.getLogger(__name__)


class APIAbertaProvider:
    """Fetches national average prices from API Aberta."""

    def __init__(self, url: str = API_ABERTA_URL, timeout: float = DGEG_TIMEOUT_SECONDS):
        self.url = url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "GPLTracker/1.0",
            "Accept": "application/json"
        })

    def get_national_average_prices(self) -> FuelPriceInfo:
        """Fetch Portugal national average fuel prices."""
        try:
            resp = self.session.get(self.url, timeout=self.timeout)
            if resp.status_code != 200:
                return FuelPriceInfo(
                    source="manual",
                    is_estimated=True,
                    message="API Aberta indisponível."
                )

            data = resp.json().get("data", [])
            lpg_price = None
            petrol_price = None
            update_date = ""

            for item in data:
                slug = item.get("fuel_slug")
                avg = item.get("avg_price_eur")
                dt = item.get("date") or ""
                if dt > update_date:
                    update_date = dt

                if slug == "gpl_auto":
                    lpg_price = float(avg) if avg else None
                elif slug == "gasoline_95":
                    petrol_price = float(avg) if avg else None

            return FuelPriceInfo(
                lpg_price=lpg_price,
                petrol_price=petrol_price,
                updated_at=update_date,
                source="apiaberta",
                is_estimated=True,
                message="Preços médios nacionais obtidos da API Aberta."
            )
        except Exception as e:
            logger.warning("Error fetching API Aberta prices: %s", e)
            return FuelPriceInfo(
                source="manual",
                is_estimated=True,
                message="Erro ao contactar API Aberta."
            )

