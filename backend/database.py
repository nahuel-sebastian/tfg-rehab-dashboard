import os
from sqlalchemy import create_engine

# Fallback para desarrollo local sin variables de entorno. No incrusta ninguna
# credencial: se toman de MYSQL_USER y MYSQL_PASSWORD, y si no están definidas la
# aplicación arranca igualmente y degrada al análisis de ficheros CSV.
_FALLBACK_URL = (
    f"mysql+pymysql://{os.getenv('MYSQL_USER', 'admin')}:"
    f"{os.getenv('MYSQL_PASSWORD', '')}@127.0.0.1:3307/"
    f"{os.getenv('MYSQL_DATABASE', 'main')}"
)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("[DB WARN] DATABASE_URL no definida — usando fallback dev local (127.0.0.1:3307)")
    DATABASE_URL = _FALLBACK_URL

# pool_pre_ping: descarta conexiones muertas (p.ej. tras reinicio de MySQL) antes de usarlas
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def bit_a_bool(v) -> bool:
    """Convierte un BIT(1) de MySQL a bool.

    pymysql devuelve BIT como bytes (b'\\x00'/b'\\x01') y bool(b'\\x00') es True
    (bytes no vacío), así que un bool(...) directo lee todos los bits como True.
    """
    if isinstance(v, (bytes, bytearray)):
        return bool(v[0]) if v else False
    return bool(v)
