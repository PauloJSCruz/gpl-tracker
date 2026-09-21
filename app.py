"""Ponto de entrada principal da aplicação GPL Tracker.

Execução:
    python app.py
"""
import sys
import argparse
import threading
import time
import webbrowser
import uvicorn

from gpl_tracker.config import SERVER_HOST, SERVER_PORT
from gpl_tracker.web.api import app


if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def open_browser(url: str, delay: float = 1.2):
    """Abre o navegador após um curto atraso para o servidor inicializar."""
    time.sleep(delay)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="GPL Tracker - Contador Financeiro & ROI de Conversão para GPL")
    parser.add_argument("--host", default=SERVER_HOST, help=f"Endereço IP (por defeito: {SERVER_HOST})")
    parser.add_argument("--port", type=int, default=SERVER_PORT, help=f"Porta HTTP (por defeito: {SERVER_PORT})")
    parser.add_argument("--no-browser", action="store_true", help="Não abrir o navegador automaticamente")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    print("=" * 65)
    print("  GPL Tracker - Contador Financeiro & ROI de Conversao para GPL")
    print("=" * 65)
    print(f"  Aplicacao disponivel em: {url}")
    print("  Pressione Ctrl+C para encerrar o servidor.")
    print("=" * 65)

    if not args.no_browser:
        threading.Thread(target=open_browser, args=(url,), daemon=True).start()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

