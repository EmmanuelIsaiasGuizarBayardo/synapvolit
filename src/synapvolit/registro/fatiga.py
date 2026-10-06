"""Índice de fatiga mioeléctrica: caída de la frecuencia mediana (MDF) a lo largo de la sesión.

Con la fatiga, la velocidad de conducción de las fibras baja y el espectro de la sEMG se desplaza a
frecuencias menores; la MDF es el indicador clásico (De Luca, 1997; Cifrek et al., 2009). Aquí:

1. Al terminar cada ejercicio, el motor calcula la MDF del canal agonista en su último segundo
   (Welch, ventanas de 128 ms, banda de 20 a 450 Hz) y la guarda en el evento.
2. Cada MDF se normaliza contra la mediana de las tres primeras del mismo movimiento.
3. El índice es la pendiente de Theil-Sen (robusta a valores atípicos) de esa serie contra el
   tiempo de sesión, en % por minuto. Negativa = el espectro baja = señal compatible con fatiga.

Es EXPLORATORIO: la MDF se validó en contracciones sostenidas a fuerza constante, y aquí las
contracciones son breves y de fuerza variable. No está validada en niños con PC. Sirve como alerta
para el clínico, nunca como diagnóstico.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt, welch
from scipy.stats import theilslopes


def frecuencia_mediana(
    x_uv: np.ndarray, fs: float, banda: tuple[float, float] = (20.0, 450.0)
) -> float | None:
    """MDF de un segmento de un canal; ``None`` si es demasiado corto para estimarla."""
    if len(x_uv) < round(0.25 * fs):
        return None
    alto = min(banda[1], 0.45 * fs)
    sos = butter(4, [banda[0], alto], btype="bandpass", fs=fs, output="sos")
    f, p = welch(
        sosfiltfilt(sos, x_uv - np.mean(x_uv)), fs=fs, nperseg=min(len(x_uv), round(0.128 * fs))
    )
    en_banda = (f >= banda[0]) & (f <= alto)
    acum = np.cumsum(p[en_banda])
    if acum[-1] <= 0:
        return None
    return float(f[en_banda][np.searchsorted(acum, acum[-1] / 2)])


def indice_fatiga(eventos: list[dict], minimo: int = 6) -> dict:
    """Pendiente de la MDF normalizada (% por minuto) a partir de los eventos ``ejercicio_fin``."""
    t, rel, base = [], [], {}
    for e in eventos:
        if e["tipo"] != "ejercicio_fin" or e.get("mdf_hz") is None:
            continue
        mov = e.get("movimiento")
        base.setdefault(mov, []).append(e["mdf_hz"])
        if len(base[mov]) <= 3:
            continue  # las tres primeras de cada movimiento forman la referencia
        t.append(e["t"] / 60.0)
        rel.append(100.0 * e["mdf_hz"] / np.median(base[mov][:3]))
    if len(t) < minimo or max(t) - min(t) < 2.0:
        return {
            "pendiente_pct_min": None,
            "n": len(t),
            "motivo": "datos insuficientes (≥6 ejercicios en ≥2 min)",
        }
    p, _, bajo, alto = theilslopes(rel, t)
    return {
        "pendiente_pct_min": round(float(p), 2),
        "ic95": [round(float(bajo), 2), round(float(alto), 2)],
        "n": len(t),
    }
