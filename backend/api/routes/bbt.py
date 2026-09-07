from fastapi import APIRouter
from sqlalchemy import text
from database import engine, bit_a_bool
from schemas import BBTReportResponse
from services.bbt_service import calcular_metricas_bbt, detectar_agarres_bbt, calcular_indice_fatiga, posiciones_agarre
from services.mock_data import cargar_json_mock as _cargar_json_mock

router = APIRouter()

def _bbt_from_mock_json():
    data = _cargar_json_mock()
    if not data:
        return {"error": "No se encontró trayectoria.json y no hay datos en SQL."}

    task_name = data.get("TaskName", "VABBT")
    is_vr = data.get("IsVr", False)
    time_limit = data.get("Time", 0.0)

    mano = data["Trajectories"][0]
    hand_type = mano["HandType"]

    penalizaciones = {"completed": 0, "no_valid": 0, "out_of_zone": 0}
    for sg in data.get("Scores", []):
        if sg.get("HandType") == hand_type:
            penalizaciones = {
                "completed": sg.get("Completed", 0),
                "no_valid": sg.get("NoValid", 0),
                "out_of_zone": sg.get("OutOfZone", 0),
            }
            break

    x, y, z, grasps, timestamps = [], [], [], [], []
    for i, coord in enumerate(mano["Coordinates"]):
        x.append(coord["PositionX"])
        y.append(coord["PositionY"])
        z.append(coord["PositionZ"])
        grasps.append(mano["LabelGrasps"][i])
        timestamps.append(mano["Timestamps"][i])

    scores_frame = mano.get("Scores", [])
    metricas = calcular_metricas_bbt(x, y, z, grasps, timestamps)

    return {
        "status": "success",
        "source": "mock_json",
        "game_type": "bbt",
        "task_name": task_name,
        "is_vr": is_vr,
        "time_limit": time_limit,
        "hand": hand_type,
        "patient": "Carlos García",
        "date": "2025-01-15",
        "x": x, "y": y, "z": z,
        "grasps": grasps,
        "timestamps": timestamps,
        "scores_por_frame": scores_frame,
        "penalizaciones": penalizaciones,
        "metricas": metricas["metricas"],
        "velocidades": metricas["velocidades"],
    }


@router.get("/api/patients/{user_id}/bbt-evolution")
def get_bbt_evolution(user_id: int):
    """
    Evolución BBT sesión a sesión desde SQL (penalizaciones por mano).
    Misma forma de respuesta que /api/csv/patients/{name}/evolution para
    reutilizar la vista y el gráfico de evolución del frontend.
    """
    try:
        query = text("""
            SELECT s.SessionID, s.Date, b.HandType,
                   sc.Completed, sc.NoValid, sc.OutOfZone
            FROM session s
            JOIN game_bbt b        ON b.SessionID = s.SessionID
            JOIN game_bbt_score sc ON sc.BBTRegisterID = b.BBTRegisterID
            WHERE s.UserID = :uid
            ORDER BY s.Date ASC, s.SessionID ASC, b.BBTRegisterID ASC
        """)
        with engine.connect() as conn:
            rows = conn.execute(query, {"uid": user_id}).mappings().all()

        vacio = {"completed": 0, "no_valid": 0, "out_of_zone": 0}
        sesiones: dict = {}
        orden = []
        for r in rows:
            sid = r["SessionID"]
            if sid not in sesiones:
                orden.append(sid)
                fecha = str(r["Date"])
                sesiones[sid] = {
                    "session_id": sid,
                    "date":       fecha[:10],
                    "datetime":   fecha[:19],
                    "left":       dict(vacio),
                    "right":      dict(vacio),
                }
            mano = str(r["HandType"]).lower()
            if mano in ("left", "right"):
                # si hay varias pruebas de la misma mano en la sesión, gana la última
                sesiones[sid][mano] = {
                    "completed":   int(r["Completed"] or 0),
                    "no_valid":    int(r["NoValid"] or 0),
                    "out_of_zone": int(r["OutOfZone"] or 0),
                }

        return {"status": "success", "user_id": user_id,
                "sessions": [sesiones[sid] for sid in orden]}
    except Exception as e:
        # Error explícito (como fruits-evolution): "0 sesiones" en silencio haría
        # creer al clínico que el paciente no tiene historia
        print(f"[DB ERROR] get_bbt_evolution(user_id={user_id}): {e}")
        return {"error": f"No se pudo cargar la evolución BBT: {e}"}


