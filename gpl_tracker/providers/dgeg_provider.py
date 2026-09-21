"""Official DGEG (Direção-Geral de Energia e Geologia) fuel provider implementation."""
import re
import logging
from typing import List, Optional, Dict, Any
import requests

from gpl_tracker.config import DGEG_BASE_URL, DGEG_TIMEOUT_SECONDS
from gpl_tracker.models.schemas import FuelPriceInfo
from gpl_tracker.providers.base import FuelStationProvider, FuelPriceProvider

logger = logging.getLogger(__name__)


def parse_price_string(price_str: Any) -> Optional[float]:
    """Parse price strings like '0,859 €/litro', '0.859', or 0.859 into float."""
    if price_str is None:
        return None
    if isinstance(price_str, (int, float)):
        return float(price_str)
    # Remove currency symbol, spaces, /litro, etc.
    s = str(price_str).replace("€", "").replace("/litro", "").replace(" ", "").strip()
    s = s.replace(",", ".")
    # Match decimal pattern
    match = re.search(r"(\d+(?:\.\d+)?)", s)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


class DGEGProvider(FuelStationProvider, FuelPriceProvider):
    """Direct provider connecting to DGEG's REST service."""

    def __init__(self, base_url: str = DGEG_BASE_URL, timeout: float = DGEG_TIMEOUT_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        })

    def search_stations(self, query: str, district: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Search stations on DGEG by name, brand, or location."""
        query_str = query.strip()
        url = f"{self.base_url}/PesquisarPostos"
        params = {
            "nome": query_str,
            "qtdPorPagina": min(limit, 50),
            "pagina": 1
        }
        if district:
            params["distrito"] = district

        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code != 200:
                logger.warning("DGEG search returned status code %s", resp.status_code)
                return []

            data = resp.json()
            results = data.get("resultado") or []
            stations = []
            for r in results:
                st_id = str(r.get("Id"))
                name = r.get("Nome") or ""
                brand = r.get("Marca") or ""
                morada = r.get("Morada") or ""
                localidade = r.get("Localidade") or ""
                municipio = r.get("Municipio") or ""
                distrito = r.get("Distrito") or ""
                cod_postal = r.get("CodPostal") or ""
                full_address = f"{morada}, {cod_postal} {localidade}".strip(", ")

                lat = None
                lon = None
                try:
                    if r.get("Latitude") is not None:
                        lat = float(r["Latitude"])
                    if r.get("Longitude") is not None:
                        lon = float(r["Longitude"])
                except (ValueError, TypeError):
                    pass

                stations.append({
                    "external_id": st_id,
                    "name": name,
                    "brand": brand,
                    "address": full_address,
                    "municipality": municipio,
                    "district": distrito,
                    "latitude": lat,
                    "longitude": lon,
                    "provider": "dgeg"
                })
            return stations
        except Exception as e:
            logger.warning("Error searching DGEG stations: %s", e)
            return []

    def get_station_details(self, external_id: str) -> Optional[Dict[str, Any]]:
        """Get station details from DGEG."""
        url = f"{self.base_url}/GetDadosPosto"
        params = {"id": external_id}
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not data.get("status"):
                return None
            res = data.get("resultado") or {}
            morada_dict = res.get("Morada") or {}
            full_addr = f"{morada_dict.get('Morada', '')}, {morada_dict.get('CodPostal', '')} {morada_dict.get('Localidade', '')}".strip(", ")
            return {
                "external_id": str(res.get("Id", external_id)),
                "name": res.get("Nome", ""),
                "brand": res.get("Marca", ""),
                "address": full_addr,
                "municipality": morada_dict.get("Municipio", ""),
                "district": morada_dict.get("Distrito", ""),
                "latitude": morada_dict.get("Latitude"),
                "longitude": morada_dict.get("Longitude"),
                "provider": "dgeg",
                "raw_fuels": res.get("Combustiveis", [])
            }
        except Exception as e:
            logger.warning("Error getting DGEG station details for %s: %s", external_id, e)
            return None

    def get_prices(self, external_id: str) -> FuelPriceInfo:
        """Fetch current GPL Auto and Petrol 95 prices for a given station."""
        url = f"{self.base_url}/GetDadosPosto"
        params = {"id": external_id}
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code != 200:
                return FuelPriceInfo(
                    source="manual",
                    is_estimated=True,
                    message=f"DGEG respondeu com status {resp.status_code}."
                )
            data = resp.json()
            if not data.get("status"):
                return FuelPriceInfo(
                    source="manual",
                    is_estimated=True,
                    message="Posto não encontrado na DGEG."
                )

            res = data.get("resultado") or {}
            fuels = res.get("Combustiveis") or []

            lpg_price = None
            petrol_price = None
            latest_update = ""

            for f in fuels:
                fuel_name = (f.get("TipoCombustivel") or "").lower()
                price_val = parse_price_string(f.get("Preco"))
                update_date = f.get("DataAtualizacao") or ""

                if "gpl" in fuel_name or "autogas" in fuel_name:
                    lpg_price = price_val
                    if update_date > latest_update:
                        latest_update = update_date
                elif "gasolina simples 95" in fuel_name or ("gasolina" in fuel_name and "95" in fuel_name and "especial" not in fuel_name):
                    petrol_price = price_val
                    if update_date > latest_update:
                        latest_update = update_date
                # Fallback to special 95 if simple 95 not yet found
                elif petrol_price is None and "gasolina" in fuel_name and "95" in fuel_name:
                    petrol_price = price_val

            return FuelPriceInfo(
                station_name=res.get("Nome"),
                lpg_price=lpg_price,
                petrol_price=petrol_price,
                updated_at=latest_update,
                source="dgeg",
                is_estimated=False,
                message="Preços obtidos diretamente da DGEG."
            )
        except requests.Timeout:
            logger.warning("DGEG timeout for station %s", external_id)
            return FuelPriceInfo(
                source="manual",
                is_estimated=True,
                message="Tempo limite de ligação à DGEG excedido (timeout)."
            )
        except Exception as e:
            logger.warning("Error fetching DGEG prices for station %s: %s", external_id, e)
            return FuelPriceInfo(
                source="manual",
                is_estimated=True,
                message=f"Erro ao contactar DGEG: {e}"
            )

