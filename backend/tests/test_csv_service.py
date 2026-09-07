"""Tests del parseo de CSV BBT (funciones puras + fixtures de fichero temporal)."""
import os
from services.csv_service import (
    parse_float_es,
    extract_datetime_from_filename,
    extract_hand_from_filename,
    csv_dt_to_iso,
    hand_label,
    iter_csv_files,
    cargar_historic_bbt,
    buscar_scores_historic,
    extract_penalizaciones,
    ruta_paciente_segura,
)


# =============================================================================
# Parseo escalar
# =============================================================================

def test_parse_float_es_coma_decimal():
    assert parse_float_es("3,14") == 3.14
    assert parse_float_es("  -0,5 ") == -0.5
    assert parse_float_es("10") == 10.0


def test_extract_datetime_from_filename():
    f = "Trajectories_L_26-02-2026 12-32-49 _ Sesion 0.csv"
    assert extract_datetime_from_filename(f) == "26-02-2026 12-32-49"
    assert extract_datetime_from_filename("sin_fecha.csv") is None


def test_extract_hand_from_filename():
    assert extract_hand_from_filename("Trajectories_L_...csv") == "L"
    assert extract_hand_from_filename("Trajectories_R_...csv") == "R"
    assert extract_hand_from_filename("Trajectories_X_...csv") is None


def test_csv_dt_to_iso():
    assert csv_dt_to_iso("26-02-2026 12-32-49") == "2026-02-26 12:32:49"
    # entrada inesperada -> devuelve tal cual sin lanzar
    assert csv_dt_to_iso("loquesea") == "loquesea"


def test_hand_label_incluye_minusculas_y_none():
    assert hand_label("R") == "Derecha"
    assert hand_label("left") == "Izquierda"
    assert hand_label("both") == "Ambas"
    assert hand_label("none") == "—"
    assert hand_label(2) == "Derecha"


# =============================================================================
# Histórico de penalizaciones
# =============================================================================

def test_extract_penalizaciones_vacio():
    assert extract_penalizaciones({}, "R") == {
        "completed": 0, "no_valid": 0, "out_of_zone": 0
    }


def test_extract_penalizaciones_lee_columnas_correctas():
    row = {
        "R_ValidCubes": "12", "R_NoValidCubes": "2", "R_OutCubes": "1",
        "L_ValidCubes": "9",  "L_NoValidCubes": "0", "L_OutCubes": "3",
    }
    assert extract_penalizaciones(row, "R") == {"completed": 12, "no_valid": 2, "out_of_zone": 1}
    assert extract_penalizaciones(row, "L") == {"completed": 9, "no_valid": 0, "out_of_zone": 3}


def test_buscar_scores_historic_normaliza_separador():
    index = {"26-02-2026 12:32:49": {"R_ValidCubes": "5"}}
    # la clave de búsqueda viene con guiones en la hora
    assert buscar_scores_historic(index, "26-02-2026 12-32-49") == {"R_ValidCubes": "5"}
    assert buscar_scores_historic(index, "01-01-2000 00-00-00") == {}


# =============================================================================
# Lectura de ficheros (fixture temporal)
# =============================================================================

def test_iter_csv_files(tmp_path):
    pdir = tmp_path / "Paco"
    pdir.mkdir()
    (pdir / "Trajectories_R_26-02-2026 12-32-49 _ s.csv").write_text("x")
    (pdir / "Trajectories_L_26-02-2026 12-40-00 _ s.csv").write_text("x")
    (pdir / "notas.txt").write_text("ignorar")           # no .csv
    (pdir / "Trajectories_X_bad.csv").write_text("x")    # sin mano/fecha válida

    files = list(iter_csv_files(str(tmp_path), "Paco"))
    hands = sorted(h for _, _, h in files)
    assert hands == ["L", "R"]   # solo los 2 válidos


def test_iter_csv_files_paciente_inexistente(tmp_path):
    assert list(iter_csv_files(str(tmp_path), "NoExiste")) == []


def test_cargar_historic_bbt_indexa_por_fecha(tmp_path):
    hist = tmp_path / "BBT_Historic_.csv"
    hist.write_text(
        "Fecha;R_ValidCubes;L_ValidCubes\n"
        "26-02-2026 12:32:49;12;9\n",
        encoding="utf-8",
    )
    idx = cargar_historic_bbt(str(hist))
    assert "26-02-2026 12:32:49" in idx
    assert idx["26-02-2026 12:32:49"]["R_ValidCubes"] == "12"


def test_cargar_historic_bbt_fichero_ausente():
    assert cargar_historic_bbt("/ruta/que/no/existe.csv") == {}


# =============================================================================
# Seguridad: path traversal
# =============================================================================

def test_ruta_paciente_segura_nombre_normal(tmp_path):
    (tmp_path / "sim-nahuel").mkdir()
    ruta = ruta_paciente_segura(str(tmp_path), "sim-nahuel")
    assert ruta is not None
    assert ruta.endswith("sim-nahuel")


def test_ruta_paciente_segura_bloquea_traversal(tmp_path):
    base = tmp_path / "Patients"
    base.mkdir()
    # Intentos de escaparse del directorio base -> None
    assert ruta_paciente_segura(str(base), "../../etc") is None
    assert ruta_paciente_segura(str(base), "../secretos") is None
    assert ruta_paciente_segura(str(base), "sim-nahuel/../../..") is None


def test_iter_csv_files_ignora_traversal(tmp_path):
    # Un CSV fuera del base no debe alcanzarse vía '..'
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    (fuera / "Trajectories_R_26-02-2026 12-32-49 _ s.csv").write_text("x")
    base = tmp_path / "Patients"
    base.mkdir()
    assert list(iter_csv_files(str(base), "../fuera")) == []
