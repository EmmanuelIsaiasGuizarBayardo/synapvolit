"""Pasa-banda y muesca de red causales, con estado por canal para procesar por bloques.

Procesar por bloques con el estado ``zi`` que deja el bloque anterior da exactamente el mismo
resultado que filtrar la señal completa de una vez; una prueba lo verifica, porque es el error
silencioso más común del filtrado en línea (reiniciar el estado en cada bloque).
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, iirnotch, sosfilt, tf2sos

from .config import ConfigProcesamiento


class FiltroEMG:
    """Butterworth pasa-banda seguido de muescas en la red y sus armónicos."""

    def __init__(self, cfg: ConfigProcesamiento) -> None:
        nyq = cfg.fs / 2
        bajo, alto = (
            cfg.banda_hz[0],
            min(cfg.banda_hz[1], 0.95 * nyq),
        )  # con fs baja no se pide 450 Hz
        self.sos_banda = butter(cfg.orden, [bajo, alto], btype="bandpass", fs=cfg.fs, output="sos")
        muescas = [
            tf2sos(*iirnotch(k * cfg.red_hz, cfg.q_muesca, fs=cfg.fs))
            for k in range(1, cfg.armonicos + 1)
            if k * cfg.red_hz < alto
        ]
        self.sos_red = np.vstack(muescas) if muescas else None
        self.zi_banda = np.zeros((len(self.sos_banda), 2, cfg.canales))
        self.zi_red = (
            None if self.sos_red is None else np.zeros((len(self.sos_red), 2, cfg.canales))
        )

    def aplicar(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Filtra un bloque ``(k, canales)``.

        Returns
        -------
        y_banda : np.ndarray
            Salida del pasa-banda, antes de la muesca.
        y : np.ndarray
            Señal final. ``y_banda - y`` es la componente de red que quitó la muesca; la calidad
            de contacto la usa sin filtrar nada más.
        """
        y_banda, self.zi_banda = sosfilt(self.sos_banda, x, axis=0, zi=self.zi_banda)
        if self.sos_red is None:
            return y_banda, y_banda
        y, self.zi_red = sosfilt(self.sos_red, y_banda, axis=0, zi=self.zi_red)
        return y_banda, y
