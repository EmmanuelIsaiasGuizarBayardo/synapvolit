"""Parámetros del procesamiento en tiempo real. Todo se deriva de ``fs``: nada asume 2 kHz."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigProcesamiento:
    """Configuración de filtros, envolvente y calidad de contacto.

    Los valores por defecto siguen las recomendaciones habituales para sEMG de superficie
    (pasa-banda de 20 a 450 Hz) y el GDD (envolvente RMS de 100 a 200 ms).
    """

    fs: float = 2000.0
    canales: int = 4
    banda_hz: tuple[float, float] = (20.0, 450.0)
    orden: int = 4  # Butterworth: 4 polos por flanco
    red_hz: float = 60.0  # México: 60 Hz
    armonicos: int = 1  # cuántos múltiplos de la red se eliminan (1 = solo la fundamental)
    # Q de la muesca: 10 quita 6 Hz alrededor de la red. Una Q alta (30) es más angosta, pero
    # su timbre tras una ráfaga de red dura ~Q/(π·f0) = 160 ms y contamina la envolvente; con
    # Q = 10 dura ~53 ms (ver test_histeresis_no_parpadea_con_rafagas_breves).
    q_muesca: float = 10.0
    ventana_rms_s: float = 0.150
    asentamiento_s: float = (
        0.050  # tras un hueco, cuánto se descarta mientras los filtros se asientan
    )
    fraccion_valida: float = 0.8  # mínimo de muestras válidas en la ventana para dar una envolvente
    bloque_max: int = 512

    @property
    def ventana(self) -> int:
        return max(1, round(self.ventana_rms_s * self.fs))

    @property
    def asentamiento(self) -> int:
        return round(self.asentamiento_s * self.fs)
