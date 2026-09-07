#!/usr/bin/env python3
"""
Banco de latencia de los endpoints (RNF-06).

Mide el tiempo de respuesta extremo a extremo con el cliente de pruebas de
FastAPI, sobre el camino de ficheros CSV. No requiere base de datos.

Uso:  python scripts/bench/bench_endpoints.py [--repeticiones 30]
"""
import argparse
import statistics
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)


def medir(ruta, reps):
    client.get(ruta)                      # calentamiento
    m = []
    for _ in range(reps):
        t0 = time.perf_counter()
        r = client.get(ruta)
        m.append((time.perf_counter() - t0) * 1000)
    m.sort()
    return r.status_code, statistics.mean(m), m[min(len(m) - 1, int(len(m) * 0.95))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeticiones", type=int, default=30)
    args = ap.parse_args()

    rutas = ["/api/csv/patients", "/api/patients"]

    r = client.get("/api/csv/patients")
    if r.status_code == 200:
        for p in (r.json().get("patients") or [])[:1]:
            nombre = p.get("name") or p.get("nombre")
            if nombre:
                rutas += [f"/api/csv/patients/{nombre}/sessions",
                          f"/api/csv/patients/{nombre}/evolution"]

    print(f"Latencia de endpoints - camino CSV, {args.repeticiones} repeticiones\n")
    print(f"{'endpoint':<48} | {'cod':>4} | {'media':>9} | {'p95':>9}")
    print(f"{'':-<48}-+-{'':->4}-+-{'':->9}-+-{'':->9}")
    peor = 0.0
    for ruta in rutas:
        cod, media, p95 = medir(ruta, args.repeticiones)
        peor = max(peor, p95)
        print(f"{ruta[:48]:<48} | {cod:>4} | {media:>6.2f} ms | {p95:>6.2f} ms")

    print(f"\nRNF-06: p95 < 500 ms  ->  peor caso medido {peor:.2f} ms  ->  "
          f"{'CUMPLE' if peor < 500 else 'NO CUMPLE'}")
    print("Limitacion: solo camino CSV. El camino SQL requiere MySQL disponible.")


if __name__ == "__main__":
    main()
