#!/usr/bin/env python3
"""
Generador de pacientes sintéticos — TFG Dashboard HMI Rehabilitación
====================================================================
Crea pacientes ficticios en MySQL con patrones clínicos controlados
(fatiga, asimetría, tendencias de mejora/empeoramiento, patologías del
catálogo) para verificación funcional del dashboard y demos.

Los datos generados son 100% sintéticos. Los usuarios se marcan con
UserTag 'SIM-*' para poder identificarlos y borrarlos en bloque.

Modos de uso:
  python seed_synthetic_patients.py                       # wizard interactivo
  python seed_synthetic_patients.py --cuadro tendinitis --nombre Julián
  python seed_synthetic_patients.py --preset presets/julian.json
  python seed_synthetic_patients.py --all-presets         # siembra todos los presets (batch)
  python seed_synthetic_patients.py --clean --all-presets # limpia y re-siembra (idempotente)
  python seed_synthetic_patients.py --list                # catálogo
  python seed_synthetic_patients.py --clean               # borra todos los SIM-*
  ... añadir --dry-run / --dump-sql out.sql / --verify según necesidad

El modo --all-presets es el que usa el contenedor de seed del docker-compose:
idempotente (con --clean re-siembra determinista), resiliente (un preset malo no
tumba el resto) y sin --verify (la API puede no estar arriba todavía).

La receta de cada paciente (parámetros + seed) se guarda en
scripts/presets/<tag>.json → regenerable exacto con --preset.
"""

import argparse
import glob
import json
import math
import os
import random
import sys
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from urllib.parse import urlsplit, unquote

try:
    import pymysql
except ImportError:
    print("Falta pymysql. Actívalo con el venv del backend:")
    print("  source backend/venv/bin/activate && python scripts/seed_synthetic_patients.py")
    sys.exit(1)

HZ = 20                # frecuencia de muestreo de las trayectorias sintetizadas.
                       # OJO: los registros reales de la plataforma van a 5 Hz
                       # (medido sobre los 105 CSV de backend/Patients).
DT = 1.0 / HZ
DUR_MAX_S = 60.0       # duración máxima de una prueba BBT
API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")
PRESETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets")

# IDs del catálogo: se resuelven por NOMBRE contra la BD en _resolver_ids()
# (el baseline de Flyway puede renumerar); estos valores son solo el fallback.
IDS = {"fruits": 1, "bbt": 2, "hospital": 1}


def _resolver_ids(conn):
    """Resuelve GameID (por GameName) y HospitalID reales de la BD."""
    cur = conn.cursor()
    cur.execute("SELECT GameID, GameName FROM game")
    por_nombre = {str(nombre).strip().lower(): gid for gid, nombre in cur.fetchall()}
    for clave in ("fruits", "bbt"):
        if clave in por_nombre:
            IDS[clave] = por_nombre[clave]
        else:
            print(f"[WARN] Juego '{clave}' no está en la tabla game; uso GameID {IDS[clave]}")
    cur.execute("SELECT HospitalID FROM hospital ORDER BY HospitalID LIMIT 1")
    fila = cur.fetchone()
    if fila:
        IDS["hospital"] = fila[0]
    else:
        print(f"[WARN] Tabla hospital vacía; uso HospitalID {IDS['hospital']} (puede fallar por FK)")

# Zona de trabajo BBT (mesa): caja origen a la izquierda, destino a la derecha
PICK = (-0.20, 0.05, -0.35)
DROP = (0.20, 0.05, -0.35)
ALTURA_ARCO = 0.18     # el transporte pasa por encima del tabique central


# =============================================================================
# CATÁLOGO DE CUADROS CLÍNICOS
# Cada cuadro = overrides sobre los parámetros base. La "ficha clínica"
# narrativa se redacta en la memoria; aquí va la traducción a parámetros.
# =============================================================================
PARAMS_BASE = {
    # rendimiento
    "vel_base":        0.45,   # m/s velocidad media de la mano (sano ~0.4-0.5)
    "frutas_base_s":   1.8,    # s entre frutas en Fruits (sano)
    "variabilidad":    0.10,   # desviación relativa de tiempos (consistencia)
    # patrón intra-sesión
    "fatiga_pct":      0,      # % de caída de velocidad primeros→últimos agarres
    "pausa_prob":      0.0,    # prob. de pausa larga por ciclo (bloqueos → anomalías)
    "pausa_dur_s":     5.0,
    "soltar_prob":     0.0,    # prob. de soltar el cubo a mitad de transporte (NoValid)
    "fuera_zona_prob": 0.0,    # prob. de dejar el cubo fuera de zona (OutOfZone)
    # alteraciones del movimiento
    "temblor_amp":     0.0,    # amplitud del temblor (m)
    "temblor_hz":      5.0,    # frecuencia del temblor (Parkinson 4-6 Hz)
    "tope_y":          None,   # límite de elevación (tendinitis/hombro congelado)
    "overshoot":       0.0,    # dismetría: se pasa del objetivo y corrige (ataxia)
    "rigidez":         0.0,    # 0-1: aplana el perfil de velocidad (espasticidad)
    # lateralidad
    "mano_afectada":   "right",
    "asimetria_pct":   0,      # % de penalización de la mano afectada
    # race: zona espacial con más fallos ('izquierda'|'derecha'|'superior'|None)
    "race_fallo_zona": None,
    "race_fallo_base": 0.08,   # prob. base de fallo
    "race_fallo_zona_extra": 0.55,
    # sesiones
    "sesiones":        6,
    "espaciado_dias":  7,
    "tendencia":       "meseta",  # mejora | empeora | meseta | recaida | sierra
    "tendencia_pct":   6,         # % de cambio por sesión
    # qué generar
    "juegos":          ["bbt", "reach", "race"],
    "device":          "Desktop",
    "vr":              False,
}

