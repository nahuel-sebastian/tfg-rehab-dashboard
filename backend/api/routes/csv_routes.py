from fastapi import APIRouter, Query
from schemas import CSVPatientsResponse, CSVSessionsResponse, CSVEvolutionResponse, BBTReportResponse
from config import _BBT_DESK_TRAJ, _BBT_VR_TRAJ, _BBT_DESK_HIST, _BBT_VR_HIST
from services.csv_service import iter_csv_files, hand_label, csv_dt_to_iso, cargar_historic_bbt, buscar_scores_historic, extract_penalizaciones, parse_float_es, ruta_paciente_segura
from services.bbt_service import calcular_metricas_bbt, detectar_agarres_bbt, calcular_indice_fatiga, posiciones_agarre
import os
import csv as csv_module

router = APIRouter()

@router.get("/api/csv/patients", response_model=CSVPatientsResponse)
def get_csv_patients():
    patients: dict = {}

    def _scan_dir(base_dir, modalidad):
        if not os.path.isdir(base_dir):
            return
        for name in sorted(os.listdir(base_dir)):
            if not os.path.isdir(os.path.join(base_dir, name)):
                continue
            if name not in patients:
                patients[name] = {"name": name, "has_desktop": False, "has_vr": False, "fechas": set()}
            patients[name][f"has_{modalidad}"] = True
            # sesión = grupo (hora, modalidad) — misma agrupación que /sessions
            # para que el contador del directorio coincida con la lista
            for _, dt, _ in iter_csv_files(base_dir, name):
                patients[name]["fechas"].add((csv_dt_to_iso(dt)[:13], modalidad))

    _scan_dir(_BBT_DESK_TRAJ, "desktop")
    _scan_dir(_BBT_VR_TRAJ,   "vr")

    result = [
        {"name": p["name"], "has_desktop": p["has_desktop"], "has_vr": p["has_vr"], "total_sessions": len(p["fechas"])}
        for p in patients.values()
    ]
    return {"status": "success", "patients": result}

@router.get("/api/csv/patients/{name}/sessions", response_model=CSVSessionsResponse)
def get_csv_patient_sessions(name: str):
    # Clave: (date_hour, modalidad) → sesiones distintas dentro del mismo día
    sessions: dict = {}

    def _add_files(base_dir, modalidad):
        game_name = "BBT Meta (VR)" if modalidad == "vr" else "BBT Desktop"
        for _, dt, hand in iter_csv_files(base_dir, name):
            dt_iso   = csv_dt_to_iso(dt)          # "YYYY-MM-DD HH:MM:SS"
            date_hour = dt_iso[:13]                 # "YYYY-MM-DD HH"  — agrupa por hora
            key = (date_hour, modalidad)
            if key not in sessions:
                sessions[key] = {"datetime_iso": dt_iso, "games": []}
            hl = hand_label(hand)
            sessions[key]["games"].append({
                "game_type":    "bbt",
                "game_name":    game_name,
                "modalidad":    modalidad,
                "hand":         hand,
                "hand_label":   hl,
                "is_vr":        modalidad == "vr",
                "datetime":     dt,
                "date":         dt_iso[:10],
                "session_date": dt_iso,
                "label":        f"{game_name} · {hl}",
                "register_id":  f"{name}|{modalidad}|{hand}|{dt}",
                "csv_params":   {"patient": name, "modalidad": modalidad, "hand": hand, "datetime_str": dt},
            })

    _add_files(_BBT_DESK_TRAJ, "desktop")
    _add_files(_BBT_VR_TRAJ,   "vr")

    result = []
    for (date_hour, modalidad) in sorted(sessions.keys(), reverse=True):
        entry      = sessions[(date_hour, modalidad)]
        games      = sorted(entry["games"], key=lambda g: g["hand"])
        game_label = "BBT Meta (VR)" if modalidad == "vr" else "BBT Desktop"
        result.append({
            "date":      entry["datetime_iso"],   # datetime completo en ISO para mostrar hora
            "modalidad": modalidad,
            "is_vr":     modalidad == "vr",
            "label":     game_label,
            "games":     games,
        })

    return {"status": "success", "patient": name, "sessions": result}

