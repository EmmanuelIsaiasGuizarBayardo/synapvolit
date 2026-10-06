"""Validación entre sesiones con registros WFDB sintéticos (estructura de GRABMyo, datos falsos)."""

import hashlib

import numpy as np
import pytest

from synapvolit.datasets.grabmyo import REPOSO, ruta_registro
from synapvolit.procesamiento import ConfigProcesamiento
from synapvolit.validacion import validar_participante, verificar_sumas

wfdb = pytest.importorskip("wfdb")
ACTIVO = {11: 4, 12: 9, 14: 1, 13: 13}


def _escribir(raiz, sesion, rng, ganancia=1.0, dur_s=1.2):
    for g in (*ACTIVO, REPOSO):
        for t in range(1, 8):
            x = rng.standard_normal((int(2048 * dur_s), 32)) * 0.01
            if g in ACTIVO:
                x[:, ACTIVO[g]] *= 30 * ganancia
            ruta = ruta_registro(raiz, sesion, 1, g, t)
            ruta.parent.mkdir(parents=True, exist_ok=True)
            wfdb.wrsamp(
                ruta.name,
                fs=2048,
                units=["mV"] * 32,
                sig_name=[f"c{i}" for i in range(32)],
                p_signal=x,
                fmt=["16"] * 32,
                write_dir=str(ruta.parent),
            )


def test_cinco_escenarios_y_criterio_de_amplitud(tmp_path):
    rng = np.random.default_rng(0)
    _escribir(tmp_path, 1, rng)
    _escribir(tmp_path, 2, rng, ganancia=0.25)  # el día 2 la señal llega a la cuarta parte
    r = validar_participante(tmp_path, 1, 1, 2, ConfigProcesamiento())
    assert r["canales"] == ["F5", "F10", "F2", "F14"]
    assert r["intra S1"] > 0.9 and r["recalibrado"] > 0.9
    assert not r["verificacion"]["ok"] and max(r["verificacion"]["razon_amplitud"]) < 0.5


def test_sumas_detectan_un_archivo_alterado(tmp_path):
    a, b = tmp_path / "a.dat", tmp_path / "b.hea"
    a.write_bytes(b"uno")
    b.write_bytes(b"dos")
    bien, mal = hashlib.sha256(b"uno").hexdigest(), hashlib.sha256(b"otro").hexdigest()
    (tmp_path / "SHA256SUMS.txt").write_text(f"{bien} a.dat\n{mal} b.hea\n", encoding="utf-8")
    assert verificar_sumas(tmp_path) == (2, ["b.hea"])
