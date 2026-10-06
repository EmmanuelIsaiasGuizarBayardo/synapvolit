"""Entrenamiento y evaluación fuera de línea con la misma cadena del tiempo real.

``evaluar_flujo`` procesa en bloques de 10 ms con ``Procesador`` y ``Decisor`` y decide a 8 Hz,
igual que la sesión en vivo; solo omite el transporte de bytes, que ya está probado aparte. Así
la exactitud que reporta es la que vería el juego.
"""

from __future__ import annotations

import numpy as np

from ..procesamiento import ConfigProcesamiento, MatrizCalibracion, Procesador, calibrar
from .decisor import Decisor
from .modelo import CLASES, ModeloLDA, entrenar

PASO_S, DECISION_S, IGNORAR_S = 0.010, 0.125, 0.5


def rasgos_de(x: np.ndarray, y: np.ndarray, cfg: ConfigProcesamiento) -> dict:
    """Envolvente, rasgos y etiquetas por paso de 10 ms de una señal etiquetada."""
    env, envv, rasgos, rv = Procesador(cfg).procesar_todo(x)
    paso = round(PASO_S * cfg.fs)
    etq_rasgos = np.where(rv, y, -1)[::paso].astype(np.int8)
    return {
        "env": env,
        "envv": envv,
        "y": y,
        "rasgos": rasgos[::paso],
        "etq": etq_rasgos,
        "tasa": cfg.fs / paso,
    }


def entrenar_desde(datos: list[dict]) -> tuple[MatrizCalibracion, ModeloLDA]:
    """Matriz con el primer bloque de datos y LDA con todos (el segundo sirve para adaptar)."""
    d0 = datos[0]
    matriz = calibrar(d0["env"], d0["envv"], d0["y"])
    modelo = entrenar(
        np.vstack([d["rasgos"] for d in datos]),
        np.concatenate([d["etq"] for d in datos]),
        d0["tasa"],
    )
    return matriz, modelo


def evaluar_flujo(
    modelo: ModeloLDA,
    matriz: MatrizCalibracion,
    x: np.ndarray,
    y: np.ndarray,
    cfg: ConfigProcesamiento,
) -> dict:
    """Decisiones a 8 Hz contra el movimiento real; ignora 0.5 s tras cada cambio de movimiento."""
    proc, dec = Procesador(cfg, matriz), Decisor(modelo, matriz)
    paso = round(PASO_S * cfg.fs)
    cada = round(DECISION_S / PASO_S)
    valido = np.ones((paso, cfg.canales), bool)
    confusion = np.zeros((len(CLASES), len(CLASES)), int)
    cambio = 0
    for k in range(len(x) // paso):
        i = (k + 1) * paso - 1
        proc.procesar(x[k * paso : i + 1], valido)
        dec.actualizar(proc.rasgos, proc.env_uv, proc.rasgos_validos)
        if i >= paso and y[i] != y[i - paso]:
            cambio = i
        if k % cada or i - cambio < IGNORAR_S * cfg.fs:
            continue
        d = dec.decision()
        if d is not None:
            confusion[y[i], d[0]] += 1
    total = confusion.sum()
    sens = [
        float(confusion[r, r] / confusion[r].sum()) if confusion[r].sum() else None
        for r in range(len(CLASES))
    ]
    return {
        "exactitud": float(np.trace(confusion) / total) if total else None,
        "sensibilidad": sens,
        "confusion": confusion,
        "decisiones": int(total),
    }