CATALOGO = {
    "control": {
        "desc": "Control sano: rendimiento alto y estable, simétrico, sin fatiga.",
        "params": {},
    },
    "tendinitis": {
        "desc": "Tendinitis de hombro: elevación limitada, lentitud cerca del tope.",
        "params": {"tope_y": 0.22, "vel_base": 0.34, "asimetria_pct": 25,
                   "fatiga_pct": 12, "tendencia": "mejora", "tendencia_pct": 7,
                   "race_fallo_zona": "superior"},
    },
    "hombro_congelado": {
        "desc": "Capsulitis adhesiva: elevación muy limitada y rigidez global.",
        "params": {"tope_y": 0.15, "vel_base": 0.25, "rigidez": 0.5,
                   "asimetria_pct": 40, "race_fallo_zona": "superior",
                   "race_fallo_base": 0.15},
    },
    "parkinson": {
        "desc": "Temblor 4-6 Hz + bradicinesia: trayectoria rugosa, todo lento.",
        "params": {"temblor_amp": 0.012, "temblor_hz": 5.0, "vel_base": 0.22,
                   "variabilidad": 0.20, "frutas_base_s": 3.2,
                   "tendencia": "meseta"},
    },
    "ataxia": {
        "desc": "Ataxia cerebelosa: dismetría (se pasa del objetivo y corrige).",
        "params": {"overshoot": 0.30, "variabilidad": 0.28, "vel_base": 0.35,
                   "frutas_base_s": 2.8, "race_fallo_base": 0.20},
    },
    "espasticidad": {
        "desc": "Espasticidad post-ictus: movimiento lento y rígido, cuesta soltar.",
        "params": {"vel_base": 0.18, "rigidez": 0.7, "frutas_base_s": 4.0,
                   "asimetria_pct": 45, "soltar_prob": 0.08},
    },
    "heminegligencia": {
        "desc": "Negligencia espacial unilateral: ignora el hemicampo izquierdo.",
        "params": {"race_fallo_zona": "izquierda", "race_fallo_zona_extra": 0.75,
                   "vel_base": 0.38, "asimetria_pct": 15},
    },
    "debilidad_agarre": {
        "desc": "Debilidad de agarre (p.ej. túnel carpiano): se le caen los cubos.",
        "params": {"soltar_prob": 0.22, "fuera_zona_prob": 0.10, "vel_base": 0.38,
                   "frutas_base_s": 2.4, "asimetria_pct": 30},
    },
    "esclerosis_multiple": {
        "desc": "EM: fatiga intra-sesión marcada y días buenos/malos alternos.",
        "params": {"fatiga_pct": 30, "tendencia": "sierra", "tendencia_pct": 15,
                   "vel_base": 0.35, "frutas_base_s": 2.6},
    },
    "dolor_intermitente": {
        "desc": "Dolor intermitente: pausas largas aleatorias (bloqueos de score).",
        "params": {"pausa_prob": 0.18, "pausa_dur_s": 6.0, "vel_base": 0.38,
                   "variabilidad": 0.25},
    },
    "edad_avanzada": {
        "desc": "Deterioro por edad: lento pero consistente y simétrico.",
        "params": {"vel_base": 0.28, "frutas_base_s": 2.8, "variabilidad": 0.07},
    },
    "recuperacion": {
        "desc": "Recuperación post-ictus: mejora progresiva sesión a sesión.",
        "params": {"vel_base": 0.22, "frutas_base_s": 3.5, "asimetria_pct": 35,
                   "sesiones": 8, "tendencia": "mejora", "tendencia_pct": 9,
                   "fatiga_pct": 18},
    },
    "recaida": {
        "desc": "Recaída: mejora inicial y empeoramiento en las últimas sesiones.",
        "params": {"vel_base": 0.30, "frutas_base_s": 2.8, "asimetria_pct": 25,
                   "sesiones": 7, "tendencia": "recaida", "tendencia_pct": 8},
    },
    "fatigabilidad": {
        "desc": "Fatigabilidad: caída clara de velocidad dentro de cada sesión.",
        "params": {"fatiga_pct": 28, "vel_base": 0.40, "frutas_base_s": 2.0},
    },
}

NOMBRES_AUTO = ["Julián", "Carmen", "Andrés", "Lucía", "Tomás", "Elena",
                "Ricardo", "Nuria", "Sergio", "Pilar", "Óscar", "Teresa", "Iván"]


# =============================================================================
# UTILIDADES
# =============================================================================
def _smoothstep(s: float) -> float:
    """Perfil de velocidad en campana (mínimo jerk aproximado)."""
    return s * s * (3 - 2 * s)


def _factor_sesion(tendencia: str, pct: float, i: int, n: int, rng) -> float:
    """Multiplicador de rendimiento de la sesión i (0-based). >1 = mejor."""
    ruido = rng.uniform(-0.03, 0.03)
    p = pct / 100.0
    if tendencia == "mejora":
        return 1.0 + p * i + ruido
    if tendencia == "empeora":
        return max(0.3, 1.0 - p * i + ruido)
    if tendencia == "recaida":
        pico = max(1, int(n * 0.6))
        if i <= pico:
            return 1.0 + p * i + ruido
        return max(0.3, 1.0 + p * pico - p * 1.6 * (i - pico) + ruido)
    if tendencia == "sierra":
        return 1.0 + (p if i % 2 == 0 else -p) + ruido
    return 1.0 + ruido  # meseta


def _conexion(db_url: str | None):
    """Abre conexión pymysql desde DATABASE_URL o el fallback dev local."""
    url = db_url or os.environ.get(
        "DATABASE_URL",
        "mysql+pymysql://admin:your_secure_password_here@127.0.0.1:3307/main")
    # urlsplit en vez de regex: soporta puertos ausentes y credenciales con
    # caracteres especiales percent-encoded (igual que SQLAlchemy)
    u = urlsplit(url)
    if not u.scheme.startswith("mysql") or not u.hostname or not u.username:
        sys.exit(f"DATABASE_URL no reconocida: {url}")
    return pymysql.connect(host=u.hostname, port=u.port or 3306,
                           user=unquote(u.username),
                           password=unquote(u.password or ""),
                           database=u.path.lstrip("/") or "main",
                           charset="utf8mb4", autocommit=False)