@router.get("/api/bbt/{register_id}", response_model=BBTReportResponse)
def get_bbt_report(register_id: int):
    """
    Devuelve TODOS los datos de una instancia BBT:
    - Metadatos (VR, mano, sesión)
    - Scores agregados (Completed, NoValid, OutOfZone)
    - Trayectoria completa (XYZ + grasps + timestamps + scores por frame)
    - Métricas biomecánicas calculadas en el servidor

    Si no hay datos en SQL, cae al JSON mock como fallback.
    """
    try:
        with engine.connect() as conn:
            main_query = text("""
                SELECT b.BBTRegisterID, b.IsVR, b.HandType, b.SessionID,
                       u.UserName, u.UserSurname1, s.Date
                FROM game_bbt b
                JOIN session s ON b.SessionID = s.SessionID
                JOIN user u ON s.UserID = u.UserID
                WHERE b.BBTRegisterID = :rid
            """)
            main_row = conn.execute(main_query, {"rid": register_id}).mappings().first()

            score_query = text("""
                SELECT Completed, NoValid, OutOfZone
                FROM game_bbt_score
                WHERE BBTRegisterID = :rid
            """)
            # Si hubiera varias filas de score para el registro, gana la última
            # (mismo criterio que get_bbt_evolution)
            score_rows = conn.execute(score_query, {"rid": register_id}).mappings().all()
            score_row  = score_rows[-1] if score_rows else None

            traj_query = text("""
                SELECT Score, LabelGrasp, Timestamp,
                       PositionX, PositionY, PositionZ
                FROM game_bbt_trajectory
                WHERE BBTRegisterID = :rid
                ORDER BY Timestamp ASC
            """)
            traj_rows = conn.execute(traj_query, {"rid": register_id}).mappings().all()

        # Con la BD viva, nunca caer al mock (mostraría datos de otro paciente):
        # registro inexistente o sin trayectoria → error explícito
        if not main_row:
            return {"error": f"No existe la prueba BBT {register_id}."}
        if not traj_rows:
            return {"error": f"La prueba BBT {register_id} no tiene trayectoria registrada."}

        x, y, z, grasps, timestamps, scores_frame = [], [], [], [], [], []
        for row in traj_rows:
            x.append(float(row["PositionX"]))
            y.append(float(row["PositionY"]))
            z.append(float(row["PositionZ"]))
            grasps.append(bit_a_bool(row["LabelGrasp"]))
            timestamps.append(float(row["Timestamp"]))
            scores_frame.append(int(row["Score"]))

        metricas       = calcular_metricas_bbt(x, y, z, grasps, timestamps)
        grasp_segments = detectar_agarres_bbt(grasps, metricas["velocidades"], timestamps)
        indice_fatiga  = calcular_indice_fatiga(grasp_segments)

        return {
            "status": "success",
            "game_type": "bbt",
            "task_name": "VABBT",
            "is_vr": bit_a_bool(main_row["IsVR"]),
            "hand": main_row["HandType"],
            "patient": f"{main_row['UserName']} {main_row['UserSurname1']}",
            "date": str(main_row["Date"]),
            "x": x, "y": y, "z": z,
            "grasps": grasps,
            "timestamps": timestamps,
            "scores_por_frame": scores_frame,
            "penalizaciones": {
                "completed": score_row["Completed"] if score_row else 0,
                "no_valid": score_row["NoValid"] if score_row else 0,
                "out_of_zone": score_row["OutOfZone"] if score_row else 0,
            },
            "metricas":       metricas["metricas"],
            "velocidades":    metricas["velocidades"],
            "grasp_segments": grasp_segments,
            "indice_fatiga":  indice_fatiga,
            "posiciones_objetos": posiciones_agarre(grasps, x, y, z),
        }
    except Exception as e:
        print(f"[DB ERROR] get_bbt_report(register_id={register_id}): {e}")

    # Fallback al JSON mock
    return _bbt_from_mock_json()
