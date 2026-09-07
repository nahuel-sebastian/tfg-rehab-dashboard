from fastapi import APIRouter
from sqlalchemy import text
from database import engine, bit_a_bool
from schemas import PatientsResponse, SessionsResponse, GamesResponse
from services.csv_service import hand_label as _hand_label
from services.mock_data import cargar_json_mock as _cargar_json_mock

router = APIRouter()

# Un juego Fruits "con datos" tiene filas en alguna subtabla de modo. Los registros
# vacíos no aparecen en /sessions/{id}/games, así que el directorio, la lista de
# sesiones y games_summary usan este MISMO predicado (si no, contador ≠ lista).
_FRUITS_CON_DATOS_SQL = """EXISTS (
                SELECT 1 FROM game_fruits f
                WHERE f.SessionID = s.SessionID
                  AND (
                      EXISTS (SELECT 1 FROM game_fruits_reach    fr  WHERE fr.FruitsRegisterID  = f.FruitsRegisterID)
                      OR EXISTS (SELECT 1 FROM game_fruits_sequence fs WHERE fs.FruitsRegisterID = f.FruitsRegisterID)
                      OR EXISTS (SELECT 1 FROM game_fruits_grab   fg  WHERE fg.FruitsRegisterID  = f.FruitsRegisterID)
                      OR EXISTS (SELECT 1 FROM game_fruits_flip   ff  WHERE ff.FruitsRegisterID  = f.FruitsRegisterID)
                      OR EXISTS (SELECT 1 FROM game_fruits_race   fr2 WHERE fr2.FruitsRegisterID = f.FruitsRegisterID)
                  )
            )"""


# =============================================================================
# NAVEGACIÓN: Pacientes
# =============================================================================
@router.get("/api/patients", response_model=PatientsResponse)
def get_patients():
    db_error = None
    try:
        query = text(f"""
            SELECT
                u.UserID,
                u.UserName,
                u.UserSurname1,
                u.UserSurname2,
                u.LeftHanded,
                COUNT(DISTINCT s.SessionID) AS total_sesiones,
                MAX(s.Date) AS ultima_sesion,
                MAX(EXISTS (SELECT 1 FROM game_bbt b2 WHERE b2.SessionID = s.SessionID)) AS has_bbt,
                MAX({_FRUITS_CON_DATOS_SQL}) AS has_fruits
            FROM user u
            JOIN session s ON u.UserID = s.UserID
            WHERE {_FRUITS_CON_DATOS_SQL} OR EXISTS (
                SELECT 1 FROM game_bbt b WHERE b.SessionID = s.SessionID
            )
            GROUP BY u.UserID, u.UserName, u.UserSurname1, u.UserSurname2, u.LeftHanded
            HAVING total_sesiones > 0
            ORDER BY u.UserID
        """)
        with engine.connect() as conn:
            rows = conn.execute(query).mappings().all()
            # BD accesible → devolver lo que haya, aunque sea lista vacía. NO caer al
            # mock aquí: un paciente ficticio ("Carlos García") se confundiría con dato
            # real (p.ej. si el seed no ha corrido y la demo parece tener un paciente).
            return {"status": "success", "patients": [dict(r) for r in rows]}
    except Exception as e:
        db_error = str(e)
        print(f"[DB ERROR] get_patients: {e}")

    # Fallback mock SOLO si la BD no es accesible (excepción arriba)
    return {
        "status": "success",
        "source": "mock",
        "db_error": db_error,
        "patients": [
            {
                "UserID": 1,
                "UserName": "Carlos",
                "UserSurname1": "García",
                "UserSurname2": "López",
                "LeftHanded": False,
                "total_sesiones": 1,
                "ultima_sesion": "2025-01-15 10:30:00",
            }
        ],
    }


# =============================================================================
# NAVEGACIÓN: Sesiones de un paciente
# =============================================================================
@router.get("/api/patients/{user_id}/sessions", response_model=SessionsResponse)
def get_patient_sessions(user_id: int):
    try:
        query = text(f"""
            SELECT
                s.SessionID,
                s.Date,
                u.UserName,
                u.UserSurname1,
                EXISTS (SELECT 1 FROM game_bbt b WHERE b.SessionID = s.SessionID) AS has_bbt,
                {_FRUITS_CON_DATOS_SQL} AS has_fruits
            FROM session s
            JOIN user u ON s.UserID = u.UserID
            WHERE s.UserID = :uid
              AND ({_FRUITS_CON_DATOS_SQL}
                  OR EXISTS (SELECT 1 FROM game_bbt b WHERE b.SessionID = s.SessionID)
              )
            ORDER BY s.Date DESC
        """)
        with engine.connect() as conn:
            rows = conn.execute(query, {"uid": user_id}).mappings().all()
            sessions = []
            for r in rows:
                row_dict = dict(r)
                games = []
                if row_dict.pop('has_bbt', False):
                    games.append('BBT')
                if row_dict.pop('has_fruits', False):
                    games.append('Fruits')
                row_dict['games_summary'] = games
                sessions.append(row_dict)
            return {
                "status": "success",
                "user_id": user_id,
                "user_name": f"{rows[0]['UserName']} {rows[0]['UserSurname1']}" if rows else "",
                "sessions": sessions,
            }
    except Exception as e:
        print(f"[DB ERROR] get_patient_sessions(user_id={user_id}): {e}")

    # Fallback mock
    return {
        "status": "success",
        "source": "mock",
        "user_id": user_id,
        "user_name": "Carlos García",
        "sessions": [{"SessionID": 100001, "Date": "2025-01-15 10:30:00"}],
    }