# =============================================================================
# GENERADOR DE TRAYECTORIAS BBT
# =============================================================================
def generar_trayectoria_bbt(p: dict, rng: random.Random, factor: float, mano: str):
    """
    Genera una prueba BBT completa para una mano.
    Devuelve (frames, completed, no_valid, out_of_zone) donde frames es una
    lista de tuplas (t, x, y, z, grasp, score, qx, qy, qz, qw, nx, ny, nz).
    """
    afectada = (mano == p["mano_afectada"])
    asim = (p["asimetria_pct"] / 100.0) if afectada else 0.0

    vel = max(0.08, p["vel_base"] * factor * (1 - asim))
    temblor_amp = p["temblor_amp"] * (1.5 if afectada else 0.6)
    tope_y = p["tope_y"] if (p["tope_y"] is not None and afectada) else None
    overshoot = p["overshoot"] * (1.0 if afectada else 0.3)

    frames = []
    t = 0.0
    score = 0
    no_valid = 0
    out_of_zone = 0
    ciclo = 0
    pos = list(DROP)
    fase_temblor = rng.uniform(0, 2 * math.pi)

    def _punto(base, dispersion=0.04):
        return [base[0] + rng.uniform(-dispersion, dispersion),
                base[1] + rng.uniform(-0.01, dispersion),
                base[2] + rng.uniform(-dispersion, dispersion)]

    def _emite(x, y, z, grasp):
        nonlocal t
        # temblor oscilatorio + ruido de medida
        tx = temblor_amp * math.sin(2 * math.pi * p["temblor_hz"] * t + fase_temblor)
        ty = temblor_amp * 0.7 * math.sin(2 * math.pi * p["temblor_hz"] * t * 1.1)
        x += tx + rng.gauss(0, 0.0015)
        y += ty + rng.gauss(0, 0.0015)
        z += rng.gauss(0, 0.0015)
        if tope_y is not None:
            y = min(y, tope_y + rng.gauss(0, 0.004))
        # orientación plausible: rotación pequeña alrededor de identidad
        qx, qy, qz = rng.gauss(0, 0.05), rng.gauss(0, 0.05), rng.gauss(0, 0.05)
        qw = math.sqrt(max(0.0, 1 - qx * qx - qy * qy - qz * qz))
        nx, ny, nz = rng.gauss(0, 0.1), 1.0, rng.gauss(0, 0.1)
        nn = math.sqrt(nx * nx + ny * ny + nz * nz)
        frames.append((round(t, 5), round(x, 5), round(y, 5), round(z, 5),
                       grasp, score,
                       round(qx, 5), round(qy, 5), round(qz, 5), round(qw, 5),
                       round(nx / nn, 5), round(ny / nn, 5), round(nz / nn, 5)))
        t += DT

    def _segmento(a, b, grasp, fat_mult, abortar_en=None):
        """Mueve la mano de a a b con arco vertical. abortar_en ∈ (0,1) corta el segmento."""
        dist = math.dist(a, b) * 1.35  # el arco alarga el camino
        dur = max(0.3, dist / max(0.05, vel / fat_mult))
        if p["rigidez"] > 0:
            dur *= 1 + p["rigidez"] * 0.5
        n = max(4, int(dur * HZ))
        cima = tope_y if tope_y is not None else (max(a[1], b[1]) + ALTURA_ARCO)
        fin = 1.0 if abortar_en is None else abortar_en
        i = 0
        while i / n < fin:
            i += 1
            s_lin = min(1.0, i / n)
            s = s_lin if p["rigidez"] > 0.4 else _smoothstep(s_lin)  # rígido = perfil plano
            x = a[0] + (b[0] - a[0]) * s
            z = a[2] + (b[2] - a[2]) * s
            y = a[1] + (b[1] - a[1]) * s + math.sin(s * math.pi) * (cima - max(a[1], b[1]))
            _emite(x, y, z, grasp)
        # dismetría: pasarse del objetivo y corregir oscilando
        if abortar_en is None and overshoot > 0:
            exceso = overshoot * (0.6 + rng.random() * 0.8)
            for k in range(int(HZ * 0.5)):
                sk = k / (HZ * 0.5)
                amplitud = exceso * (1 - sk) * math.cos(sk * math.pi * 2)
                _emite(b[0] + (b[0] - a[0]) * 0.18 * amplitud,
                       b[1] + 0.04 * amplitud, b[2], grasp)
        return [frames[-1][1], frames[-1][2], frames[-1][3]]

    def _pausa(dur, grasp):
        base = [frames[-1][1], frames[-1][2], frames[-1][3]] if frames else pos
        for _ in range(int(dur * HZ)):
            _emite(base[0], base[1], base[2], grasp)

    _emite(*pos, False)
    while t < DUR_MAX_S:
        ciclo += 1
        # la fatiga alarga los ciclos progresivamente (ramp hasta el ciclo ~12)
        fat_mult = 1 + (p["fatiga_pct"] / 100.0) * min(1.0, ciclo / 12.0)

        # ALCANCE: ir a por el cubo (mano vacía)
        objetivo = _punto(PICK)
        pos = _segmento(pos, objetivo, False, fat_mult)
        if t >= DUR_MAX_S:
            break

        if rng.random() < p["pausa_prob"]:
            _pausa(p["pausa_dur_s"] * rng.uniform(0.7, 1.3), False)

        # TRANSPORTE: llevar el cubo (agarrado)
        destino = _punto(DROP)
        r = rng.random()
        if r < p["soltar_prob"]:
            # se le cae a mitad de camino → no puntúa
            pos = _segmento(pos, destino, True, fat_mult,
                            abortar_en=rng.uniform(0.3, 0.7))
            no_valid += 1
        elif r < p["soltar_prob"] + p["fuera_zona_prob"]:
            # lo deja fuera de la zona válida
            fuera = [destino[0] + rng.uniform(0.10, 0.18), destino[1],
                     destino[2] + rng.uniform(-0.15, 0.15)]
            pos = _segmento(pos, fuera, True, fat_mult)
            out_of_zone += 1
        else:
            pos = _segmento(pos, destino, True, fat_mult)
            score += 1

    return frames, score, no_valid, out_of_zone


