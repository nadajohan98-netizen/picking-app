"""
Arranca el servidor de desarrollo.

    py run.py

Luego abre http://127.0.0.1:8000 en el navegador.

- host="127.0.0.1": solo accesible desde este mismo computador. Cuando queramos
  que otros equipos de la red entren (Fase 4 en adelante), se cambia a "0.0.0.0".
- reload=True: si editas un archivo .py, el servidor se reinicia solo.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
