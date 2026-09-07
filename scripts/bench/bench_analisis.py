#!/usr/bin/env python3
"""
Banco de medición de la capa de análisis (RNF-06, RNF-07).

Mide el coste de las funciones de servicio frente al tamaño de la trayectoria,
de forma independiente de la base de datos y del navegador. Reproducible:
semilla fija.

Uso:  python scripts/bench/bench_analisis.py [--repeticiones 20]
"""
import argparse
import math
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from services.bbt_service import (  # noqa: E402
    calcular_metricas_bbt,
    detectar_agarres_bbt,
    calcular_indice_fatiga,
    posiciones_agarre,
)

TAMANOS = [300, 1_000, 5_000, 10_000, 25_000, 50_000]
SEMILLA = 4242


def sintetizar(n, rng):
    """Trayectoria BBT plausible: ciclos alcance/transporte a 20 Hz."""
    x, y, z, grasps, ts = [], [], [], [], []
    t = 0.0
    ciclo = max(20, n // 30)          # ~30 agarres por sesion
    for i in range(n):
        fase = i % ciclo
        agarrado = fase > ciclo * 0.45
        ang = 2 * math.pi * fase / ciclo
        x.append(0.30 * math.cos(ang) + rng.gauss(0, 0.004))
        y.append(0.20 + 0.12 * math.sin(ang) + rng.gauss(0, 0.004))
        z.append(0.10 * math.sin(2 * ang) + rng.gauss(0, 0.004))
        grasps.append(agarrado)
        ts.append(t)
        t += 0.05                      # 20 Hz
    return x, y, z, grasps, ts


def medir(fn, reps):
    muestras = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        muestras.append((time.perf_counter() - t0) * 1000)
    muestras.sort()
    return {
        "media": statistics.mean(muestras),
        "p50": muestras[len(muestras) // 2],
        "p95": muestras[min(len(muestras) - 1, int(len(muestras) * 0.95))],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeticiones", type=int, default=20)
    args = ap.parse_args()

    print(f"Banco de analisis BBT - semilla {SEMILLA}, {args.repeticiones} repeticiones\n")
    print(f"{'fotogramas':>11} | {'metricas':>18} | {'segmentacion':>18} | "
          f"{'total p95':>10} | {'agarres':>8}")
    print(f"{'':->11}-+-{'':->18}-+-{'':->18}-+-{'':->10}-+-{'':->8}")

    filas = []
    for n in TAMANOS:
        rng = random.Random(SEMILLA)
        x, y, z, g, ts = sintetizar(n, rng)

        r_met = medir(lambda: calcular_metricas_bbt(x, y, z, g, ts), args.repeticiones)
        res = calcular_metricas_bbt(x, y, z, g, ts)
        vel = res["velocidades"]

        r_seg = medir(lambda: detectar_agarres_bbt(g, vel, ts), args.repeticiones)
        segs = detectar_agarres_bbt(g, vel, ts)
        calcular_indice_fatiga(segs)
        posiciones_agarre(g, x, y, z)

        total_p95 = r_met["p95"] + r_seg["p95"]
        filas.append((n, r_met, r_seg, total_p95, len(segs)))
        print(f"{n:>11,} | {r_met['media']:>7.2f} ms media | "
              f"{r_seg['media']:>7.2f} ms media | {total_p95:>7.2f} ms | {len(segs):>8}")

    print("\nRNF-06: p95 del analisis < 500 ms para sesiones de hasta 10.000 fotogramas")
    ref = next(f for f in filas if f[0] == 10_000)
    veredicto = "CUMPLE" if ref[3] < 500 else "NO CUMPLE"
    print(f"  -> 10.000 fotogramas: {ref[3]:.2f} ms p95  ->  {veredicto}")


if __name__ == "__main__":
    main()