@router.get("/api/csv/patients/{name}/evolution", response_model=CSVEvolutionResponse)
def get_csv_patient_evolution(name: str, modalidad: str = "desktop"):
    base_dir  = _BBT_DESK_TRAJ if modalidad == "desktop" else _BBT_VR_TRAJ
    hist_path = _BBT_DESK_HIST if modalidad == "desktop" else _BBT_VR_HIST

    # Recoger datetimes únicos a partir de los ficheros de trayectoria
    seen: dict = {}  # datetime_str -> date "DD-MM-YYYY"
    for _, dt, _ in iter_csv_files(base_dir, name):
        if dt not in seen:
            seen[dt] = dt.split(' ')[0]

    if not seen:
        return {"status": "success", "patient": name, "modalidad": modalidad, "sessions": []}

    historic = cargar_historic_bbt(hist_path)

    def _parse_dt(dt_str: str):
        date_part, time_part = dt_str.split(' ')
        d, m, y = date_part.split('-')
        hh, mm, ss = time_part.split('-')
        return (int(y), int(m), int(d), int(hh), int(mm), int(ss))

    sessions = []
    for dt_str in sorted(seen.keys(), key=_parse_dt):
        hist_row = buscar_scores_historic(historic, dt_str)
        sessions.append({
            "date":     seen[dt_str],
            "datetime": dt_str,
            "left":     extract_penalizaciones(hist_row, 'L'),
            "right":    extract_penalizaciones(hist_row, 'R'),
        })

    return {"status": "success", "patient": name, "modalidad": modalidad, "sessions": sessions}

@router.get("/api/csv/bbt", response_model=BBTReportResponse)
def get_csv_bbt_report(
    patient: str      = Query(...),
    modalidad: str    = Query(...),
    hand: str         = Query(...),
    datetime_str: str = Query(...),
):
    base_dir    = _BBT_DESK_TRAJ if modalidad == "desktop" else _BBT_VR_TRAJ
    patient_dir = ruta_paciente_segura(base_dir, patient)

    if not patient_dir or not os.path.isdir(patient_dir):
        return {"error": f"Paciente '{patient}' no encontrado en {modalidad}"}

    # Buscar el CSV que coincide con mano y datetime
    target_file = None
    for f in os.listdir(patient_dir):
        if f'_{hand}_' in f and datetime_str in f and f.endswith('.csv'):
            target_file = os.path.join(patient_dir, f)
            break

    if not target_file:
        return {"error": f"CSV no encontrado para {patient} {modalidad} {hand} {datetime_str}"}

    # Parsear CSV
    x, y, z, grasps, timestamps, scores_frame = [], [], [], [], [], []
    with open(target_file, 'r', encoding='utf-8') as f:
        reader = csv_module.DictReader(f, delimiter=';')
        for row in reader:
            x.append(parse_float_es(row['X']))
            y.append(parse_float_es(row['Y']))
            z.append(parse_float_es(row['Z']))
            grasps.append(row['Grasping'].strip().lower() == 'true')
            timestamps.append(parse_float_es(row['Timestamp']))
            score_val = row.get('Score', '0').strip()
            scores_frame.append(int(score_val) if score_val.lstrip('-').isdigit() else 0)

    posiciones_objetos = posiciones_agarre(grasps, x, y, z)

    # Scores del histórico
    hist_path     = _BBT_DESK_HIST if modalidad == "desktop" else _BBT_VR_HIST
    historic      = cargar_historic_bbt(hist_path)
    hist_row      = buscar_scores_historic(historic, datetime_str)
    penalizaciones = extract_penalizaciones(hist_row, hand)

    metricas       = calcular_metricas_bbt(x, y, z, grasps, timestamps)
    grasp_segments = detectar_agarres_bbt(grasps, metricas["velocidades"], timestamps)

    return {
        "status":            "success",
        "source":            "csv",
        "game_type":         "bbt",
        "task_name":         "VABBT",
        "is_vr":             modalidad == "vr",
        "hand":              2 if hand == 'R' else 1,
        "patient":           patient,
        "date":              csv_dt_to_iso(datetime_str),  # solo display; el matching usa datetime_str
        "modalidad":         modalidad,
        "x": x, "y": y, "z": z,
        "grasps":            grasps,
        "timestamps":        timestamps,
        "scores_por_frame":  scores_frame,
        "posiciones_objetos": posiciones_objetos,
        "penalizaciones":    penalizaciones,
        "metricas":          metricas["metricas"],
        "velocidades":       metricas["velocidades"],
        "grasp_segments":    grasp_segments,
        "indice_fatiga":     calcular_indice_fatiga(grasp_segments),
    }
