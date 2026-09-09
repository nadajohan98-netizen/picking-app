"""
Un único objeto `templates` compartido por todos los routers, para no crear uno
distinto en cada archivo.
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=BASE_DIR / "templates")
