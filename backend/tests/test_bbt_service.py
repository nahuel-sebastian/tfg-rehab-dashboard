"""Tests de la lógica biomecánica BBT (funciones puras, sin BD ni servidor)."""
from services.bbt_service import (
    calcular_metricas_bbt,
    detectar_agarres_bbt,
    calcular_indice_fatiga,
)


# =============================================================================
# calcular_metricas_bbt
# =============================================================================

def test_metricas_trayectoria_simple():
    # Mueve 1 m en alcance (mano vacía), luego 0 m en transporte (agarrado)
    x = [0.0, 1.0, 1.0]
    y = [0.0, 0.0, 0.0]
    z = [0.0, 0.0, 0.0]
    grasps = [False, False, True]
    ts = [0.0, 1.0, 2.0]

    out = calcular_metricas_bbt(x, y, z, grasps, ts)
    m = out["metricas"]

    assert m["distancia_m"] == 1.0
    assert m["tiempo_alcance_s"] == 1.0
    assert m["tiempo_transporte_s"] == 1.0
    assert m["velocidad_media_ms"] == 0.5          # 1 m / 2 s
    assert m["velocidad_pico_ms"] == 1.0
    assert m["num_transiciones"] == 1              # un único False->True
    assert m["ratio_eficiencia_pct"] == 50.0       # 1 s transporte / 2 s total
    # velocidades: primer valor siempre 0, longitud == nº de frames
    assert out["velocidades"][0] == 0.0
    assert len(out["velocidades"]) == len(x)


def test_metricas_sin_movimiento():
    x = y = z = [0.0, 0.0]
    grasps = [False, False]
    ts = [0.0, 1.0]
    m = calcular_metricas_bbt(x, y, z, grasps, ts)["metricas"]
    assert m["distancia_m"] == 0.0
    assert m["velocidad_media_ms"] == 0.0
    assert m["num_transiciones"] == 0


def test_metricas_dt_cero_no_divide_por_cero():
    # Dos frames con el mismo timestamp -> no debe lanzar ZeroDivisionError
    x = [0.0, 1.0]; y = [0.0, 0.0]; z = [0.0, 0.0]
    out = calcular_metricas_bbt(x, y, z, [False, False], [5.0, 5.0])
    assert out["velocidades"][1] == 0.0


# =============================================================================
# detectar_agarres_bbt
# =============================================================================

def test_un_agarre_cerrado():
    grasps = [False, True, True, False]
    vel = [0.0, 0.5, 0.5, 0.0]
    ts = [0.0, 1.0, 2.0, 3.0]
    segs = detectar_agarres_bbt(grasps, vel, ts)
    assert len(segs) == 1
    assert segs[0]["num"] == 1
    assert segs[0]["frame_inicio_agarre"] == 1
    assert segs[0]["frame_fin"] == 2


def test_dos_agarres():
    grasps = [True, False, True, False]
    vel = [0.5, 0.0, 0.5, 0.0]
    ts = [0.0, 1.0, 2.0, 3.0]
    segs = detectar_agarres_bbt(grasps, vel, ts)
    assert len(segs) == 2
    assert [s["num"] for s in segs] == [1, 2]


def test_trayectoria_termina_en_agarre_bug4():
    # Regresión bug #4: si la trayectoria acaba con el objeto en la mano,
    # el último agarre NO debe perderse.
    grasps = [False, True]
    vel = [0.0, 0.5]
    ts = [0.0, 1.0]
    segs = detectar_agarres_bbt(grasps, vel, ts)
    assert len(segs) == 1
    assert segs[0]["frame_fin"] == 1   # último frame, no se descarta


def test_sin_agarres():
    segs = detectar_agarres_bbt([False, False, False], [0.0, 0.1, 0.1], [0, 1, 2])
    assert segs == []


# =============================================================================
# calcular_indice_fatiga
# =============================================================================

def _seg(num, vel):
    return {"num": num, "velocidad_media_ms": vel}


def test_fatiga_pocos_agarres_devuelve_none():
    # Menos de n*2 (=6) segmentos -> None
    segs = [_seg(i, 1.0) for i in range(5)]
    assert calcular_indice_fatiga(segs) is None


def test_fatiga_detectada_cuando_velocidad_cae():
    # Primeros 3 rápidos (1.0), últimos 3 lentos (0.5) -> -50% < -15% -> fatiga
    segs = [_seg(i, 1.0) for i in range(3)] + [_seg(i, 0.5) for i in range(3, 6)]
    out = calcular_indice_fatiga(segs)
    assert out is not None
    assert out["cambio_pct"] == -50.0
    assert out["fatiga_detectada"] is True


def test_fatiga_no_detectada_si_estable():
    segs = [_seg(i, 1.0) for i in range(6)]
    out = calcular_indice_fatiga(segs)
    assert out["cambio_pct"] == 0.0
    assert out["fatiga_detectada"] is False
