"""Filtros y envolvente contra referencias independientes y respuestas conocidas."""

import numpy as np
import pytest
from scipy.signal import sosfilt

from synapvolit.procesamiento import ConfigProcesamiento, FiltroEMG, RMSDeslizante


def _seno(f, fs, s=3.0, a=100.0):
    t = np.arange(int(s * fs)) / fs
    return np.tile((a * np.sin(2 * np.pi * f * t))[:, None], (1, 4))


def _por_bloques(filtro, x, b=20):
    return np.vstack([filtro.aplicar(x[i : i + b])[1] for i in range(0, len(x), b)])


@pytest.mark.parametrize("fs", [2000.0, 3000.0])
def test_por_bloques_es_identico_a_una_sola_pasada(fs):
    cfg = ConfigProcesamiento(fs=fs)
    x = np.random.default_rng(0).standard_normal((int(2 * fs), 4))
    f = FiltroEMG(cfg)
    ref = sosfilt(f.sos_red, sosfilt(f.sos_banda, x, axis=0), axis=0)
    np.testing.assert_allclose(_por_bloques(FiltroEMG(cfg), x), ref, rtol=0, atol=1e-10)


@pytest.mark.parametrize("fs", [2000.0, 3000.0])
@pytest.mark.parametrize(
    ("f", "minimo", "maximo"),
    [(10, 0, 0.1), (60, 0, 0.03), (100, 0.95, 1.05), (300, 0.95, 1.05), (700, 0, 0.3)],
)
def test_respuesta_en_frecuencia(fs, f, minimo, maximo):
    y = _por_bloques(FiltroEMG(ConfigProcesamiento(fs=fs)), _seno(f, fs))
    estable = y[int(1.5 * fs) :, 0]  # después del transitorio
    ganancia = np.sqrt(2) * estable.std() / 100.0
    assert minimo <= ganancia <= maximo, f"{f} Hz a fs={fs:g}: ganancia {ganancia:.3f}"


def test_envolvente_igual_a_convolucion_de_referencia():
    w, x = 300, np.random.default_rng(1).standard_normal((5000, 4)) * 50
    r = RMSDeslizante(4, w)
    env, val = np.empty((5000, 4), np.float32), np.empty((5000, 4), bool)
    for i in range(0, 5000, 20):
        r.actualizar(x[i : i + 20], np.ones((20, 4), bool), env[i : i + 20], val[i : i + 20])
    ref = np.sqrt(
        np.stack([np.convolve(x[:, c] ** 2, np.ones(w), "valid") / w for c in range(4)], axis=1)
    )
    np.testing.assert_allclose(env[w - 1 :], ref, rtol=1e-5)
    assert not val[: int(0.8 * w) - 1].any() and val[int(0.8 * w) :].all()


def test_envolvente_de_un_seno_es_amplitud_entre_raiz_de_dos():
    x = _seno(100, 2000.0, s=1.0, a=80.0)
    r = RMSDeslizante(4, 300)
    env, val = np.empty((2000, 4), np.float32), np.empty((2000, 4), bool)
    r.actualizar(x, np.ones_like(x, bool), env, val)
    assert abs(env[-1, 0] - 80 / np.sqrt(2)) < 0.5


def test_muestras_invalidas_no_cuentan():
    x = np.full((600, 4), 10.0)
    valido = np.ones((600, 4), bool)
    x[400:440, 1] = 1e6  # basura marcada como inválida
    valido[400:440, 1] = False
    r = RMSDeslizante(4, 300)
    env, val = np.empty((600, 4), np.float32), np.empty((600, 4), bool)
    r.actualizar(x, valido, env, val)
    assert (
        np.allclose(env[300:, 1], 10.0) and val[300:].all()
    )  # 40 de 300 inválidas: sigue valiendo
    valido[300:500, 2] = False
    r2 = RMSDeslizante(4, 300)
    r2.actualizar(x, valido, env, val)
    assert not val[480:520, 2].any()  # más del 20% inválido en la ventana: sin envolvente