# =============================================================================
# NAVEGACIÓN: Juegos jugados en una sesión
# =============================================================================
_FRUITS_GAME_TYPES = {
    'reach':    ('fruits',          'game_fruits_reach',    'FruitsRegisterID'),
    'sequence': ('fruits_sequence', 'game_fruits_sequence', 'FruitsRegisterID'),
    'grab':     ('fruits_grab',     'game_fruits_grab',     'FruitsRegisterID'),
    'flip':     ('fruits_flip',     'game_fruits_flip',     'FruitsRegisterID'),
    'race':     ('fruits_race',     'game_fruits_race',     'FruitsRegisterID'),
}


@router.get("/api/sessions/{session_id}/games", response_model=GamesResponse)
def get_session_games(session_id: int):
    try:
        result_games = []
        with engine.connect() as conn:
            session_date_row = conn.execute(
                text("SELECT Date FROM session WHERE SessionID = :sid"), {"sid": session_id}
            ).fetchone()
            session_date = str(session_date_row[0]) if session_date_row else None

            # BBT
            for bbt in conn.execute(text("""
                SELECT b.BBTRegisterID, b.IsVR, b.HandType, g.GameName
                FROM game_bbt b
                LEFT JOIN game g ON b.GameID = g.GameID
                WHERE b.SessionID = :sid
            """), {"sid": session_id}).mappings().all():
                result_games.append({
                    "game_type":    "bbt",
                    "game_name":    bbt["GameName"] or "Box & Blocks Test",
                    "register_id":  bbt["BBTRegisterID"],
                    "is_vr":        bit_a_bool(bbt["IsVR"]),
                    "hand_type":    bbt["HandType"],
                    "hand_label":   _hand_label(bbt["HandType"]),
                    "session_date": session_date,
                })

            # Fruits — todos los modos directamente desde game_fruits
            for f_row in conn.execute(text("""
                SELECT f.FruitsRegisterID, f.GameMode, f.IsVR, g.GameName
                FROM game_fruits f
                LEFT JOIN game g ON f.GameID = g.GameID
                WHERE f.SessionID = :sid
                ORDER BY f.FruitsRegisterID
            """), {"sid": session_id}).mappings().all():
                mode = f_row["GameMode"]
                fid  = f_row["FruitsRegisterID"]
                if mode not in _FRUITS_GAME_TYPES:
                    continue
                game_type, sub_table, fk_col = _FRUITS_GAME_TYPES[mode]
                has_data = conn.execute(
                    text(f"SELECT 1 FROM {sub_table} WHERE {fk_col} = :fid LIMIT 1"),
                    {"fid": fid}
                ).fetchone()
                if not has_data:
                    continue
                result_games.append({
                    "game_type":    game_type,
                    "game_name":    f"{f_row['GameName'] or 'Fruits'} — {mode}",
                    "register_id":  fid,
                    "is_vr":        bit_a_bool(f_row["IsVR"]),
                    "game_mode":    mode,
                    "session_date": session_date,
                })

        return {"status": "success", "session_id": session_id, "games": result_games}

    except Exception as e:
        print(f"[DB ERROR] get_session_games(session_id={session_id}): {e}")

    # Fallback mock (solo si la BD no es accesible)
    data = _cargar_json_mock()
    if not data:
        return {"error": "No se encontró trayectoria.json"}

    mano = data["Trajectories"][0]
    return {
        "status": "success",
        "source": "mock",
        "session_id": session_id,
        "games": [
            {
                "game_type": "bbt",
                "game_name": data.get("TaskName", "Box & Blocks Test"),
                "register_id": 1,
                "is_vr": data.get("IsVr", False),
                "hand_type": mano["HandType"],
                "hand_label": "Derecha" if mano["HandType"] == 2 else "Izquierda",
            }
        ],
    }


