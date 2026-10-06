"""COBS: vectores canónicos y validación contra una implementación independiente."""

import numpy as np
import pytest

from synapvolit.transporte import cobs_codificar, cobs_decodificar, cobs_max

# Vectores de la descripción original y de la referencia de Wikipedia
VECTORES = [
    (b"", b"\x01"),
    (b"\x00", b"\x01\x01"),
    (b"\x00\x00", b"\x01\x01\x01"),
    (b"\x11\x22\x00\x33", b"\x03\x11\x22\x02\x33"),
    (b"\x11\x22\x33\x44", b"\x05\x11\x22\x33\x44"),
    (b"\x11\x00\x00\x00", b"\x02\x11\x01\x01\x01"),
    (bytes(range(1, 255)), b"\xff" + bytes(range(1, 255))),
    (bytes(range(1, 256)), b"\xff" + bytes(range(1, 255)) + b"\x02\xff"),
]


def _cod(x: bytes) -> bytes:
    dst = bytearray(cobs_max(len(x)))
    return bytes(dst[: cobs_codificar(x, len(x), dst)])


@pytest.mark.parametrize(("dato", "codificado"), VECTORES)
def test_vectores_canonicos(dato, codificado):
    assert _cod(dato) == codificado
    dst = bytearray(len(dato) + 8)
    assert bytes(dst[: cobs_decodificar(codificado, 0, len(codificado), dst)]) == dato


def test_igual_a_implementacion_independiente():
    cobs = pytest.importorskip("cobs.cobs")
    rng = np.random.default_rng(1)
    for _ in range(300):
        n = int(rng.integers(0, 700))
        x = rng.integers(0, 256, n, dtype=np.uint8)
        x[rng.random(n) < 0.6] = rng.integers(1, 256)  # tramos largos sin ceros
        x = x.tobytes()
        assert _cod(x) == cobs.encode(x)


def test_trama_corrupta_se_rechaza():
    # los ceros nunca llegan al decodificador (son el delimitador); un byte alterado se nota
    # porque un código apunta fuera de la trama, o después por el CRC
    dst = bytearray(64)
    assert cobs_decodificar(b"\x09\x11\x22", 0, 3, dst) == -1
