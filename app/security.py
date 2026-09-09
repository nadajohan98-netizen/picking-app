"""
Seguridad: hash de contraseñas y clave secreta de las cookies.

Sobre el hash
-------------
Nunca guardamos la contraseña tal cual. Guardamos el resultado de pasarla por
PBKDF2 (una función lenta a propósito) junto con:

  - un "salt" (grano de sal) aleatorio y distinto por usuario, para que dos
    personas con la misma contraseña tengan hashes diferentes;
  - el número de iteraciones (cuántas vueltas de cálculo), guardado dentro del
    propio texto para poder subirlo en el futuro sin romper los hashes viejos.

Formato del texto guardado (parecido al de Django):

    pbkdf2_sha256$<iteraciones>$<salt_base64>$<hash_base64>

`hashlib` y `secrets` son de la librería estándar de Python: cero dependencias.
Para una app en red local esto es seguro de sobra. Si algún día sale a internet
se puede cambiar a Argon2 o bcrypt sin tocar el resto del código.
"""

import base64
import hashlib
import hmac
import secrets
from pathlib import Path

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 200_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Convierte una contraseña en texto plano en el texto seguro que guardamos."""
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return "$".join(
        [
            _ALGORITHM,
            str(_ITERATIONS),
            base64.b64encode(salt).decode(),
            base64.b64encode(derived).decode(),
        ]
    )


def verify_password(password: str, stored: str) -> bool:
    """Comprueba si `password` corresponde al hash `stored`. Nunca lanza error."""
    try:
        algorithm, iterations_text, salt_b64, hash_b64 = stored.split("$")
        if algorithm != _ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        return False

    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    # compare_digest evita filtrar información por el tiempo que tarda la comparación.
    return hmac.compare_digest(derived, expected)


# ---------------------------------------------------------------------------
# Clave secreta para firmar las cookies de sesión.
# Se guarda en un archivo local (.secret_key, ignorado por git). Si no existe,
# se crea con un valor aleatorio la primera vez que arranca la app.
# ---------------------------------------------------------------------------
_SECRET_KEY_FILE = Path(__file__).resolve().parent.parent / ".secret_key"


def get_secret_key() -> str:
    if _SECRET_KEY_FILE.exists():
        return _SECRET_KEY_FILE.read_text().strip()
    key = secrets.token_hex(32)
    _SECRET_KEY_FILE.write_text(key)
    return key
