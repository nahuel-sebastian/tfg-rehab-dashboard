#!/usr/bin/env python3
"""
Analisis de sensibilidad de los umbrales de decision (memoria, seccion 8.3).

Los umbrales de fatiga (-15 %) y de asimetria (20 / 40 %) se fijaron por
criterio de diseno. Este script mide el valor real que presenta cada paciente
sintetico y barre los umbrales para determinar cuanto depende de ellos la
clasificacion.

Requiere MySQL disponible con los pacientes SIM-* sembrados.
Uso:  python scripts/bench/barrido_umbrales.py [--latex]
"""
import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

cli = TestClient(app)

UMBRALES_FATIGA = [-5, -10, -15, -20, -25, -30]
UMBRALES_ASIM = [10, 15, 20, 25, 30, 40]


def pacientes_sinteticos():
    ps = cli.get("/api/patients").json().get("patients", [])
    return [p for p in ps if p.get("UserSurname1") == "Sim"]


def recorrer(uid):
    """Devuelve (cambios_fatiga, asimetrias) de todas las sesiones del paciente."""
    fatigas, asimetrias = [], []
    ses = cli.get(f"/api/patients/{uid}/sessions").json().get("sessions", [])
    for s in ses:
        juegos = cli.get(f"/api/sessions/{s['SessionID']}/games").json().get("games", [])
        for j in juegos:
            rid = j["register_id"]
            if j["game_type"] == "bbt":
                d = cli.get(f"/api/bbt/{rid}").json()
                idx = d.get("indice_fatiga") or {}
                if idx.get("cambio_pct") is not None:
                    fatigas.append(idx["cambio_pct"])
            elif j.get("game_mode") == "reach":
                d = cli.get(f"/api/fruits/{rid}").json()
                manos = d.get("hands") or {}
                fpm = [manos[k]["metricas"]["frutas_por_minuto"]
                       for k in ("LEFT", "RIGHT")
                       if manos.get(k, {}).get("metricas", {}).get("frutas_por_minuto")]
                if len(fpm) == 2 and max(fpm) > 0:
                    asimetrias.append((max(fpm) - min(fpm)) / max(fpm) * 100)
    return fatigas, asimetrias


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--latex", action="store_true", help="emite las filas en LaTeX")
    args = ap.parse_args()

    datos = []
    for p in pacientes_sinteticos():
        f, a = recorrer(p["UserID"])
        datos.append({
            "nombre": p["UserName"],
            "fatiga": statistics.mean(f) if f else None,
            "asim": statistics.mean(a) if a else None,
        })

    print("VALORES MEDIDOS POR PACIENTE\n")
    print(f"{'paciente':<10} | {'fatiga (%)':>11} | {'asimetria (%)':>14}")
    print(f"{'':-<10}-+-{'':->11}-+-{'':->14}")
    for d in datos:
        f = f"{d['fatiga']:+.1f}" if d["fatiga"] is not None else "n/d"
        a = f"{d['asim']:.1f}" if d["asim"] is not None else "n/d"
        print(f"{d['nombre']:<10} | {f:>11} | {a:>14}")

    print("\n\nBARRIDO DEL UMBRAL DE FATIGA")
    print("(x = fatiga detectada con ese umbral)\n")
    cab = "  ".join(f"{u:>4}%" for u in UMBRALES_FATIGA)
    print(f"{'paciente':<10} | {cab}")
    print(f"{'':-<10}-+-{'':->{len(cab)}}")
    for d in datos:
        if d["fatiga"] is None:
            continue
        marcas = "  ".join(f"{'x' if d['fatiga'] < u else '.':>5}" for u in UMBRALES_FATIGA)
        print(f"{d['nombre']:<10} | {marcas}")
    print(f"{'':-<10}-+-{'':->{len(cab)}}")
    tot = "  ".join(f"{sum(1 for d in datos if d['fatiga'] is not None and d['fatiga'] < u):>5}"
                    for u in UMBRALES_FATIGA)
    print(f"{'TOTAL':<10} | {tot}")

    print("\n\nBARRIDO DEL UMBRAL DE ASIMETRIA")
    print("(x = alerta emitida con ese umbral)\n")
    cab = "  ".join(f"{u:>4}%" for u in UMBRALES_ASIM)
    print(f"{'paciente':<10} | {cab}")
    print(f"{'':-<10}-+-{'':->{len(cab)}}")
    for d in datos:
        if d["asim"] is None:
            continue
        marcas = "  ".join(f"{'x' if d['asim'] > u else '.':>5}" for u in UMBRALES_ASIM)
        print(f"{d['nombre']:<10} | {marcas}")
    print(f"{'':-<10}-+-{'':->{len(cab)}}")
    tot = "  ".join(f"{sum(1 for d in datos if d['asim'] is not None and d['asim'] > u):>5}"
                    for u in UMBRALES_ASIM)
    print(f"{'TOTAL':<10} | {tot}")

    print("\n\nMARGEN RESPECTO AL UMBRAL ADOPTADO")
    print("(distancia en puntos porcentuales; margen pequeno = clasificacion fragil)\n")
    print(f"{'paciente':<10} | {'fatiga vs -15':>14} | {'asimetria vs 20':>16}")
    print(f"{'':-<10}-+-{'':->14}-+-{'':->16}")
    for d in datos:
        mf = f"{d['fatiga'] - (-15):+.1f}" if d["fatiga"] is not None else "n/d"
        ma = f"{d['asim'] - 20:+.1f}" if d["asim"] is not None else "n/d"
        print(f"{d['nombre']:<10} | {mf:>14} | {ma:>16}")

    if args.latex:
        print("\n\n% --- filas LaTeX ---")
        for d in datos:
            f = f"${d['fatiga']:+.1f}$" if d["fatiga"] is not None else "---"
            a = f"${d['asim']:.1f}$" if d["asim"] is not None else "---"
            print(f"\t\t{d['nombre']} & {f} & {a} \\\\ \\hline")


if __name__ == "__main__":
    main()
