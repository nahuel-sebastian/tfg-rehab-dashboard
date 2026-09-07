from fastapi import APIRouter
from sqlalchemy import text
from database import engine, bit_a_bool
from collections import defaultdict
import math
import statistics

router = APIRouter()


# =============================================================================
# Helpers compartidos por todos los modos Fruits
# =============================================================================
def _fruits_meta(conn, fid: int):
    """Metadatos comunes (modo, VR, paciente, fecha) de un game_fruits."""
    return conn.execute(text("""
        SELECT f.GameMode, f.IsVR, u.UserName, u.UserSurname1, s.Date
        FROM game_fruits f
        JOIN session s ON f.SessionID = s.SessionID
        JOIN user u    ON s.UserID    = u.UserID
        WHERE f.FruitsRegisterID = :fid
    """), {"fid": fid}).mappings().first()


def _times_between(conn, table: str, fk_col: str, rid: int):
    """Lista de TimeBetween para un registro de mano (tabla *_times)."""
    return [float(r["TimeBetween"]) for r in conn.execute(
        text(f"SELECT TimeBetween FROM {table} WHERE {fk_col} = :rid"), {"rid": rid}
    ).mappings().all()]


def _base_metricas(times, total_t: float, total_f: int) -> dict:
    """Bloque de métricas temporales común a todos los modos."""
    return {
        "total_frutas":      total_f,
        "tiempo_total_s":    total_t,
        "tiempo_medio_s":    round(sum(times) / len(times), 3) if times else 0.0,
        "tiempo_min_s":      round(min(times), 3) if times else 0.0,
        "tiempo_max_s":      round(max(times), 3) if times else 0.0,
        "frutas_por_minuto": round(total_f / (total_t / 60), 1) if total_t > 0 else 0.0,
        "std_dev_s":         round(statistics.stdev(times), 3) if len(times) > 1 else 0.0,
    }


def _envelope(game_type: str, fid: int, meta, hands: dict) -> dict:
    """Respuesta estándar de un dashboard Fruits."""
    return {
        "status":             "success",
        "game_type":          game_type,
        "fruits_register_id": fid,
        "game_mode":          meta["GameMode"],
        "is_vr":              bit_a_bool(meta["IsVR"]),
        "patient":            f"{meta['UserName']} {meta['UserSurname1']}",
        "date":               str(meta["Date"]),
        "hands":              hands,
    }


# =============================================================================
# FRUITS: Dashboard completo — todas las manos juntas (RIGHT / LEFT / BOTH)
# =============================================================================
@router.get("/api/fruits/{fruits_register_id}")
def get_fruits_report(fruits_register_id: int):
    try:
        with engine.connect() as conn:
            meta = _fruits_meta(conn, fruits_register_id)
            if not meta:
                return {"error": "Registro no encontrado"}

            hand_rows = conn.execute(text("""
                SELECT FruitsReachRegisterID, HandType, TotalFruits, Time
                FROM game_fruits_reach
                WHERE FruitsRegisterID = :fid
                ORDER BY HandType
            """), {"fid": fruits_register_id}).mappings().all()

            hands = {}
            for hr in hand_rows:
                times   = _times_between(conn, "game_fruits_reach_times", "FruitsReachRegisterID", hr["FruitsReachRegisterID"])
                total_t = float(hr["Time"])
                total_f = int(hr["TotalFruits"])
                hands[str(hr["HandType"]).upper()] = {
                    "total_fruits":  total_f,
                    "total_time":    total_t,
                    "times_between": times,
                    "metricas":      _base_metricas(times, total_t, total_f),
                }

            return _envelope("fruits", fruits_register_id, meta, hands)
    except Exception as e:
        print(f"[DB ERROR] get_fruits_report: {e}")
        return {"error": str(e)}