# =============================================================================
# GENERADOR FRUITS
# =============================================================================
def generar_tiempos_fruits(p: dict, rng: random.Random, factor: float, mano: str,
                           n_frutas: int = 14):
    """Serie de tiempos entre frutas para una mano. Devuelve lista de floats."""
    afectada = (mano == p["mano_afectada"])
    asim = (p["asimetria_pct"] / 100.0) if afectada else 0.0
    base = p["frutas_base_s"] / max(0.3, factor) * (1 + asim)
    tiempos = []
    for i in range(n_frutas):
        fat = 1 + (p["fatiga_pct"] / 100.0) * (i / max(1, n_frutas - 1))
        v = rng.gauss(base * fat, base * p["variabilidad"])
        tiempos.append(round(max(0.4, v), 3))
    return tiempos


def generar_race(p: dict, rng: random.Random, factor: float, mano: str):
    """Genera action_states de Race con patrón espacial de fallos."""
    afectada = (mano == p["mano_afectada"])
    n_acciones = max(8, int(16 * min(1.4, factor)))
    states = []
    aciertos = 0
    for _ in range(n_acciones):
        fx = rng.uniform(-0.5, 0.5)
        fy = rng.uniform(0.9, 1.7)
        fz = rng.uniform(-0.1, 0.1)
        prob_fallo = p["race_fallo_base"] * (1.6 if afectada else 1.0)
        zona = p["race_fallo_zona"]
        if zona and afectada:
            en_zona = ((zona == "izquierda" and fx < -0.08)
                       or (zona == "derecha" and fx > 0.08)
                       or (zona == "superior" and fy > 1.35))
            if en_zona:
                prob_fallo += p["race_fallo_zona_extra"]
        correcto = rng.random() > min(0.95, prob_fallo)
        if correcto:
            hx, hy, hz = fx + rng.gauss(0, 0.02), fy + rng.gauss(0, 0.02), fz
            aciertos += 1
        else:
            # la mano no llega: se queda corta hacia el centro/abajo
            hx = fx * rng.uniform(0.3, 0.7)
            hy = fy - rng.uniform(0.15, 0.40)
            hz = fz
        states.append((correcto, round(fx, 4), round(fy, 4), round(fz, 4),
                       round(hx, 4), round(hy, 4), round(hz, 4)))
    return states, aciertos, n_acciones - aciertos


# =============================================================================
# INSERCIÓN EN MYSQL
# =============================================================================
class Insertor:
    """Encapsula los INSERTs; si dump_path está definido, también vuelca SQL."""

    def __init__(self, conn, dump_path=None, dry_run=False):
        self.conn = conn
        self.cur = conn.cursor()
        self.dry = dry_run
        self.dump = open(dump_path, "w", encoding="utf-8") if dump_path else None
        if self.dump:
            self.dump.write("-- Pacientes sintéticos generados por seed_synthetic_patients.py\n"
                            "-- Datos 100% inventados (verificación funcional del dashboard)\n\n")

    def _vuelca(self, sql, args):
        if self.dump:
            self.dump.write(self.cur.mogrify(sql, args) + ";\n")

    def uno(self, sql, args):
        self.cur.execute(sql, args)
        self._vuelca(sql, args)
        return self.cur.lastrowid

    def muchos(self, sql, lista):
        self.cur.executemany(sql, lista)
        if self.dump:
            for args in lista:
                self.dump.write(self.cur.mogrify(sql, args) + ";\n")

    def cierra(self, ok=True):
        if self.dry or not ok:
            self.conn.rollback()
        else:
            self.conn.commit()
        if self.dump:
            self.dump.close()


class TagExistente(Exception):
    """El paciente (UserTag) ya está en la BD. Permite al modo batch saltarlo
    en vez de abortar todo el seed."""


