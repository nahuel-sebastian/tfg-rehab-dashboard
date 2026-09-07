FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Backend code (overridden at runtime by docker-compose volume)
COPY backend/ ./backend/

# Patient CSV data (fallback; volume takes priority at runtime)
COPY backend/Patients/ ./backend/Patients/

WORKDIR /app/backend

# Sin --reload: el watcher es de desarrollo (uvicorn local); en contenedor
# provoca reinicios a mitad de petición al tocar el volumen montado
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
