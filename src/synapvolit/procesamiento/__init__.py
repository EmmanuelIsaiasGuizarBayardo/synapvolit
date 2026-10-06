"""Procesamiento en tiempo real: filtros, envolvente RMS, calidad de contacto y normalización."""

from .calibracion import MOVIMIENTOS, MatrizCalibracion, calibrar
from .calidad import BUENO, DUDOSO, MALO, NOMBRES, SIN_EVALUAR, CalidadContacto, UmbralesCalidad
from .config import ConfigProcesamiento
from .envolvente import RMSDeslizante
from .filtros import FiltroEMG
from .procesador import Procesador

__all__ = [
    "BUENO",
    "DUDOSO",
    "MALO",
    "MOVIMIENTOS",
    "NOMBRES",
    "SIN_EVALUAR",
    "CalidadContacto",
    "ConfigProcesamiento",
    "FiltroEMG",
    "MatrizCalibracion",
    "Procesador",
    "RMSDeslizante",
    "UmbralesCalidad",
    "calibrar",
    "calibrar_senal",
]


def calibrar_senal(datos, etiquetas, cfg: ConfigProcesamiento) -> MatrizCalibracion:
    """Calibra con una señal etiquetada pasando por la misma cadena que el tiempo real."""
    env, valida, _, _ = Procesador(cfg).procesar_todo(datos)
    return calibrar(env, valida, etiquetas)
