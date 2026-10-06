"""Calibración y normalización con una sesión sintética de amplitudes conocidas."""

import numpy as np
import pytest

from synapvolit.procesamiento import (
    ConfigProcesamiento,
    MatrizCalibracion,
    Procesador,
    calibrar_senal,
)

FS = 2000.0
REPOSO, MVC = 3.0, 200.0


def _sesion(rng, reps=3, ganancia=1.0, antagonista=0.0):
    """Reposo 2 s + movimiento 3 s, para cada movimiento y repetición; el agonista es el canal m."""
    xs, ys = [], []
    for _ in range(reps):
        for m in range(4):
            xs.append(rng.standard_normal((int(2 * FS), 4)) * REPOSO)
            ys.append(np.zeros(int(2 * FS), np.int8))
            mov = rng.standard_normal((int(3 * FS), 4)) * REPOSO
            mov[:, m] = rng.standard_normal(int(3 * FS)) * MVC * ganancia
            mov[:, (1, 0, 3, 2)[m]] = rng.standard_normal(int(3 * FS)) * MVC * antagonista
            xs.append(mov)
            ys.append(np.full(int(3 * FS), m + 1, np.int8))
    return np.vstack(xs), np.concatenate(ys)


def test_normalizacion_a_mitad_de_esfuerzo_da_cerca_de_medio():
    rng = np.random.default_rng(0)
    cfg = ConfigProcesamiento()
    matriz = calibrar_senal(*_sesion(rng), cfg)
    assert np.all(matriz.referencia_uv > 20 * matriz.reposo_uv)
    x, y = _sesion(rng, reps=1, ganancia=0.5, antagonista=0.3)
    p = Procesador(cfg, matriz)
    vistos = {m: [] for m in range(4)}
    for i in range(0, len(x), 20):
        p.procesar(x[i : i + 20], np.ones((20, 4), bool))
        if y[i] > 0 and p.activacion_valida.all():
            vistos[y[i] - 1].append(p.activacion.copy())
    for m in range(4):
        a = np.median(vistos[m][len(vistos[m]) // 3 :], axis=0)  # ya dentro del movimiento
        assert abs(a[m] - 0.5) < 0.07, f"movimiento {m}: {a}"
        assert abs(matriz.coactivacion(a, m) - 0.6) < 0.1  # 0.3 / 0.5


def test_canal_que_no_se_activa_invalida_la_calibracion():
    with pytest.raises(ValueError, match="no supera su reposo"):
        MatrizCalibracion(np.full(4, 5.0), np.full((4, 4), 4.0))


def test_falta_un_movimiento_se_dice():
    x, y = _sesion(np.random.default_rng(1), reps=1)
    y[y == 3] = 0
    with pytest.raises(ValueError, match="pronacion"):
        calibrar_senal(x, y, ConfigProcesamiento())