def insertar_paciente(ins: Insertor, receta: dict):
    """Genera e inserta el paciente completo. Devuelve resumen con IDs y esperados.

    Lanza TagExistente si el UserTag ya está en la BD (el llamador decide si aborta
    —modo directo— o lo salta —modo batch/contenedor—)."""
    p = dict(PARAMS_BASE)
    p.update(CATALOGO[receta["cuadro"]]["params"])
    p.update(receta.get("overrides", {}))
    rng = random.Random(receta["seed"])

    ins.cur.execute("SELECT UserID FROM user WHERE UserTag = %s", (receta["tag"],))
    existente = ins.cur.fetchone()
    if existente:
        raise TagExistente(
            f"Ya existe un paciente con tag {receta['tag']} (UserID {existente[0]}).")

    zurdo = 1 if rng.random() < 0.10 else 0  # ~10% de zurdos, determinista por seed
    uid = ins.uno(
        "INSERT INTO user (UserTag, UserName, UserSurname1, UserSurname2, "
        "LeftHanded, IsActive, HospitalID, AffectedSide, SkinTone) "
        "VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s)",
        (receta["tag"], receta["nombre"], receta["apellido"], "Sintético",
         zurdo, IDS["hospital"], 2 if p["mano_afectada"] == "right" else 1,
         rng.randint(1, 5)))

    n = p["sesiones"]
    inicio = datetime.now() - timedelta(days=p["espaciado_dias"] * (n - 1))
    resumen = {"user_id": uid, "tag": receta["tag"], "nombre": receta["nombre"],
               "cuadro": receta["cuadro"], "sesiones": [], "params": p}

    for i in range(n):
        factor = _factor_sesion(p["tendencia"], p["tendencia_pct"], i, n, rng)
        fecha = (inicio + timedelta(days=p["espaciado_dias"] * i)).replace(
            hour=rng.randint(9, 18), minute=rng.randint(0, 59), second=0, microsecond=0)
        sid = ins.uno(
            "INSERT INTO session (Date, UserID, Device, Guid) VALUES (%s, %s, %s, %s)",
            (fecha.strftime("%Y-%m-%d %H:%M:%S"), uid, p["device"], str(uuid.uuid4())))
        ses = {"session_id": sid, "fecha": fecha.strftime("%Y-%m-%d %H:%M"),
               "factor": round(factor, 3), "bbt": {}, "fruits": {}}

        # ---- BBT: una prueba por mano -------------------------------------
        if "bbt" in p["juegos"]:
            for mano in ("right", "left"):
                frames, comp, noval, fuera = generar_trayectoria_bbt(p, rng, factor, mano)
                rid = ins.uno(
                    "INSERT INTO game_bbt (IsVR, HandType, TaskName, SessionID, GameID, Date) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (1 if p["vr"] else 0, mano, "VABBT", sid, IDS["bbt"],
                     fecha.strftime("%Y-%m-%d %H:%M:%S")))
                ins.uno(
                    "INSERT INTO game_bbt_score (Completed, NoValid, OutOfZone, BBTRegisterID) "
                    "VALUES (%s, %s, %s, %s)", (comp, noval, fuera, rid))
                ins.muchos(
                    "INSERT INTO game_bbt_trajectory (Score, LabelGrasp, Timestamp, "
                    "PositionX, PositionY, PositionZ, RotationX, RotationY, RotationZ, "
                    "RotationW, NormalX, NormalY, NormalZ, BBTRegisterID) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    [(f[5], 1 if f[4] else 0, f[0], f[1], f[2], f[3],
                      f[6], f[7], f[8], f[9], f[10], f[11], f[12], rid)
                     for f in frames])
                ses["bbt"][mano] = {"register_id": rid, "completed": comp,
                                    "no_valid": noval, "out_of_zone": fuera,
                                    "frames": len(frames)}

        # ---- Fruits: cabecera por modo, detalle por mano -------------------
        modos_simples = [m for m in p["juegos"] if m in ("reach", "grab", "sequence", "flip")]
        for modo in modos_simples:
            fid = ins.uno(
                "INSERT INTO game_fruits (GameMode, SessionID, GameID, IsVR, Date) "
                "VALUES (%s, %s, %s, %s, %s)",
                (modo, sid, IDS["fruits"], 1 if p["vr"] else 0,
                 fecha.strftime("%Y-%m-%d %H:%M:%S")))
            ses["fruits"][modo] = {"fruits_register_id": fid, "hands": {}}
            for mano in ("right", "left"):
                tiempos = generar_tiempos_fruits(p, rng, factor, mano)
                total_t = round(sum(tiempos) + rng.uniform(0.5, 2.0), 3)
                total_f = len(tiempos)
                tabla = {"reach": ("game_fruits_reach", "FruitsReachRegisterID"),
                         "grab": ("game_fruits_grab", "FruitsGrabRegisterID"),
                         "sequence": ("game_fruits_sequence", "FruitsSequenceRegisterID"),
                         "flip": ("game_fruits_flip", "FruitsFlipRegisterID")}[modo]
                if modo == "sequence":
                    hid = ins.uno(
                        f"INSERT INTO {tabla[0]} (HandType, TotalFruits, Time, "
                        "FruitsByCycle, FruitsFrequency, FruitsRegisterID) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (mano, total_f, total_t, 3,
                         round(total_f / (total_t / 60), 3), fid))
                elif modo == "flip":
                    hid = ins.uno(
                        f"INSERT INTO {tabla[0]} (HandType, TotalFruits, Time, "
                        "SupinationThreshold, PronationThreshold, FruitsRegisterID) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (mano, total_f, total_t, 45.0, 45.0, fid))
                else:
                    hid = ins.uno(
                        f"INSERT INTO {tabla[0]} (HandType, TotalFruits, Time, FruitsRegisterID) "
                        "VALUES (%s, %s, %s, %s)", (mano, total_f, total_t, fid))
                ins.muchos(
                    f"INSERT INTO {tabla[0]}_times (TimeBetween, {tabla[1]}) VALUES (%s, %s)",
                    [(tb, hid) for tb in tiempos])
                ses["fruits"][modo]["hands"][mano] = {
                    "total": total_f, "time": total_t,
                    "fpm": round(total_f / (total_t / 60), 1)}

        if "race" in p["juegos"]:
            fid = ins.uno(
                "INSERT INTO game_fruits (GameMode, SessionID, GameID, IsVR, Date) "
                "VALUES (%s, %s, %s, %s, %s)",
                ("race", sid, IDS["fruits"], 1 if p["vr"] else 0,
                 fecha.strftime("%Y-%m-%d %H:%M:%S")))
            ses["fruits"]["race"] = {"fruits_register_id": fid, "hands": {}}
            for mano in ("right", "left"):
                states, ok_n, fail_n = generar_race(p, rng, factor, mano)
                tiempos = generar_tiempos_fruits(p, rng, factor, mano, n_frutas=max(2, ok_n))
                total_t = round(sum(tiempos) + rng.uniform(0.5, 2.0), 3)
                rrid = ins.uno(
                    "INSERT INTO game_fruits_race (HandType, TotalFruits, FailedFruits, "
                    "Time, FruitSpeed, FruitsFrequency, FruitsRegisterID) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (mano, ok_n, fail_n, total_t, round(rng.uniform(0.8, 1.4), 3),
                     round(ok_n / (total_t / 60), 3), fid))
                ins.muchos(
                    "INSERT INTO game_fruits_race_times (TimeBetween, FruitsRaceRegisterID) "
                    "VALUES (%s, %s)", [(tb, rrid) for tb in tiempos])
                ins.muchos(
                    "INSERT INTO game_fruits_race_action_state (IsCorrect, "
                    "FruitPositionX, FruitPositionY, FruitPositionZ, "
                    "HandPositionX, HandPositionY, HandPositionZ, FruitsRaceRegisterID) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    [(1 if s[0] else 0, s[1], s[2], s[3], s[4], s[5], s[6], rrid)
                     for s in states])
                ses["fruits"]["race"]["hands"][mano] = {
                    "ok": ok_n, "fail": fail_n,
                    "precision": round(ok_n / (ok_n + fail_n) * 100, 1)}

        resumen["sesiones"].append(ses)
    return resumen


