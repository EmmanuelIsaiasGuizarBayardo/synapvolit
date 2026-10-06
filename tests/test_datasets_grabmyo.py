"""Conversión de GRABMyo con registros WFDB sintéticos escritos en una carpeta temporal.

Las pruebas no descargan el dataset: imitan su estructura de carpetas y su formato para
verificar la selección de canales, el encadenado, las etiquetas y el remuestreo.
"""

import json

import numpy as np
import pytest

from synapvolit.datasets import cargar_senal
from synapvolit.datasets.grabmyo import REPOSO, convertir, ruta_registro

wfdb = pytest.importorskip("wfdb")
FS = 2048
ACTIVO = {11: 4, 12: 9, 14: 1, 13: 13}  # canal de la ranura que debe elegir la selección automática


def _escribir(raiz, rng):
    for g in (*ACTIVO, REPOSO):
        for t in (1, 2):
            x = rng.standard_normal((FS * 5, 32)) * 0.01  # mV
            if g in ACTIVO:
                x[:, ACTIVO[g]] *= 30  # un canal claramente específico por movimiento
            ruta = ruta_registro(raiz, 1, 3, g, t)
            ruta.parent.mkdir(parents=True, exist_ok=True)
            wfdb.wrsamp(
                ruta.name,
                fs=FS,
                units=["mV"] * 32,
                sig_name=[f"ch{i}" for i in range(32)],
                p_signal=x,
                fmt=["16"] * 32,
                write_dir=str(ruta.parent),
            )


def test_conversion_completa(tmp_path):
    raiz = tmp_path / "raw" / "grabmyo" / "1.1.0"
    _escribir(raiz, np.random.default_rng(0))
    csv = convertir(raiz, tmp_path / "processed", 1, 3, ensayos=range(1, 3))
    meta = json.loads(csv.with_suffix(".json").read_text(encoding="utf-8"))
    assert meta["canales_origen"] == [
        "F5",
        "F10",
        "F2",
        "F14",
    ]  # extensión, flexión, pronación, supinación
    s = cargar_senal(csv)
    assert s.fs == 2000 and s.datos.shape[1] == 4
    # 2 ensayos × 4 movimientos × (2 s de reposo + 5 s), menos 15 transiciones de 20 ms
    assert abs(len(s.datos) / s.fs - (56.0 - 15 * 0.020)) < 0.01
    cambios = s.etiquetas[np.flatnonzero(np.diff(s.etiquetas)) + 1]
    assert list(cambios[:8]) == [1, 0, 2, 0, 3, 0, 4, 0]  # orden del flujo
    assert np.all(s.datos[s.etiquetas == 1, 0].std() > 5 * s.datos[s.etiquetas == 0, 0].std())


def test_falta_un_archivo_dice_que_hacer(tmp_path):
    with pytest.raises(FileNotFoundError, match="data/raw"):
        convertir(tmp_path, tmp_path / "out", 1, 1, ensayos=range(1, 2))
