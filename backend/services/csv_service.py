import os
import re
import csv as csv_module

def parse_float_es(s: str) -> float:
    """Parsea float con decimal europeo (coma → punto)."""
    return float(str(s).replace(',', '.').strip())

def extract_datetime_from_filename(filename: str):
    """Extrae 'DD-MM-YYYY HH-MM-SS' del nombre del archivo CSV."""
    m = re.search(r'(\d{2}-\d{2}-\d{4} \d{2}-\d{2}-\d{2})', filename)
    return m.group(1) if m else None

def extract_hand_from_filename(filename: str):
    if '_L_' in filename:
        return 'L'
    if '_R_' in filename:
        return 'R'
    return None

def csv_dt_to_iso(dt_str: str) -> str:
    """Convierte 'DD-MM-YYYY HH-MM-SS' (formato nombre de archivo) a 'YYYY-MM-DD HH:MM:SS'."""
    try:
        date_part, time_part = dt_str.split(' ')
        d, m, y = date_part.split('-')
        h, mi, s = time_part.split('-')
        return f"{y}-{m}-{d} {h}:{mi}:{s}"
    except Exception:
        return dt_str

def hand_label(hand) -> str:
    """Convierte código de mano (L/R/1/2/LEFT/RIGHT/lowercase) a etiqueta legible."""
    return {
        'R': 'Derecha', 2: 'Derecha', 'RIGHT': 'Derecha', 'right': 'Derecha',
        'L': 'Izquierda', 1: 'Izquierda', 'LEFT': 'Izquierda', 'left': 'Izquierda',
        'BOTH': 'Ambas', 'both': 'Ambas',
        'NONE': '—', 'none': '—',
    }.get(hand, str(hand))

def ruta_paciente_segura(base_dir: str, name: str):
    """
    Devuelve la ruta del directorio del paciente solo si queda DENTRO de base_dir.
    Previene path traversal (p.ej. name='../../etc'). None si la ruta se escapa.
    """
    candidato = os.path.join(base_dir, name)
    base = os.path.realpath(base_dir)
    full = os.path.realpath(candidato)
    if full == base or full.startswith(base + os.sep):
        return candidato
    return None

def iter_csv_files(base_dir: str, patient_name: str):
    """Genera (filename, datetime_str, hand) para cada CSV válido de un paciente."""
    patient_dir = ruta_paciente_segura(base_dir, patient_name)
    if not patient_dir or not os.path.isdir(patient_dir):
        return
    for filename in sorted(os.listdir(patient_dir)):
        if not filename.endswith('.csv'):
            continue
        dt   = extract_datetime_from_filename(filename)
        hand = extract_hand_from_filename(filename)
        if dt and hand:
            yield filename, dt, hand

def cargar_historic_bbt(hist_path: str) -> dict:
    """Carga BBT_Historic_.csv como dict indexado por datetime normalizado → O(1) lookup."""
    if not os.path.exists(hist_path):
        return {}
    index = {}
    with open(hist_path, 'r', encoding='utf-8') as f:
        reader = csv_module.DictReader(f, delimiter=';')
        for row in reader:
            fecha = row.get('Fecha', '').strip()
            if fecha:
                index[fecha] = dict(row)
    return index

def buscar_scores_historic(historic_index: dict, datetime_str: str) -> dict:
    """Convierte 'DD-MM-YYYY HH-MM-SS' → 'DD-MM-YYYY HH:MM:SS' y hace lookup O(1)."""
    parts = datetime_str.split(' ')
    if len(parts) == 2:
        key = f"{parts[0]} {parts[1].replace('-', ':')}"
        return historic_index.get(key, {})
    return {}

def extract_penalizaciones(hist_row: dict, hand: str) -> dict:
    """Extrae los scores de penalización del histórico para la mano indicada (L/R)."""
    if not hist_row:
        return {"completed": 0, "no_valid": 0, "out_of_zone": 0}
    prefix = 'L' if hand == 'L' else 'R'
    return {
        "completed":   int(hist_row.get(f'{prefix}_ValidCubes',   0) or 0),
        "no_valid":    int(hist_row.get(f'{prefix}_NoValidCubes', 0) or 0),
        "out_of_zone": int(hist_row.get(f'{prefix}_OutCubes',     0) or 0),
    }
