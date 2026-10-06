"""Ruta completa con la fuente simulada: simulador → bytes → decodificador.

La señal de prueba se genera aquí porque las pruebas no pueden depender de un dataset
descargado; el simulador real reproduce GRABMyo.
"""

import numpy as np

from synapvolit.transporte import (
    ESCENARIOS,
    BufferCircular,
    Decodificador,
    Escenario,
    SimuladorESP32,
    correr,
)


def _senal(seg=3.0, fs=2000.0):
    rng = np.random.default_rng(10)
    return (rng.standard_normal((int(seg * fs), 4)) * 80).astype(np.float32), fs


def _correr(esc, seg=6.0):
    x, fs = _senal()
    sim = SimuladorESP32(x, fs, escenario=esc)
    buf = BufferCircular(4, int(seg * fs) + 2000)
    dec = Decodificador(buf)
    correr(sim, dec.alimentar, seg, tiempo_real=False)
    return sim, buf, dec


def test_escenario_limpio_es_exacto_y_da_la_vuelta_a_la_senal():
    sim, buf, dec = _correr(ESCENARIOS["limpio"])
    assert dec.tramas == 600 and dec.perdidas == dec.crc_malos == 0  # 6 s de una señal de 3 s
    esperado = (np.tile(sim.cuentas, (2, 1)) * sim.lsb_uv).astype(np.float32)
    assert np.array_equal(buf.datos[:12000], esperado)


def test_fallas_son_reproducibles_con_la_misma_semilla():
    esc = Escenario("prueba", perdida_tramas=0.05, corrupcion=0.05, semilla=3)
    a, b = _correr(esc)[2], _correr(esc)[2]
    assert (a.perdidas, a.crc_malos, a.cobs_malos) == (b.perdidas, b.crc_malos, b.cobs_malos)
    assert a.perdidas > 0 and a.crc_malos + a.cobs_malos > 0


def test_desconexion_y_contacto_quedan_marcados():
    esc = Escenario(
        "prueba",
        desconexion_cada_s=2.0,
        desconexion_dur_s=0.5,
        contacto_canal=1,
        contacto_cada_s=3.0,
        contacto_dur_s=1.0,
    )
    _, buf, dec = _correr(esc)
    assert (
        dec.perdidas == 2 * 50
    )  # dos desconexiones de 0.5 s (a los 2 y 4 s; a los 6 s ya terminó)
    sin_contacto = ~buf.valido[: buf.escritas, 1] & buf.valido[: buf.escritas, 0]
    assert sin_contacto.sum() == 2000  # 1 s a 2 kHz, a los 3 s
