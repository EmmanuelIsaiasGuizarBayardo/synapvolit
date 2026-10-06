"""Funciones auxiliares del proyecto."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def zscore_por_canal(epochs: NDArray[np.floating], eps: float = 1e-8) -> NDArray[np.floating]:
    """Normaliza cada canal dentro de cada época.

    Parameters
    ----------
    epochs : ndarray of shape (n_epochs, n_channels, n_times)
        Datos de entrada.
    eps : float, default=1e-8
        Término de estabilidad para evitar división por cero en canales planos.

    Returns
    -------
    ndarray of shape (n_epochs, n_channels, n_times)
        Datos normalizados.

    Notes
    -----
    Esta normalización es por época y no requiere estadísticos del conjunto de
    entrenamiento, así que no introduce fuga de datos. Si en cambio normalizas
    con la media y desviación del dataset completo, el `fit` debe hacerse solo
    sobre el set de entrenamiento.
    """
    if epochs.ndim != 3:
        raise ValueError(f"Se esperaban 3 dimensiones, se recibieron {epochs.ndim}")
    media = epochs.mean(axis=-1, keepdims=True)
    desv = epochs.std(axis=-1, keepdims=True)
    return (epochs - media) / (desv + eps)
