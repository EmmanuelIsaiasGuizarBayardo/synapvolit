"""Ruta completa: simulador → bytes → decodificador → procesador, con fallas sembradas."""

import time
import tracemalloc

import numpy as np

from synapvolit.procesamiento import MALO, ConfigProcesamiento, Procesador
from synapvolit.transporte import BufferCircular, Decodificador, Escenario, SimuladorESP32, correr

FS = 2000.0


def _montaje(esc):
    x = np.random.default_rng(7).standard_normal((int(5 * FS), 4)).astype(np.float32) * 40
    sim = SimuladorESP32(x, FS, escenario=esc)
    buf = BufferCircular(4, 8192)
    return sim, buf, Decodificador(buf), Procesador(ConfigProcesamiento())


def test_contacto_perdido_invalida_ese_canal_en_el_procesador():
    esc = Escenario("prueba", contacto_canal=2, contacto_cada_s=3.0, contacto_dur_s=1.0)
    sim, buf, dec, p = _montaje(esc)
    malo, valido = [], []
    for _ in range(600):  # 6 s en pasos de 10 ms
        correr(sim, dec.alimentar, 0.01, tiempo_real=False)
        p.actualizar(buf)
        malo.append(p.calidad[2] == MALO)
        valido.append(p.env_valida.copy())
    malo, valido = np.array(malo), np.array(valido)
    assert malo[330:390].all() and not malo[:290].any()
    assert not valido[330:390, 2].any() and valido[330:390, [0, 1, 3]].all()


def test_procesamiento_mucho_mas_rapido_que_el_tiempo_real_y_sin_crecer_en_memoria():
    sim, buf, dec, p = _montaje(Escenario())
    correr(sim, dec.alimentar, 1.0, tiempo_real=False)
    p.actualizar(buf)
    tracemalloc.start()
    antes = tracemalloc.get_traced_memory()[0]
    t0 = time.perf_counter()
    for _ in range(300):  # 30 s de señal, leída cada 100 ms
        correr(sim, dec.alimentar, 0.1, tiempo_real=False)
        p.actualizar(buf)
    dur = time.perf_counter() - t0
    crecimiento = tracemalloc.get_traced_memory()[0] - antes
    tracemalloc.stop()
    assert p.atrasos == 0 and p.procesadas == 31 * FS
    assert dur < 10.0, f"30 s de señal tardaron {dur:.1f} s"  # holgado: en una PC normal es <1 s
    assert crecimiento < 64_000, f"la memoria creció {crecimiento} bytes"
