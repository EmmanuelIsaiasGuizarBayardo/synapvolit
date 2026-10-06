"""Estados de contacto con tiempos exactos (contados en muestras, sin reloj)."""

import numpy as np

from synapvolit.procesamiento import BUENO, DUDOSO, MALO, ConfigProcesamiento, Procesador

FS = 2000.0


def _emg(s, rng, sigma=30.0):
    return rng.standard_normal((int(s * FS), 4)) * sigma


def _red(s, a):
    t = np.arange(int(s * FS)) / FS
    return (a * np.sin(2 * np.pi * 60 * t))[:, None]


def _correr(p, x, valido=None):
    estados = []
    for i in range(0, len(x), 20):
        v = np.ones((20, 4), bool) if valido is None else valido[i : i + 20]
        p.procesar(x[i : i + 20], v)
        estados.append(p.calidad.copy())
    return np.array(estados)  # un estado por bloque de 10 ms


def test_contacto_limpio_es_bueno():
    est = _correr(Procesador(ConfigProcesamiento()), _emg(2, np.random.default_rng(0)))
    assert (est[-100:] == BUENO).all()


def test_red_moderada_es_dudosa_y_fuerte_es_mala():
    rng = np.random.default_rng(1)
    x = _emg(3, rng)
    x[:, 1:2] += _red(3, 60.0)  # ~42 µV RMS de red
    x[:, 2:3] += _red(3, 400.0)  # ~280 µV RMS de red
    est = _correr(Procesador(ConfigProcesamiento()), x)
    assert est[-1, 0] == BUENO and est[-1, 1] == DUDOSO and est[-1, 2] == MALO


def test_senal_plana_es_mala():
    x = _emg(2, np.random.default_rng(2))
    x[:, 3] = 0.0
    assert _correr(Procesador(ConfigProcesamiento()), x)[-1, 3] == MALO


def test_contraccion_fuerte_no_se_confunde_con_red():
    x = _emg(3, np.random.default_rng(5), sigma=600.0)  # sEMG de banda ancha muy intensa
    est = _correr(Procesador(ConfigProcesamiento()), x)
    assert (est[30:] == BUENO).all()


def test_histeresis_no_parpadea_con_artefactos_breves():
    rng = np.random.default_rng(3)
    x = _emg(4, rng)
    t = np.arange(int(0.2 * FS)) / FS
    x[int(2.0 * FS) : int(2.2 * FS), 0] += 3000 * np.sin(np.pi * t / 0.2)  # tirón del cable, 200 ms
    x[int(3.0 * FS) : int(3.1 * FS), 1:2] += _red(0.1, 60.0)  # 100 ms de red moderada
    est = _correr(Procesador(ConfigProcesamiento()), x)
    assert (est[30:, :2] == BUENO).all()


def test_sin_contacto_entra_a_los_250_ms_y_sale_tras_500_ms_limpios():
    rng = np.random.default_rng(4)
    x = _emg(5, rng)
    valido = np.ones_like(x, bool)
    valido[int(2 * FS) : int(3 * FS), 1] = False  # el brazalete marca 1 s sin contacto
    est = _correr(Procesador(ConfigProcesamiento()), x, valido)[:, 1]
    malos = np.flatnonzero(est == MALO)
    assert 223 <= malos[0] <= 226  # bloque 200 = 2.0 s: entra al acumular 250 ms
    assert 347 <= malos[-1] <= 351  # bloque 300 = 3.0 s: sale tras 500 ms limpios
    assert (est[360:] == BUENO).all()