def sembrar_todos(conn, clean_first=False, dry_run=False):
    """Siembra TODOS los presets de PRESETS_DIR (modo batch / contenedor de seed).

    Idempotente y resiliente:
      - clean_first: borra los SIM-* antes → re-siembra determinista (seeds fijas en
        los presets). Es la vía recomendada para el contenedor en cada arranque.
      - sin clean_first: salta los presets cuyo tag ya exista (no duplica).
      - cada preset va en su propia transacción → un preset ilegible o con error no
        arrastra a los demás.
    Devuelve True si no hubo fallos duros (presets ilegibles / errores de inserción).
    """
    if clean_first and not dry_run:
        limpiar_sinteticos(conn)

    rutas = sorted(glob.glob(os.path.join(PRESETS_DIR, "*.json")))
    if not rutas:
        print(f"No hay presets en {PRESETS_DIR}")
        return True

    print(f"Sembrando {len(rutas)} preset(s) de {os.path.relpath(PRESETS_DIR)}...")
    creados = saltados = fallidos = 0
    for ruta in rutas:
        fichero = os.path.basename(ruta)
        try:
            with open(ruta, encoding="utf-8") as f:
                receta = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"  ✗ {fichero}: preset ilegible ({e})")
            fallidos += 1
            continue

        # Transacción propia por preset: un fallo hace rollback solo de ese paciente
        ins = Insertor(conn, dry_run=dry_run)
        try:
            resumen = insertar_paciente(ins, receta)
            ins.cierra(ok=True)
            creados += 1
            print(f"  ✓ {receta['tag']} ({receta['cuadro']}) — UserID {resumen['user_id']}, "
                  f"{len(resumen['sesiones'])} sesiones")
        except TagExistente:
            ins.cierra(ok=False)
            saltados += 1
            print(f"  = {receta.get('tag', fichero)}: ya existe, saltado")
        except Exception as e:  # cuadro desconocido, error SQL, etc.
            ins.cierra(ok=False)
            fallidos += 1
            print(f"  ✗ {receta.get('tag', fichero)}: error ({e})")

    print(f"\nSeed batch: {creados} creado(s), {saltados} saltado(s), {fallidos} fallido(s).")
    return fallidos == 0


def limpiar_sinteticos(conn):
    """Borra todos los usuarios SIM-* y sus datos en cascada manual."""
    cur = conn.cursor()
    cur.execute("SELECT UserID, UserTag FROM user WHERE UserTag LIKE 'SIM-%%'")
    usuarios = cur.fetchall()
    if not usuarios:
        print("No hay pacientes sintéticos (SIM-*) en la BD.")
        return
    for uid, tag in usuarios:
        cur.execute("SELECT SessionID FROM session WHERE UserID = %s", (uid,))
        sids = [r[0] for r in cur.fetchall()]
        for sid in sids:
            cur.execute("SELECT BBTRegisterID FROM game_bbt WHERE SessionID = %s", (sid,))
            for (rid,) in cur.fetchall():
                cur.execute("DELETE FROM game_bbt_trajectory WHERE BBTRegisterID = %s", (rid,))
                cur.execute("DELETE FROM game_bbt_score WHERE BBTRegisterID = %s", (rid,))
            cur.execute("DELETE FROM game_bbt WHERE SessionID = %s", (sid,))
            cur.execute("SELECT FruitsRegisterID FROM game_fruits WHERE SessionID = %s", (sid,))
            for (fid,) in cur.fetchall():
                for tabla, pk in [("game_fruits_reach", "FruitsReachRegisterID"),
                                  ("game_fruits_grab", "FruitsGrabRegisterID"),
                                  ("game_fruits_sequence", "FruitsSequenceRegisterID"),
                                  ("game_fruits_flip", "FruitsFlipRegisterID")]:
                    cur.execute(f"SELECT {pk} FROM {tabla} WHERE FruitsRegisterID = %s", (fid,))
                    for (hid,) in cur.fetchall():
                        cur.execute(f"DELETE FROM {tabla}_times WHERE {pk} = %s", (hid,))
                    cur.execute(f"DELETE FROM {tabla} WHERE FruitsRegisterID = %s", (fid,))
                cur.execute("SELECT FruitsRaceRegisterID FROM game_fruits_race "
                            "WHERE FruitsRegisterID = %s", (fid,))
                for (rrid,) in cur.fetchall():
                    cur.execute("DELETE FROM game_fruits_race_action_state "
                                "WHERE FruitsRaceRegisterID = %s", (rrid,))
                    cur.execute("DELETE FROM game_fruits_race_times "
                                "WHERE FruitsRaceRegisterID = %s", (rrid,))
                cur.execute("DELETE FROM game_fruits_race WHERE FruitsRegisterID = %s", (fid,))
            cur.execute("DELETE FROM game_fruits WHERE SessionID = %s", (sid,))
        cur.execute("DELETE FROM session WHERE UserID = %s", (uid,))
        cur.execute("DELETE FROM user WHERE UserID = %s", (uid,))
        print(f"  Borrado {tag} (UserID {uid}, {len(sids)} sesiones)")
    conn.commit()
    print(f"{len(usuarios)} paciente(s) sintético(s) eliminados.")


# =============================================================================
# AUTO-VERIFICACIÓN CONTRA LA API
# =============================================================================
def _get_json(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode())


