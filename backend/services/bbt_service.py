import math
import statistics

def calcular_metricas_bbt(x, y, z, grasps, timestamps):
    distancia_total = 0.0
    tiempo_alcance = 0.0
    tiempo_transporte = 0.0
    velocidades = [0.0]

    for i in range(1, len(x)):
        dx = x[i] - x[i - 1]
        dy = y[i] - y[i - 1]
        dz = z[i] - z[i - 1]
        dist = math.sqrt(dx**2 + dy**2 + dz**2)
        distancia_total += dist

        dt = timestamps[i] - timestamps[i - 1]
        if grasps[i]:
            tiempo_transporte += dt
        else:
            tiempo_alcance += dt

        velocidades.append(round(dist / dt, 4) if dt > 0 else 0.0)

    tiempo_total = tiempo_alcance + tiempo_transporte
    duracion = (timestamps[-1] - timestamps[0]) if len(timestamps) > 1 else 0

    return {
        "metricas": {
            "distancia_m": round(distancia_total, 2),
            "tiempo_alcance_s": round(tiempo_alcance, 2),
            "tiempo_transporte_s": round(tiempo_transporte, 2),
            "velocidad_media_ms": round(distancia_total / duracion, 4) if duracion > 0 else 0.0,
            "velocidad_pico_ms": round(max(velocidades), 4) if velocidades else 0.0,
            "num_transiciones": sum(
                1 for i in range(1, len(grasps)) if grasps[i] != grasps[i - 1]
            ),
            "ratio_eficiencia_pct": round(
                (tiempo_transporte / tiempo_total) * 100, 1
            ) if tiempo_total > 0 else 0.0,
        },
        "velocidades": velocidades,
    }

def detectar_agarres_bbt(grasps, velocidades, timestamps):
    """Segmenta la trayectoria BBT en ciclos reach→transport por cada bloque agarrado."""
    segments = []
    n = len(grasps)
    in_grasp = False
    grasp_start = 0
    prev_end = 0
    grasp_num = 0

    def _cerrar(fin_excl):
        """Cierra el segmento de agarre actual; fin_excl = frame donde se soltó (exclusivo)."""
        nonlocal grasp_num, prev_end
        grasp_num += 1
        vel_transport = [velocidades[f] for f in range(grasp_start, fin_excl) if f < len(velocidades)]
        segments.append({
            'num':                       grasp_num,
            'frame_inicio_reach':        prev_end,
            'frame_inicio_agarre':       grasp_start,
            'frame_fin':                 fin_excl - 1,
            'duracion_reach_frames':     grasp_start - prev_end,
            'duracion_transporte_frames': fin_excl - grasp_start,
            'velocidad_media_ms':        round(statistics.mean(vel_transport), 4) if vel_transport else 0.0,
            'velocidad_pico_ms':         round(max(vel_transport), 4) if vel_transport else 0.0,
            'tiempo_inicio_s':           round(timestamps[prev_end], 2) if prev_end < len(timestamps) else 0.0,
            'tiempo_fin_s':              round(timestamps[fin_excl - 1], 2) if (fin_excl - 1) < len(timestamps) else 0.0,
        })
        prev_end = fin_excl

    for i in range(n):
        if grasps[i] and not in_grasp:
            in_grasp = True
            grasp_start = i
        elif not grasps[i] and in_grasp:
            in_grasp = False
            _cerrar(i)

    # La trayectoria termina con el objeto aún en la mano → cerrar el último agarre
    if in_grasp:
        _cerrar(n)

    return segments

def posiciones_agarre(grasps, x, y, z):
    """Posición (x,y,z) del inicio de cada agarre.

    Mismo criterio de inicio de segmento que detectar_agarres_bbt (incluye el
    frame 0 si la trayectoria empieza agarrando) → posiciones[i] corresponde
    1:1 con grasp_segments[i] en la vista 3D.
    """
    return [
        {"x": x[i], "y": y[i], "z": z[i]}
        for i in range(len(grasps))
        if grasps[i] and (i == 0 or not grasps[i - 1])
    ]

def calcular_indice_fatiga(grasp_segments, n=3):
    """Compara velocidad media de los primeros n agarres vs los últimos n."""
    if not grasp_segments or len(grasp_segments) < n * 2:
        return None
    primeros = grasp_segments[:n]
    ultimos  = grasp_segments[-n:]
    vel_p = sum(s['velocidad_media_ms'] for s in primeros) / n
    vel_u = sum(s['velocidad_media_ms'] for s in ultimos)  / n
    if vel_p == 0:
        return None
    cambio_pct = round((vel_u - vel_p) / vel_p * 100, 1)
    return {
        'velocidad_primeros_ms': round(vel_p, 4),
        'velocidad_ultimos_ms':  round(vel_u, 4),
        'cambio_pct':            cambio_pct,
        'n_agarres':             n,
        'fatiga_detectada':      cambio_pct < -15,
    }
