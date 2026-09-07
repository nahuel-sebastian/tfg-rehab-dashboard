# Panel clínico para análisis de sesiones de rehabilitación robótica

Trabajo de Fin de Grado, Grado en Ingeniería Informática, Universidad Carlos III
de Madrid. Curso 2025-2026.

Panel web para el análisis cinemático de sesiones de rehabilitación de la
extremidad superior. Toma los datos que registran las pruebas **Box and Blocks
Test** y **Fruits** (trayectorias tridimensionales de la mano, puntuaciones y
métricas temporales) y los transforma en métricas biomecánicas interpretables:
distancia, velocidad, eficiencia, índice de fatiga, asimetría bilateral y
dismetría.

---

## Puesta en marcha

Requisitos: Docker y Docker Compose. Nada más: el frontend no tiene cadena de
compilación y las bibliotecas de cliente van auto-alojadas.

```bash
cp .env.example .env      # y rellenar las credenciales
docker compose up --build
```

Un único comando levanta los cuatro servicios:

| Servicio | Qué hace | Puerto |
|---|---|---|
| `mysql` | Base de datos | 3307 |
| `flyway` | Construye el esquema y termina | — |
| `api` | API de análisis (FastAPI) | 8000 |
| `frontend` | Interfaz (nginx) | 80 |

- Interfaz: <http://localhost>
- Documentación interactiva de la API: <http://localhost:8000/docs>

## Datos

**La base arranca vacía.** El esquema se construye a partir de las migraciones de
`db/flyway/`, que no incluyen datos de pacientes.

Para poblarla con los pacientes sintéticos que ilustran la memoria:

```bash
docker compose exec api python scripts/seed_synthetic_patients.py --preset todos
docker compose exec api python scripts/seed_synthetic_patients.py --verify
```

Cada paciente se genera a partir de una **receta JSON con semilla fija**
(`scripts/presets/`), de modo que el resultado es reproducible de forma exacta.
La opción `--verify` consulta la API y comprueba que el sistema detecta lo que se
inyectó. `--clean` elimina los pacientes `SIM-*`.

El sistema también funciona **sin base de datos**: degrada al análisis de los
ficheros CSV de `backend/Patients/` y, si tampoco los hay, a datos simulados.

## Pruebas

```bash
cd backend && python -m pytest -q
```

34 pruebas que no requieren base de datos: se ejecutan sobre el camino
degradado. Se lanzan también en integración continua en cada cambio
(`.github/workflows/`).

## Mediciones de rendimiento

En `scripts/bench/`:

| Guion | Qué mide |
|---|---|
| `bench_analisis.py` | Escalado de la capa de análisis |
| `bench_endpoints.py` | Latencia de la API |
| `barrido_umbrales.py` | Sensibilidad de los umbrales clínicos |
| `bench_navegador.js` | Carga del visor 3D, cadencia y tiempo de informe |

El último se pega en la consola del navegador con un panel de BBT abierto.

## Estructura

```
backend/     API FastAPI: routers por dominio y servicios de análisis
frontend/    Interfaz Vue 3 sin compilación, con vendor/ auto-alojado
scripts/     Generador de pacientes sintéticos y bancos de medición
db/flyway/   Migraciones del esquema
```

## Sobre el esquema de base de datos

El esquema procede de la plataforma del departamento y queda fuera del alcance
de este trabajo: el panel es un consumidor de ese esquema, no su autor. Las
migraciones se incluyen para que el sistema sea reproducible por un tercero.
**Se han suprimido los usuarios de prueba que traía el volcado original**, de
modo que el repositorio no distribuye datos de identificación de personas.

## Licencia

El código se entrega a la Universidad Carlos III de Madrid, que puede usarlo,
modificarlo, extenderlo y desplegarlo con fines docentes y de investigación.
Fuera de ese ámbito, todos los derechos quedan reservados. Véase `LICENSE`.

Las bibliotecas de `frontend/vendor/` y las tipografías de `frontend/css/fonts/`
conservan sus propias licencias junto a los ficheros.
