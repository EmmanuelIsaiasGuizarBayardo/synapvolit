"""Criterios para aceptar un perfil guardado con la señal de hoy (una sola fuente de verdad).

La usan la verificación en vivo y la validación fuera de línea, así que lo que se mide en la
validación es exactamente lo que decide el motor con un paciente.

Dos criterios, porque fallan por razones distintas:

* **Exactitud** del LDA guardado sobre los datos de hoy (≥ 80%): si cambió la colocación de los
  electrodos, el patrón entre canales cambia y el modelo deja de acertar.
* **Razón de amplitud** entre la referencia de hoy y la guardada en cada canal agonista (0.5 a 2):
  una piel más seca o un electrodo más lejos cambian la amplitud y desajustan la intensidad.
"""

from __future__ import annotations

import numpy as np

from ..procesamiento import MOVIMIENTOS, MatrizCalibracion, calibrar
from .modelo import ModeloLDA, evaluar

EXACTITUD_MINIMA = 0.8
RAZON_MIN, RAZON_MAX = 0.5, 2.0


def verificar_perfil(
    guardada: MatrizCalibracion,
    modelo: ModeloLDA,
    env: np.ndarray,
    valida: np.ndarray,
    etiquetas: np.ndarray,
    rasgos: np.ndarray,
    etiquetas_rasgos: np.ndarray,
    tasa: float,
) -> dict:
    """``{"ok", "exactitud", "razon_amplitud", "fuera"}`` para los datos de una verificación."""
    try:
        nueva = calibrar(env, valida, etiquetas)
        razon = nueva.referencia_uv / guardada.referencia_uv
    except ValueError:  # ningún canal sube en su movimiento: casi seguro, electrodos movidos
        razon = np.zeros(len(guardada.reposo_uv))
    exactitud = evaluar(modelo, rasgos, etiquetas_rasgos, tasa)
    fuera = [
        MOVIMIENTOS[m]
        for m, c in enumerate(guardada.agonista)
        if not RAZON_MIN <= razon[c] <= RAZON_MAX
    ]
    return {
        "ok": exactitud >= EXACTITUD_MINIMA and not fuera,
        "exactitud": round(float(exactitud), 3),
        "razon_amplitud": [round(float(r), 2) for r in razon],
        "fuera": fuera,
    }
