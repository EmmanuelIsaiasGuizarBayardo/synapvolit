"""Intérprete del protocolo con tramas sintéticas: sin hardware, sin reloj y sin hilos."""

import tracemalloc

import numpy as np

from synapvolit.transporte import BufferCircular, Decodificador, Empaquetador, crc16
from synapvolit.transporte.trama import BIT_SATURACION

N, NC = 20, 4


def _bloques(k, rng):
    return rng.integers(-3000, 3000, (k, N, NC), dtype=np.int16)


def _flujo(bloques, *, t0=0, saltar=(), banderas=None):
    emp, salida = Empaquetador(NC, N), bytearray()
    salida += emp.control({"tipo": "hola", "fs": 2000, "lsb_uv": 0.5})
    for k, b in enumerate(bloques):
        if k not in saltar:
            salida += emp.emg(k, t0 + k * 10_000, b, 0 if banderas is None else banderas[k])
    return bytes(salida)


def test_crc_valor_de_verificacion():
    assert crc16(b"123456789", 9) == 0x29B1  # CRC-16/CCITT-FALSE


def test_ida_y_vuelta_exacta_en_pedazos_arbitrarios():
    rng = np.random.default_rng(0)
    bloques = _bloques(50, rng)
    datos = _flujo(bloques)
    buf = BufferCircular(NC, 2000)
    dec = Decodificador(buf, fs=1000.0)
    i = 0
    while i < len(datos):  # el puerto entrega pedazos de tamaño variable
        k = int(rng.integers(1, 40))
        dec.alimentar(datos[i : i + k])
        i += k
    assert dec.tramas == 50 and dec.crc_malos == dec.cobs_malos == dec.perdidas == 0
    assert dec.fs == 2000 and dec.lsb_uv == 0.5  # el saludo fija muestreo y escala
    assert np.array_equal(buf.datos[:1000], bloques.reshape(-1, NC) * np.float32(0.5))
    assert buf.valido[:1000].all()
    assert np.all(np.diff(buf.t_us[:1000]) == 500)  # 2 kHz: 500 µs entre muestras


def test_perdida_de_tramas_es_ausencia_explicita():
    buf = BufferCircular(NC, 2000)
    dec = Decodificador(buf)
    dec.alimentar(_flujo(_bloques(10, np.random.default_rng(1)), saltar={3, 4}))
    assert dec.perdidas == 2 and dec.tramas == 8
    assert buf.escritas == 200  # el hueco ocupa su lugar en el tiempo
    assert not buf.valido[60:100].any() and buf.valido[:60].all() and buf.valido[100:200].all()
    assert np.all(np.diff(buf.t_us[:200]) == 500)


def test_byte_corrupto_se_descarta_y_el_flujo_se_recupera():
    datos = bytearray(_flujo(_bloques(20, np.random.default_rng(2))))
    datos[len(datos) // 2] ^= 0x5A
    dec = Decodificador(BufferCircular(NC, 2000))
    dec.alimentar(datos)
    assert dec.crc_malos + dec.cobs_malos >= 1
    assert dec.tramas >= 18 and dec.perdidas == 20 - dec.tramas


def test_contacto_perdido_invalida_solo_ese_canal():
    ban = [0] * 5
    ban[2] = 1 << 1 | BIT_SATURACION
    buf = BufferCircular(NC, 1000)
    dec = Decodificador(buf)
    dec.alimentar(_flujo(_bloques(5, np.random.default_rng(3)), banderas=ban))
    assert not buf.valido[40:60, 1].any() and buf.valido[40:60, [0, 2, 3]].all()
    assert dec.saturadas == 1


def test_vuelta_del_reloj_de_32_bits():
    buf = BufferCircular(NC, 1000)
    dec = Decodificador(buf)
    dec.alimentar(_flujo(_bloques(6, np.random.default_rng(4)), t0=2**32 - 25_000))
    assert np.all(np.diff(buf.t_us[:120]) == 500)  # continuo a través de la vuelta
    assert dec.reinicios == 0


def test_memoria_estable_en_flujo_largo():
    rng = np.random.default_rng(5)
    datos = _flujo(_bloques(200, rng))
    dec = Decodificador(BufferCircular(NC, 4096))
    for _ in range(3):  # calentamiento
        dec.alimentar(datos)
    tracemalloc.start()
    antes = tracemalloc.get_traced_memory()[0]
    for _ in range(25):  # 5000 tramas = 50 s de señal a 2 kHz
        dec.alimentar(datos)
    crecimiento = tracemalloc.get_traced_memory()[0] - antes
    tracemalloc.stop()
    assert crecimiento < 32_000, f"la memoria creció {crecimiento} bytes"
