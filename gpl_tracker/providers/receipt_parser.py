"""Receipt and invoice parsing interface (prepared for future OCR integration)."""
from typing import Dict, Any, Optional
from gpl_tracker.providers.base import ReceiptParserProvider


class MockReceiptParser(ReceiptParserProvider):
    """Stub receipt parser providing the foundation for future OCR / vision models."""

    def parse_receipt_image(self, image_bytes: bytes) -> Dict[str, Any]:
        """Extract information from receipt image bytes.

        Returns:
            Dictionary with extracted fields (amount_paid, lpg_liters, lpg_price, date, station_name)
        """
        # Architectural placeholder for OCR engine (e.g. Tesseract, PaddleOCR, or Gemini Vision)
        return {
            "amount_paid": None,
            "lpg_liters": None,
            "lpg_price": None,
            "date": None,
            "station_name": None,
            "confidence": 0.0,
            "is_supported": False,
            "message": "Módulo OCR reservado para expansão futura."
        }

