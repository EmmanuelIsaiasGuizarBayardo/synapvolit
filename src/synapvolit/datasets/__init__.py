"""Datasets públicos de sEMG convertidos al formato que reproduce el simulador.

Formato: un CSV con columnas ``etiqueta, c0, c1, c2, c3`` (µV) y un JSON hermano con la
procedencia, el muestreo y el mapa de canales. Los datos viven en ``data/``, fuera de Git.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# Clases del contrato con WristQuest: 0 reposo, 1 extensión, 2 flexión, 3 pronación, 4 supinación
CLASES = ("reposo", "extension", "flexion", "pronacion", "supinacion")


@dataclass(frozen=True)
class Senal:
    """Señal multicanal en µV con su etiqueta por muestra y su procedencia."""

    datos: np.ndarray  # (N, canales) float32, µV
    etiquetas: np.ndarray  # (N,) int8, índice en CLASES
    fs: float
    meta: dict = field(default_factory=dict)


def cargar_senal(csv: Path) -> Senal:
    """Lee un CSV convertido y su JSON de procedencia.

    Raises
    ------
    FileNotFoundError
        Si falta el CSV o su JSON; el mensaje dice con qué comando se genera.
    """
    csv = Path(csv)
    meta_ruta = csv.with_suffix(".json")
    if not csv.exists() or not meta_ruta.exists():
        raise FileNotFoundError(
            f"No existe {csv} (o su .json). Se genera con: "
            "uv run python -m synapvolit.datasets.grabmyo --sesion 1 --participante 1"
        )
    meta = json.loads(meta_ruta.read_text(encoding="utf-8"))
    tabla = pd.read_csv(csv, dtype=np.float32)
    canales = [c for c in tabla.columns if c.startswith("c")]
    datos = np.ascontiguousarray(tabla[canales].to_numpy(dtype=np.float32))
    etiquetas = tabla["etiqueta"].to_numpy().astype(np.int8)
    return Senal(datos, etiquetas, float(meta["fs"]), meta)
