"""Perfil de calibración de un paciente: matriz y LDA guardados junto a sus sesiones.

Se guarda en JSON legible, nunca con ``pickle``: abrir un perfil no puede ejecutar código, y
cualquiera puede revisar qué contiene. No incluye sEMG: solo reposo y referencias por canal,
los pesos del LDA, su exactitud y la configuración con que se obtuvieron.

Un perfil solo se usa si la cadena actual calcula los mismos rasgos que cuando se creó (mismo
muestreo, canales, banda, red y ventana). Si no, se rechaza con el motivo: un modelo entrenado
con otros rasgos daría decisiones sin sentido sin avisar.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import numpy as np

from ..clasificacion import ModeloLDA
from ..procesamiento import ConfigProcesamiento, MatrizCalibracion

VERSION = 1
ARCHIVO = "perfil.json"
RASGOS = "log1p(RMS)+log1p(DASDV)"


def _firma(cfg: ConfigProcesamiento) -> dict:
    return {
        "fs": cfg.fs,
        "canales": cfg.canales,
        "banda_hz": list(cfg.banda_hz),
        "red_hz": cfg.red_hz,
        "ventana_rms_s": cfg.ventana_rms_s,
        "rasgos": RASGOS,
    }


def guardar_perfil(
    carpeta: Path, matriz: MatrizCalibracion, modelo: ModeloLDA, cfg: ConfigProcesamiento
) -> Path:
    """Escribe el perfil de forma atómica (archivo temporal y reemplazo): nunca queda a medias."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    datos = {
        "version": VERSION,
        "fecha": f"{datetime.now():%Y-%m-%d}",
        "config": _firma(cfg),
        "matriz": {
            "reposo_uv": matriz.reposo_uv.tolist(),
            "mvc_uv": matriz.mvc_uv.tolist(),
            "agonista": list(matriz.agonista),
            "antagonista": list(matriz.antagonista),
        },
        "modelo": {
            "w": modelo.w.tolist(),
            "b": modelo.b.tolist(),
            "clases": modelo.clases.tolist(),
            "exactitud": modelo.exactitud,
        },
    }
    destino, temporal = carpeta / ARCHIVO, carpeta / (ARCHIVO + ".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temporal, destino)
    return destino


def cargar_perfil(
    carpeta: Path, cfg: ConfigProcesamiento
) -> tuple[MatrizCalibracion, ModeloLDA, dict] | None:
    """Lee el perfil; ``None`` si no existe.

    Raises
    ------
    ValueError
        Si está dañado o se creó con otra configuración de rasgos (dice cuál).
    """
    ruta = Path(carpeta) / ARCHIVO
    if not ruta.exists():
        return None
    try:
        d = json.loads(ruta.read_text(encoding="utf-8"))
        if d.get("version") != VERSION:
            raise ValueError(f"versión de perfil {d.get('version')} no compatible")
        diferentes = [k for k, v in _firma(cfg).items() if d["config"].get(k) != v]
        if diferentes:
            raise ValueError(f"se creó con otra configuración ({', '.join(diferentes)})")
        m = d["matriz"]
        matriz = MatrizCalibracion(
            np.array(m["reposo_uv"]),
            np.array(m["mvc_uv"]),
            tuple(m["agonista"]),
            tuple(m["antagonista"]),
        )
        o = d["modelo"]
        modelo = ModeloLDA(
            np.array(o["w"]), np.array(o["b"]), np.array(o["clases"]), o.get("exactitud")
        )
    except (KeyError, TypeError, json.JSONDecodeError) as e:
        raise ValueError(f"perfil dañado: {e}") from e
    return matriz, modelo, {"fecha": d.get("fecha"), "exactitud": modelo.exactitud}