def verificar(resumen: dict):
    """Comprueba que el dashboard detecta lo inyectado. Imprime tabla esperado/obtenido."""
    p = resumen["params"]
    print(f"\n=== Verificación contra API ({API_BASE}) — {resumen['nombre']} ===")
    try:
        _get_json(f"{API_BASE}/api/patients")
    except (urllib.error.URLError, OSError):
        print("  ✗ API no accesible — arranca el backend (uvicorn) y usa --verify de nuevo.")
        return False

    filas = []
    ult = resumen["sesiones"][-1]

    # 1. Fatiga BBT (mano afectada, última sesión)
    mano = p["mano_afectada"]
    if ult["bbt"].get(mano):
        rid = ult["bbt"][mano]["register_id"]
        d = _get_json(f"{API_BASE}/api/bbt/{rid}")
        fat = d.get("indice_fatiga")
        espera_fatiga = p["fatiga_pct"] >= 18
        detectada = bool(fat and fat.get("fatiga_detectada"))
        filas.append(("Fatiga BBT detectada", espera_fatiga, detectada,
                      espera_fatiga == detectada))
        filas.append(("BBT completed (score)", ult["bbt"][mano]["completed"],
                      d["penalizaciones"]["completed"],
                      ult["bbt"][mano]["completed"] == d["penalizaciones"]["completed"]))
        filas.append(("BBT frames trayectoria", ult["bbt"][mano]["frames"],
                      len(d.get("x", [])), ult["bbt"][mano]["frames"] == len(d.get("x", []))))

    # 2. Asimetría Fruits reach (última sesión)
    if ult["fruits"].get("reach"):
        fid = ult["fruits"]["reach"]["fruits_register_id"]
        d = _get_json(f"{API_BASE}/api/fruits/{fid}")
        hands = d.get("hands", {})
        if "RIGHT" in hands and "LEFT" in hands:
            r = hands["RIGHT"]["metricas"]["frutas_por_minuto"]
            l = hands["LEFT"]["metricas"]["frutas_por_minuto"]
            asim_obs = abs(r - l) / ((r + l) / 2) * 100 if (r + l) else 0
            espera = p["asimetria_pct"]
            # tolerancia amplia: el ruido y la fatiga también afectan
            ok = (asim_obs >= espera * 0.4) if espera >= 15 else (asim_obs < 18)
            filas.append((f"Asimetría reach (~{espera}%)", f">= {espera*0.4:.0f}%",
                          f"{asim_obs:.1f}%", ok))

    # 3. Race: precisión y action_states
    if ult["fruits"].get("race"):
        fid = ult["fruits"]["race"]["fruits_register_id"]
        d = _get_json(f"{API_BASE}/api/fruits-race/{fid}")
        hands = d.get("hands", {})
        clave = p["mano_afectada"].upper()
        if clave in hands:
            esp = ult["fruits"]["race"]["hands"][p["mano_afectada"]]
            obs_states = len(hands[clave].get("action_states", []))
            esperado_states = esp["ok"] + esp["fail"]
            filas.append(("Race action_states", esperado_states, obs_states,
                          esperado_states == obs_states))
            obs_prec = hands[clave]["metricas"].get("precision_pct")
            filas.append(("Race precisión %", esp["precision"], obs_prec,
                          abs((obs_prec or 0) - esp["precision"]) < 0.1))

    # 4. Evolución: nº de sesiones
    d = _get_json(f"{API_BASE}/api/patients/{resumen['user_id']}/fruits-evolution")
    n_obs = len(d.get("sessions", []))
    filas.append(("Sesiones en evolución", p["sesiones"], n_obs, n_obs == p["sesiones"]))

    ancho = max(len(f[0]) for f in filas) + 2
    print(f"  {'Comprobación'.ljust(ancho)}{'Esperado':>14}{'Obtenido':>14}  Resultado")
    todo_ok = True
    for nombre, esp, obs, ok in filas:
        todo_ok &= ok
        print(f"  {nombre.ljust(ancho)}{str(esp):>14}{str(obs):>14}  {'✓' if ok else '✗'}")
    print(f"  → {'TODO CORRECTO' if todo_ok else 'HAY DISCREPANCIAS'}")
    return todo_ok


# =============================================================================
# WIZARD INTERACTIVO
# =============================================================================
def _pregunta(texto, defecto=None, tipo=str):
    sufijo = f" [{defecto}]" if defecto is not None else ""
    while True:
        v = input(f"  {texto}{sufijo}: ").strip()
        if not v and defecto is not None:
            return defecto
        if not v:
            continue
        try:
            if tipo is bool:
                return v.lower() in ("s", "si", "sí", "y", "yes", "1", "true")
            return tipo(v)
        except ValueError:
            print("    valor no válido, prueba otra vez")