# =============================================================================
# FRUITS: Evolución temporal del paciente sesión a sesión
# =============================================================================
@router.get("/api/patients/{user_id}/fruits-evolution")
def get_fruits_evolution(user_id: int):
    try:
        with engine.connect() as conn:
            q = text("""
                SELECT s.SessionID, s.Date,
                       fr.HandType, fr.TotalFruits, fr.Time
                FROM session s
                JOIN game_fruits f        ON f.SessionID          = s.SessionID
                JOIN game_fruits_reach fr ON fr.FruitsRegisterID  = f.FruitsRegisterID
                WHERE s.UserID = :uid
                ORDER BY s.Date ASC, s.SessionID ASC, fr.HandType
            """)
            rows = conn.execute(q, {"uid": user_id}).mappings().all()

            sessions_map  = defaultdict(lambda: {"date": None, "RIGHT": [], "LEFT": [], "BOTH": [], "NONE": []})
            session_order = []

            for row in rows:
                sid = row["SessionID"]
                if sid not in session_order:
                    session_order.append(sid)
                    sessions_map[sid]["date"] = str(row["Date"])
                hand = str(row["HandType"]).upper()  # BD guarda lowercase
                if hand in ("RIGHT", "LEFT", "BOTH", "NONE"):
                    total_t = float(row["Time"])
                    total_f = int(row["TotalFruits"])
                    sessions_map[sid][hand].append({
                        "total_fruits":      total_f,
                        "total_time":        total_t,
                        "frutas_por_minuto": round(total_f / (total_t / 60), 1) if total_t > 0 else 0.0,
                    })

            sessions = []
            for sid in session_order:
                sm   = sessions_map[sid]
                entry = {"date": sm["date"], "session_id": sid}
                for hand in ("RIGHT", "LEFT", "BOTH", "NONE"):
                    data = sm[hand]
                    if data:
                        entry[hand] = {
                            "total_fruits":      round(sum(d["total_fruits"] for d in data) / len(data), 1),
                            "total_time":        round(sum(d["total_time"]   for d in data) / len(data), 2),
                            "frutas_por_minuto": round(sum(d["frutas_por_minuto"] for d in data) / len(data), 1),
                        }
                    else:
                        entry[hand] = None
                sessions.append(entry)

            return {"status": "success", "user_id": user_id, "sessions": sessions}
    except Exception as e:
        print(f"[DB ERROR] get_fruits_evolution: {e}")
        return {"error": str(e)}


# =============================================================================
# FRUITS: Secuencia
# =============================================================================
@router.get("/api/fruits-sequence/{fruits_register_id}")
def get_fruits_sequence_report(fruits_register_id: int):
    try:
        with engine.connect() as conn:
            meta = _fruits_meta(conn, fruits_register_id)
            if not meta:
                return {"error": "Registro no encontrado"}
            hand_rows = conn.execute(text("""
                SELECT FruitsSequenceRegisterID, HandType, TotalFruits, Time,
                       FruitsByCycle, FruitsFrequency
                FROM game_fruits_sequence
                WHERE FruitsRegisterID = :fid ORDER BY HandType
            """), {"fid": fruits_register_id}).mappings().all()
            hands = {}
            for hr in hand_rows:
                times   = _times_between(conn, "game_fruits_sequence_times", "FruitsSequenceRegisterID", hr["FruitsSequenceRegisterID"])
                total_t, total_f = float(hr["Time"]), int(hr["TotalFruits"])
                hands[str(hr["HandType"]).upper()] = {
                    "total_fruits":     total_f,
                    "total_time":       total_t,
                    "times_between":    times,
                    "fruits_by_cycle":  int(hr["FruitsByCycle"]),
                    "fruits_frequency": float(hr["FruitsFrequency"]),
                    "metricas":         _base_metricas(times, total_t, total_f),
                }
            return _envelope("fruits_sequence", fruits_register_id, meta, hands)
    except Exception as e:
        print(f"[DB ERROR] get_fruits_sequence_report: {e}")
        return {"error": str(e)}


# =============================================================================
# FRUITS: Agarre
# =============================================================================
@router.get("/api/fruits-grab/{fruits_register_id}")
def get_fruits_grab_report(fruits_register_id: int):
    try:
        with engine.connect() as conn:
            meta = _fruits_meta(conn, fruits_register_id)
            if not meta:
                return {"error": "Registro no encontrado"}
            hand_rows = conn.execute(text("""
                SELECT FruitsGrabRegisterID, HandType, TotalFruits, Time
                FROM game_fruits_grab
                WHERE FruitsRegisterID = :fid ORDER BY HandType
            """), {"fid": fruits_register_id}).mappings().all()
            hands = {}
            for hr in hand_rows:
                times   = _times_between(conn, "game_fruits_grab_times", "FruitsGrabRegisterID", hr["FruitsGrabRegisterID"])
                total_t, total_f = float(hr["Time"]), int(hr["TotalFruits"])
                hands[str(hr["HandType"]).upper()] = {
                    "total_fruits":  total_f,
                    "total_time":    total_t,
                    "times_between": times,
                    "metricas":      _base_metricas(times, total_t, total_f),
                }
            return _envelope("fruits_grab", fruits_register_id, meta, hands)
    except Exception as e:
        print(f"[DB ERROR] get_fruits_grab_report: {e}")
        return {"error": str(e)}


