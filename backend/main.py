"""
API REST — Dashboard HMI Rehabilitación Robótica
================================================
Fuentes de datos:
  - CSV  → datos reales BBT (trayectorias + histórico de partidas)
  - MySQL → datos estructurados Fruits/BBT (opcional, fallo silencioso)
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import patients, bbt, fruits, csv_routes

app = FastAPI(title="API Reportes - TFG Rehabilitación Robótica")

# allow_origins=["*"] es incompatible con allow_credentials=True (los navegadores
# rechazan el comodín con credenciales). No usamos cookies/auth, así que credentials=False.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend at /app/
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

app.include_router(patients.router)
app.include_router(bbt.router)
app.include_router(fruits.router)
app.include_router(csv_routes.router)