def wizard():
    print("\n=== Generador de pacientes sintéticos — wizard ===\n")
    print("Cuadros disponibles:")
    for i, (k, v) in enumerate(CATALOGO.items(), 1):
        print(f"  {i:2}. {k:20} {v['desc']}")
    idx = _pregunta("Cuadro clínico (número o nombre)", "1")
    claves = list(CATALOGO.keys())
    cuadro = claves[int(idx) - 1] if str(idx).isdigit() else str(idx)
    if cuadro not in CATALOGO:
        sys.exit(f"Cuadro desconocido: {cuadro}")
    base = dict(PARAMS_BASE); base.update(CATALOGO[cuadro]["params"])

    nombre = _pregunta("Nombre del paciente", random.choice(NOMBRES_AUTO))
    overrides = {}
    overrides["sesiones"] = _pregunta("¿Cuántas sesiones?", base["sesiones"], int)
    overrides["tendencia"] = _pregunta(
        "Tendencia entre sesiones (mejora/empeora/meseta/recaida/sierra)",
        base["tendencia"])
    overrides["tendencia_pct"] = _pregunta("% de cambio por sesión", base["tendencia_pct"], float)
    if _pregunta("¿Fatiga intra-sesión? (s/n)", "s" if base["fatiga_pct"] else "n", bool):
        overrides["fatiga_pct"] = _pregunta("  % de caída de velocidad", base["fatiga_pct"] or 25, float)
    else:
        overrides["fatiga_pct"] = 0
    if _pregunta("¿Asimetría entre manos? (s/n)", "s" if base["asimetria_pct"] else "n", bool):
        overrides["asimetria_pct"] = _pregunta("  % de penalización", base["asimetria_pct"] or 30, float)
        overrides["mano_afectada"] = _pregunta("  Mano afectada (right/left)", base["mano_afectada"])
    else:
        overrides["asimetria_pct"] = 0
    juegos = _pregunta("Juegos a generar (coma: bbt,reach,grab,sequence,flip,race)",
                       ",".join(base["juegos"]))
    overrides["juegos"] = [j.strip() for j in juegos.split(",") if j.strip()]
    seed = _pregunta("Seed aleatoria", random.randint(1, 99999), int)

    receta = {
        "nombre": nombre,
        "apellido": "Sim",
        "tag": f"SIM-{cuadro.upper()}-{seed}",
        "cuadro": cuadro,
        "seed": seed,
        "overrides": overrides,
    }
    os.makedirs(PRESETS_DIR, exist_ok=True)
    ruta = os.path.join(PRESETS_DIR, f"{nombre.lower()}_{cuadro}.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(receta, f, ensure_ascii=False, indent=2)
    print(f"\nReceta guardada en {os.path.relpath(ruta)} — regenerable con --preset")
    return receta


# =============================================================================
# MAIN
# =============================================================================
def main():
    ap = argparse.ArgumentParser(description="Generador de pacientes sintéticos (SIM-*)")
    ap.add_argument("--list", action="store_true", help="muestra el catálogo de cuadros")
    ap.add_argument("--cuadro", help="cuadro del catálogo (modo directo, sin wizard)")
    ap.add_argument("--nombre", help="nombre del paciente (modo directo)")
    ap.add_argument("--sesiones", type=int, help="nº de sesiones (modo directo)")
    ap.add_argument("--seed", type=int, help="seed aleatoria (modo directo)")
    ap.add_argument("--preset", help="ruta a receta JSON existente")
    ap.add_argument("--all-presets", action="store_true",
                    help="siembra todos los presets de scripts/presets/ (batch; para el contenedor)")
    ap.add_argument("--clean", action="store_true", help="borra todos los pacientes SIM-*")
    ap.add_argument("--dry-run", action="store_true", help="genera y hace rollback (no persiste)")
    ap.add_argument("--dump-sql", metavar="FICHERO", help="vuelca los INSERTs a un .sql")
    ap.add_argument("--verify", action="store_true", help="verifica contra la API tras insertar")
    ap.add_argument("--db-url", help="DATABASE_URL alternativa")
    args = ap.parse_args()

    if args.list:
        print("Catálogo de cuadros clínicos:")
        for k, v in CATALOGO.items():
            print(f"  {k:20} {v['desc']}")
        return

    conn = _conexion(args.db_url)

    # Modo batch (contenedor): siembra todos los presets. Con --clean re-siembra.
    if args.all_presets:
        _resolver_ids(conn)
        ok = sembrar_todos(conn, clean_first=args.clean, dry_run=args.dry_run)
        sys.exit(0 if ok else 1)

    if args.clean:
        limpiar_sinteticos(conn)
        return

    if args.preset:
        with open(args.preset, encoding="utf-8") as f:
            receta = json.load(f)
        print(f"Receta cargada: {receta['nombre']} ({receta['cuadro']}, seed {receta['seed']})")
    elif args.cuadro:
        if args.cuadro not in CATALOGO:
            sys.exit(f"Cuadro desconocido: {args.cuadro} (usa --list)")
        seed = args.seed if args.seed is not None else random.randint(1, 99999)
        nombre = args.nombre or random.choice(NOMBRES_AUTO)
        overrides = {}
        if args.sesiones:
            overrides["sesiones"] = args.sesiones
        receta = {"nombre": nombre, "apellido": "Sim",
                  "tag": f"SIM-{args.cuadro.upper()}-{seed}",
                  "cuadro": args.cuadro, "seed": seed, "overrides": overrides}
        os.makedirs(PRESETS_DIR, exist_ok=True)
        ruta = os.path.join(PRESETS_DIR, f"{nombre.lower()}_{args.cuadro}.json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(receta, f, ensure_ascii=False, indent=2)
        print(f"Receta guardada en {os.path.relpath(ruta)}")
    else:
        receta = wizard()

    _resolver_ids(conn)
    ins = Insertor(conn, dump_path=args.dump_sql, dry_run=args.dry_run)
    try:
        resumen = insertar_paciente(ins, receta)
        ins.cierra(ok=True)
    except TagExistente as e:
        ins.cierra(ok=False)
        sys.exit(f"{e} Cambia la seed o borra los SIM-* con --clean.")
    except Exception:
        ins.cierra(ok=False)
        raise

    # Resumen navegable
    accion = "GENERADO (dry-run, no persistido)" if args.dry_run else "INSERTADO"
    print(f"\n{accion}: {resumen['nombre']} [{resumen['tag']}] — UserID {resumen['user_id']}")
    print(f"  Cuadro: {resumen['cuadro']} — {CATALOGO[resumen['cuadro']]['desc']}")
    for s in resumen["sesiones"]:
        partes = []
        for mano, b in s["bbt"].items():
            partes.append(f"bbt/{mano[0].upper()}={b['completed']}c (id {b['register_id']})")
        for modo, fdata in s["fruits"].items():
            partes.append(f"{modo} (id {fdata['fruits_register_id']})")
        print(f"  Sesión {s['session_id']} · {s['fecha']} · factor {s['factor']}: "
              + ", ".join(partes))
    if not args.dry_run:
        print(f"\n  Dashboard: abre el directorio de pacientes y busca '{resumen['nombre']}'")

    if args.verify and not args.dry_run:
        verificar(resumen)


if __name__ == "__main__":
    main()
