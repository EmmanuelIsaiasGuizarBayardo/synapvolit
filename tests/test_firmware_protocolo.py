"""El firmware del ESP32 arma exactamente los mismos bytes que el motor espera.

Compila ``firmware/brazalete_esp32/protocolo.h`` en la PC (si hay un compilador de C++) y compara su
salida, byte a byte, con la de ``synapvolit.transporte.Empaquetador``; después la decodifica.
"""

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from synapvolit.transporte import BufferCircular, Decodificador, Empaquetador
from synapvolit.transporte.trama import BIT_SATURACION

RAIZ = Path(__file__).resolve().parents[1] / "firmware" / "brazalete_esp32"
COMPILADOR = shutil.which("g++") or shutil.which("clang++")


def _bloque(s: int) -> np.ndarray:
    i = np.arange(80)
    m = ((s * 977 + i * 131) % 65536 - 32768).astype(np.int16)
    if s % 7 == 0:
        m[5] = 0
    return m.reshape(20, 4)


@pytest.mark.skipif(COMPILADOR is None, reason="sin compilador de C++ en esta máquina")
def test_bytes_identicos_a_python_y_decodificables(tmp_path):
    exe = tmp_path / "prueba_pc"
    subprocess.run(
        [COMPILADOR, "-std=c++17", "-O2", "-o", str(exe), str(RAIZ / "prueba_pc.cpp")], check=True
    )
    cpp = subprocess.run([str(exe)], check=True, capture_output=True).stdout
    emp, py = Empaquetador(4, 20), bytearray()
    for s in range(300):
        py += emp.emg(
            s,
            (4294900000 + s * 10000) & 0xFFFFFFFF,
            _bloque(s),
            BIT_SATURACION if s % 11 == 0 else 0,
        )
        if s == 150:
            py += emp.control({"tipo": "hola", "fs": 2000, "lsb_uv": 0.75})
    assert cpp == bytes(py)  # 300 tramas EMG y un saludo: idénticos byte a byte
    buf = BufferCircular(4, 8000)
    dec = Decodificador(buf)
    dec.alimentar(cpp)
    assert (
        dec.tramas == 300 and dec.crc_malos == dec.cobs_malos == dec.perdidas == dec.reinicios == 0
    )
    assert dec.lsb_uv == 0.75 and dec.saturadas == 28
    assert np.all(
        np.diff(buf.t_us[:6000]) > 0
    )  # continuo a través de la vuelta del reloj de 32 bits
