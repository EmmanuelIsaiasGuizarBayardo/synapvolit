"""Evaluación honesta del decodificador con datos reales y la cadena en línea completa.

Uso::

    uv run python -m synapvolit.clasificacion

Calibra y entrena con los ensayos 1-3 (como lo haría la calibración guiada) y después reproduce
los ensayos 4-7 por la ruta real: simulador → bytes → decodificador → procesador → decisor, con
decisiones a 8 Hz. Compara cada decisión con el movimiento real. Se ignoran los 0.5 s que siguen
a cada cambio de movimiento, porque ahí la persona todavía está empezando o terminando.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

from ..datasets import cargar_senal
from ..procesamiento import ConfigProcesamiento, Procesador, calibrar
from ..transporte import BufferCircular, Decodificador, SimuladorESP32, correr
from . import CLASES, Decisor, entrenar


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Evalúa el decodificador LDA con la ruta en línea completa."
    )
    ap.add_argument("--csv", type=Path, default=Path("data/processed/grabmyo/s1_p01.csv"))
    a = ap.parse_args(argv)
    try:
        s = cargar_senal(a.csv)
    except FileNotFoundError as e:
        print(f"Falta la señal de demostración.\n  {e}\n  La descarga se explica en docs/datos.md.")
        return 2
    cfg = ConfigProcesamiento(fs=s.fs, canales=s.datos.shape[1])
    paso = round(0.010 * s.fs)  # un paso del bucle: 10 ms
    corte = len(s.datos) * 3 // 7 // paso * paso
    env, envv, rasgos, rv = Procesador(cfg).procesar_todo(s.datos[:corte])
    matriz = calibrar(env, envv, s.etiquetas[:corte])
    etq = np.where(rv, s.etiquetas[:corte], -1)[::paso].astype(np.int8)
    modelo = entrenar(rasgos[::paso], etq, s.fs / paso)
    exac = "no disponible" if modelo.exactitud is None else f"{modelo.exactitud:.0%}"
    print(f"Entrenado con los ensayos 1-3. Exactitud validada por repeticiones: {exac}")

    sim = SimuladorESP32(s.datos[corte:], s.fs)
    reales = s.etiquetas[corte:]
    buf = BufferCircular(cfg.canales, int(4 * s.fs))
    dec = Decodificador(buf, fs=s.fs)
    proc = Procesador(cfg, matriz)
    decisor = Decisor(modelo, matriz)
    confusion = np.zeros((5, 5), int)
    inten = [[] for _ in range(5)]
    ultimo_cambio, latencias, buscando = 0, [], None
    t_proc = 0.0
    pasos = len(reales) // paso
    for k in range(pasos):
        correr(sim, dec.alimentar, paso / s.fs, tiempo_real=False)
        t0 = time.perf_counter()
        proc.actualizar(buf)
        decisor.actualizar(proc.rasgos, proc.env_uv, proc.rasgos_validos)
        t_proc += time.perf_counter() - t0
        i = (k + 1) * paso - 1
        if i > 0 and reales[i] != reales[i - paso]:
            ultimo_cambio = i
            buscando = (int(reales[i]), i) if reales[i] > 0 else None
        if k % round(0.125 * s.fs / paso):  # decisiones a 8 Hz
            continue
        d = decisor.decision()
        if d is None:
            continue
        clase, _, intensidad, _ = d
        if (
            buscando and clase == buscando[0]
        ):  # latencia: del inicio del movimiento a la 1.ª decisión correcta
            latencias.append((i - buscando[1]) / s.fs)
            buscando = None
        if i - ultimo_cambio < 0.5 * s.fs:
            continue
        confusion[reales[i], clase] += 1
        if clase == reales[i] and clase > 0:
            inten[clase].append(intensidad)
    total = confusion.sum()
    print(f"\nDecisiones en línea, ensayos 4-7 ({total} decisiones a 8 Hz):")
    print(f"  exactitud global: {np.trace(confusion) / total:.0%}")
    print("  real \\ decidido " + " ".join(f"{c[:5]:>6}" for c in CLASES))
    for r in range(5):
        print(f"  {CLASES[r]:<16}" + " ".join(f"{v:6d}" for v in confusion[r]))
    sens = [confusion[r, r] / max(confusion[r].sum(), 1) for r in range(5)]
    print("  sensibilidad: " + ", ".join(f"{CLASES[r]} {sens[r]:.0%}" for r in range(5)))
    print(
        "  intensidad media al acertar: "
        + ", ".join(f"{CLASES[c]} {np.mean(inten[c]):.2f}" for c in range(1, 5) if inten[c])
    )
    if latencias:
        lat = np.median(latencias) * 1000
        print(f"  latencia hasta la primera decisión correcta: mediana {lat:.0f} ms")
    print(
        f"  costo del procesamiento y la decisión: {t_proc / pasos * 1e6:.0f} µs por paso de 10 ms"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
