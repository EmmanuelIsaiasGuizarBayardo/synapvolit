"""LDA, intensidad por patrón y decisión suavizada, contra referencias independientes."""

import time

import numpy as np
import pytest
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis

from synapvolit.clasificacion import Decisor, Intensidades, entrenar
from synapvolit.procesamiento import MatrizCalibracion

TASA = 100.0
CENTROS = np.array([[0, 0], [3, 0], [0, 3], [-3, 0], [0, -3]], float)  # 5 clases separables


def _datos(rng, reps=3, s=2.0, ruido=0.6):
    """Reposo y luego cada movimiento, ``reps`` veces; rasgos de 8 dimensiones."""
    xs, ys = [], []
    for _ in range(reps):
        for c in (0, 1, 0, 2, 0, 3, 0, 4):
            n = int(s * TASA)
            x = np.zeros((n, 8))
            x[:, :2] = CENTROS[c]
            xs.append(x + rng.standard_normal((n, 8)) * ruido)
            ys.append(np.full(n, c, np.int8))
    return np.vstack(xs), np.concatenate(ys)


def test_inferencia_identica_a_scikit_learn():
    x, y = _datos(np.random.default_rng(0))
    modelo = entrenar(x, y, TASA, quitar_inicio_s=0.0)
    ref = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto").fit(x, y)
    post = np.empty(5)
    for fila in x[::37]:
        np.testing.assert_allclose(
            modelo.probabilidades(fila, post), ref.predict_proba(fila[None])[0], atol=1e-9
        )


def test_exactitud_validada_por_repeticiones():
    x, y = _datos(np.random.default_rng(1))
    assert entrenar(x, y, TASA).exactitud > 0.95
    x1, y1 = _datos(np.random.default_rng(1), reps=1)
    assert entrenar(x1, y1, TASA).exactitud is None  # con una repetición no hay estimación honesta


def test_falta_una_clase():
    x, y = _datos(np.random.default_rng(2))
    with pytest.raises(ValueError, match="flexion"):
        entrenar(x[y != 2], y[y != 2], TASA)


def test_softmax_estable_con_puntajes_enormes():
    x, y = _datos(np.random.default_rng(3))
    post = entrenar(x, y, TASA).probabilidades(np.full(8, 1e6), np.empty(5))
    assert np.isfinite(post).all() and abs(post.sum() - 1) < 1e-12


def _matriz():
    # extensión activa sobre todo el canal 0 pero también los demás (diafonía, como en GRABMyo)
    reposo = np.full(4, 10.0)
    mvc = np.array(
        [[400, 120, 120, 120], [20, 100, 30, 20], [20, 30, 100, 40], [20, 20, 40, 100]], float
    )
    return MatrizCalibracion(reposo, mvc)


def test_intensidad_por_patron_y_co_contraccion():
    m = _matriz()
    it, co = np.empty(4), np.empty(4)
    calc = Intensidades(m)
    p = m.mvc_uv - m.reposo_uv
    calc.calcular(m.reposo_uv + 0.5 * p[0], it, co)
    assert abs(it[0] - 0.5) < 1e-9 and co[0] < 1e-9  # mitad del patrón de extensión, sin flexión
    calc.calcular(m.reposo_uv + 0.6 * p[1] + 0.3 * p[0], it, co)
    assert abs(co[1] - 0.5) < 1e-9  # la diafonía compartida no se confunde con antagonista


def test_patrones_paralelos_no_dan_co_contraccion():
    reposo = np.full(4, 10.0)
    mvc = np.array([[110, 60, 10, 10], [210, 110, 10.0, 10], [10, 10, 110, 60], [10, 10, 60, 110]])
    it, co = np.empty(4), np.empty(4)
    Intensidades(MatrizCalibracion(reposo, mvc)).calcular(np.full(4, 50.0), it, co)
    assert np.isnan(co[0]) and np.isnan(co[1]) and not np.isnan(co[2])


def test_decisor_suaviza_y_respeta_la_ausencia():
    x, y = _datos(np.random.default_rng(4))
    d = Decisor(entrenar(x, y, TASA), _matriz(), pasos=12)
    assert d.decision() is None
    env = np.full(4, 10.0)
    for _ in range(12):
        d.actualizar(np.r_[CENTROS[2], np.zeros(6)], env, True)
    d.actualizar(np.r_[CENTROS[1], np.zeros(6)], env, True)  # una ventana aislada distinta
    clase, conf, _, _ = d.decision()
    assert clase == 2 and conf > 0.85
    for _ in range(9):
        d.actualizar(np.zeros(8), env, False)
    assert d.decision() is None  # menos del 75% de pasos válidos en la ventana


def test_costo_por_paso_despreciable():
    x, y = _datos(np.random.default_rng(5))
    d = Decisor(entrenar(x, y, TASA), _matriz())
    env, r = np.full(4, 50.0), x[100]
    t0 = time.perf_counter()
    for _ in range(5000):
        d.actualizar(r, env, True)
    por_paso = (time.perf_counter() - t0) / 5000
    assert por_paso < 0.5e-3, f"{por_paso * 1e6:.0f} µs por paso"  # el paso dura 10 ms
