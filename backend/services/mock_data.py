import os
import json

_MOCK_PATH = os.path.join(os.path.dirname(__file__), "..", "trayectoria.json")


def cargar_json_mock():
    """Carga el JSON de trayectoria mock (fallback sin BD/CSV). None si no existe."""
    if not os.path.exists(_MOCK_PATH):
        return None
    with open(_MOCK_PATH, "r") as f:
        return json.load(f)
