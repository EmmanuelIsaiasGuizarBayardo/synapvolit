"""Clasificación multicanal: LDA, intensidad por patrón y decisión suavizada."""

from .decisor import Decisor
from .intensidad import ANTAGONISTA, Intensidades
from .modelo import CLASES, ModeloLDA, entrenar, evaluar

__all__ = ["ANTAGONISTA", "CLASES", "Decisor", "Intensidades", "ModeloLDA", "entrenar", "evaluar"]