# =============================================================================
# FRUITS: Volteo (Flip)
# =============================================================================
@router.get("/api/fruits-flip/{fruits_register_id}")
def get_fruits_flip_report(fruits_register_id: int):
    try:
        with engine.connect() as conn:
            meta = _fruits_meta(conn, fruits_register_id)
            if not meta:
                return {"error": "Registro no encontrado"}
            hand_rows = conn.execute(text("""
                SELECT FruitsFlipRegisterID, HandType, TotalFruits, Time,
                       SupinationThreshold, PronationThreshold
                FROM game_fruits_flip
                WHERE FruitsRegisterID = :fid ORDER BY HandType
            """), {"fid": fruits_register_id}).mappings().all()
            hands = {}
            for hr in hand_rows:
                times   = _times_between(conn, "game_fruits_flip_times", "FruitsFlipRegisterID", hr["FruitsFlipRegisterID"])
                total_t, total_f = float(hr["Time"]), int(hr["TotalFruits"])
                hands[str(hr["HandType"]).upper()] = {
                    "total_fruits":         total_f,
                    "total_time":           total_t,
                    "times_between":        times,
                    "supination_threshold": float(hr["SupinationThreshold"]),
                    "pronation_threshold":  float(hr["PronationThreshold"]),
                    "metricas":             _base_metricas(times, total_t, total_f),
                }
            return _envelope("fruits_flip", fruits_register_id, meta, hands)
    except Exception as e:
        print(f"[DB ERROR] get_fruits_flip_report: {e}")
        return {"error": str(e)}


# =============================================================================
# FRUITS: Race
# =============================================================================
@router.get("/api/fruits-race/{fruits_register_id}")
def get_fruits_race_report(fruits_register_id: int):
    try:
        with engine.connect() as conn:
            meta = _fruits_meta(conn, fruits_register_id)
            if not meta:
                return {"error": "Registro no encontrado"}
            hand_rows = conn.execute(text("""
                SELECT FruitsRaceRegisterID, HandType, TotalFruits, FailedFruits,
                       Time, FruitSpeed, FruitsFrequency
                FROM game_fruits_race
                WHERE FruitsRegisterID = :fid ORDER BY HandType
            """), {"fid": fruits_register_id}).mappings().all()
            hands = {}
            for hr in hand_rows:
                rid     = hr["FruitsRaceRegisterID"]
                times   = _times_between(conn, "game_fruits_race_times", "FruitsRaceRegisterID", rid)
                action_states = [
                    {"is_correct": bit_a_bool(r["IsCorrect"]),
                     "fruit_pos": [float(r["FruitPositionX"]), float(r["FruitPositionY"]), float(r["FruitPositionZ"])],
                     "hand_pos":  [float(r["HandPositionX"]),  float(r["HandPositionY"]),  float(r["HandPositionZ"])]}
                    for r in conn.execute(
                        text("SELECT * FROM game_fruits_race_action_state WHERE FruitsRaceRegisterID = :rid ORDER BY ActionStateID"),
                        {"rid": rid}
                    ).mappings().all()
                ]
                total_t, total_f, failed = float(hr["Time"]), int(hr["TotalFruits"]), int(hr["FailedFruits"])
                metricas = _base_metricas(times, total_t, total_f)
                metricas["frutas_falladas"] = failed
                metricas["precision_pct"]   = round((total_f / (total_f + failed)) * 100, 1) if (total_f + failed) > 0 else 0.0
                # Dismetría: por cuántos cm falla la mano en cada evento fallado
                # (distancia mano↔fruta; marcador de ataxia/dismetría cerebelosa)
                errores_m = [math.dist(s["hand_pos"], s["fruit_pos"])
                             for s in action_states if not s["is_correct"]]
                if errores_m:
                    metricas["error_fallo_medio_cm"] = round(statistics.mean(errores_m) * 100, 1)
                    metricas["error_fallo_max_cm"]   = round(max(errores_m) * 100, 1)
                hands[str(hr["HandType"]).upper()] = {
                    "total_fruits":     total_f,
                    "failed_fruits":    failed,
                    "total_time":       total_t,
                    "fruit_speed":      float(hr["FruitSpeed"]),
                    "fruits_frequency": float(hr["FruitsFrequency"]),
                    "times_between":    times,
                    "action_states":    action_states,
                    "metricas":         metricas,
                }
            return _envelope("fruits_race", fruits_register_id, meta, hands)
    except Exception as e:
        print(f"[DB ERROR] get_fruits_race_report: {e}")
        return {"error": str(e)}
