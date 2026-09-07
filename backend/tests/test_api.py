"""Tests de endpoints vía TestClient (sin uvicorn).

No asumen que MySQL esté disponible: los endpoints SQL degradan a mock/CSV,
así que el contrato de respuesta debe cumplirse en ambos casos.
"""
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


# =============================================================================
# Navegación
# =============================================================================

def test_patients_responde_lista():
    r = client.get("/api/patients")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    assert isinstance(data["patients"], list)   # real o mock, pero lista


def test_csv_patients_responde():
    r = client.get("/api/csv/patients")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    assert isinstance(data["patients"], list)


def test_bbt_id_inexistente_nunca_500():
    # Con BD viva -> error explícito (nunca el mock: sería el dato de otro paciente);
    # sin BD -> fallback al JSON mock. En ambos casos 200 y contrato válido.
    r = client.get("/api/bbt/999999999")
    assert r.status_code == 200
    data = r.json()
    assert data.get("error") or (data["status"] == "success" and "x" in data and "metricas" in data)


# =============================================================================
# Integración CSV (usa los CSV reales de backend/Patients/)
# =============================================================================

def _primer_paciente_csv():
    data = client.get("/api/csv/patients").json()
    pacientes = data.get("patients", [])
    return pacientes[0]["name"] if pacientes else None


def test_csv_total_sessions_coincide_con_lista_de_sesiones():
    # El contador del directorio usa la misma agrupación (hora, modalidad)
    # que la vista de sesiones: no deben descuadrar.
    data = client.get("/api/csv/patients").json()
    if not data["patients"]:
        pytest.skip("No hay pacientes CSV")
    for p in data["patients"]:
        ses = client.get(f"/api/csv/patients/{p['name']}/sessions").json()["sessions"]
        assert p["total_sessions"] == len(ses), f"{p['name']}: {p['total_sessions']} != {len(ses)}"


def test_csv_sessions_de_paciente_real():
    name = _primer_paciente_csv()
    if not name:
        pytest.skip("No hay pacientes CSV en backend/Patients/")
    r = client.get(f"/api/csv/patients/{name}/sessions")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    assert data["patient"] == name
    assert isinstance(data["sessions"], list)


def test_csv_bbt_dashboard_de_fichero_real():
    name = _primer_paciente_csv()
    if not name:
        pytest.skip("No hay pacientes CSV")
    sesiones = client.get(f"/api/csv/patients/{name}/sessions").json()["sessions"]
    juego = next((g for s in sesiones for g in s["games"]), None)
    if not juego:
        pytest.skip("Paciente sin partidas BBT")

    p = juego["csv_params"]
    r = client.get("/api/csv/bbt", params={
        "patient": p["patient"], "modalidad": p["modalidad"],
        "hand": p["hand"], "datetime_str": p["datetime_str"],
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    assert data["source"] == "csv"
    # Trayectoria coherente: mismas longitudes en cada eje
    assert len(data["x"]) == len(data["y"]) == len(data["z"]) == len(data["timestamps"])
    assert "metricas" in data and "velocidades" in data


def test_csv_bbt_fichero_inexistente_devuelve_error():
    r = client.get("/api/csv/bbt", params={
        "patient": "NoExiste", "modalidad": "desktop",
        "hand": "R", "datetime_str": "01-01-2000 00-00-00",
    })
    assert r.status_code == 200
    assert "error" in r.json()


# =============================================================================
# Conversión BIT(1) de MySQL (pymysql devuelve bytes; bool(b'\x00') sería True)
# =============================================================================

def test_bit_a_bool_bytes_y_nativos():
    from database import bit_a_bool
    assert bit_a_bool(b"\x00") is False
    assert bit_a_bool(b"\x01") is True
    assert bit_a_bool(b"") is False
    assert bit_a_bool(0) is False
    assert bit_a_bool(1) is True
    assert bit_a_bool(None) is False
    assert bit_a_bool(True) is True


def test_bbt_evolution_responde_lista_o_error():
    # Con MySQL: sessions es lista; sin MySQL: error explícito (nunca
    # "0 sesiones" con status success, que ocultaría el fallo al clínico)
    r = client.get("/api/patients/1/bbt-evolution")
    assert r.status_code == 200
    data = r.json()
    assert "error" in data or isinstance(data["sessions"], list)
