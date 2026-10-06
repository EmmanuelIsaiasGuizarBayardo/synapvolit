"""LDA multicanal: se entrena con scikit-learn y se evalúa en línea con álgebra preasignada.

Rasgos: ``log1p(RMS)`` y ``log1p(DASDV)`` de cada canal en la ventana de 150 ms (8 rasgos con
4 canales). El logaritmo vuelve más gaussianas las amplitudes de sEMG, que es lo que supone el LDA.

Entrenamiento: ``LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")``. El encogimiento
de Ledoit-Wolf estabiliza la covarianza cuando hay pocos datos y rasgos correlacionados, como
la RMS y la DASDV de un mismo canal.

Inferencia: el LDA es lineal, así que cada decisión es ``W @ x + b`` (5 × 8 multiplicaciones) y
un softmax. No se llama a ``predict_proba`` en el bucle: su validación de entradas y sus arreglos
nuevos cuestan más que el cálculo. Una prueba verifica que el resultado es idéntico al de
scikit-learn, que actúa como implementación de referencia independiente.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

CLASES = ("reposo", "extension", "flexion", "pronacion", "supinacion")
DESCANSO = 5  # etiqueta de los descansos entre repeticiones: se entrena como reposo


@dataclass(frozen=True)
class ModeloLDA:
    """Parámetros del LDA ya entrenado (solo lectura)."""

    w: np.ndarray  # (clases, rasgos)
    b: np.ndarray  # (clases,)
    clases: np.ndarray  # etiqueta de cada fila de w
    exactitud: float | None = None  # validada por repeticiones; None si no hay con qué estimarla

    def puntajes(self, x: np.ndarray, out: np.ndarray) -> np.ndarray:
        """Función discriminante de cada clase, escrita en ``out``."""
        np.dot(self.w, x, out=out)
        out += self.b
        return out

    def probabilidades(self, x: np.ndarray, out: np.ndarray) -> np.ndarray:
        """Probabilidad posterior de cada clase (softmax estable, en el lugar)."""
        self.puntajes(x, out)
        out -= out.max()
        np.exp(out, out=out)
        out /= out.sum()
        return out


def _grupos(etiquetas: np.ndarray, tasa: float, trozo_s: float = 1.0) -> np.ndarray:
    """Un grupo por repetición; el reposo, que es un solo tramo largo, se parte en trozos de 1 s."""
    grupos = np.empty(len(etiquetas), np.int64)
    bordes = np.r_[0, np.flatnonzero(np.diff(etiquetas)) + 1, len(etiquetas)]
    g, trozo = 0, max(1, round(trozo_s * tasa))
    for i, f in zip(bordes[:-1], bordes[1:], strict=True):
        paso = trozo if etiquetas[i] == 0 else f - i
        for k in range(i, f, paso):
            grupos[k : min(k + paso, f)] = g
            g += 1
    return grupos


def entrenar(
    rasgos: np.ndarray, etiquetas: np.ndarray, tasa: float, *, quitar_inicio_s: float = 0.5
) -> ModeloLDA:
    """Entrena con rasgos etiquetados (0 reposo, 1-4 movimientos, 5 descanso; -1 = ignorar).

    Se descartan los primeros ``quitar_inicio_s`` de cada repetición de movimiento y de cada
    descanso (a lo más el 30% del tramo): ahí la persona todavía está contrayendo o relajando y
    la etiqueta no describe la señal.

    La exactitud se estima con validación cruzada agrupada por repetición
    (``StratifiedGroupKFold``):
    ninguna ventana de una repetición se usa a la vez para entrenar y evaluar. Si algún movimiento
    tiene una sola repetición, no hay forma honesta de estimarla y queda en ``None``.

    Raises
    ------
    ValueError
        Si falta alguna de las cinco clases.
    """
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.model_selection import StratifiedGroupKFold, cross_val_score

    usar = etiquetas >= 0
    quitar = round(quitar_inicio_s * tasa)
    bordes = np.r_[0, np.flatnonzero(np.diff(etiquetas)) + 1, len(etiquetas)]
    for i, f in zip(bordes[:-1], bordes[1:], strict=True):
        if etiquetas[i] > 0:  # en repeticiones cortas se quita a lo más el 30% inicial
            usar[i : i + min(quitar, int(0.3 * (f - i)))] = False
    x = rasgos[usar].astype(np.float64)
    y = np.where(etiquetas[usar] == DESCANSO, 0, etiquetas[usar])  # el descanso es reposo
    faltan = [CLASES[c] for c in range(len(CLASES)) if not np.any(y == c)]
    if faltan:
        raise ValueError(f"no hay datos de {', '.join(faltan)} para entrenar")
    lda = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto").fit(x, y)
    grupos = _grupos(etiquetas, tasa)[usar]
    reps = [len(np.unique(grupos[y == c])) for c in range(1, len(CLASES))]
    exactitud = None
    if min(reps) >= 2:
        cv = StratifiedGroupKFold(n_splits=min(3, min(reps)))
        modelo = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
        exactitud = float(cross_val_score(modelo, x, y, groups=grupos, cv=cv).mean())
    return ModeloLDA(lda.coef_.copy(), lda.intercept_.copy(), lda.classes_.copy(), exactitud)
