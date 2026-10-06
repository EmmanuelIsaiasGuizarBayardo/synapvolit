"""Demostración sin hardware: calibra con los ensayos 1-3 y procesa en vivo los ensayos 4-7.

Uso::

    uv run python -m synapvolit.procesamiento
    uv run python -m synapvolit.procesamiento --escenario fallas --rapido

Calibrar y evaluar con ensayos distintos evita el resultado optimista de medir sobre los mismos
datos con que se calibró. Al final imprime la activación media de cada canal según el
movimiento real: si la cadena funciona, cada canal destaca en su propio movimiento.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from ..datasets import CLASES, cargar_senal
from ..transporte import ESCENARIOS, BufferCircular, Decodificador, SimuladorESP32, correr
from . import NOMBRES, ConfigProcesamiento, Procesador, calibrar_senal

LETRA = {-1: "?", 0: "B", 1: "D", 2: "M"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Calibración y procesamiento en vivo con la fuente simulada."
    )
    ap.add_argument("--csv", type=Path, default=Path("data/processed/grabmyo/s1_p01.csv"))
    ap.add_argument("--escenario", choices=sorted(ESCENARIOS), default="limpio")
    ap.add_argument("--segundos", type=float, default=60.0)
    ap.add_argument("--rapido", action="store_true", help="sin esperar: tan rápido como se pueda")
    a = ap.parse_args(argv)
    try:
        senal = cargar_senal(a.csv)
    except FileNotFoundError as e:  # arrancar siempre: decir qué falta y cómo se resuelve
        print(f"Falta la señal de demostración.\n  {e}\n  La descarga se explica en docs/datos.md.")
        return 2
    cfg = ConfigProcesamiento(fs=senal.fs, canales=senal.datos.shape[1])
    corte = len(senal.datos) * 3 // 7 // 20 * 20
    try:
        matriz = calibrar_senal(senal.datos[:corte], senal.etiquetas[:corte], cfg)
    except ValueError as e:
        print(f"No se pudo calibrar: {e}")
        return 2
    mov = ("ext", "flex", "pron", "sup")
    print(f"FUENTE SIMULADA: {senal.meta.get('dataset', '?')}, escenario '{a.escenario}'")
    print("Calibración (ensayos 1-3), µV de envolvente:")
    print("  canal     " + " ".join(f"{m:>7}" for m in mov))
    print("  reposo    " + " ".join(f"{v:7.1f}" for v in matriz.reposo_uv))
    print("  referencia" + " ".join(f"{v:7.1f}" for v in matriz.referencia_uv))
    sim = SimuladorESP32(senal.datos[corte:], senal.fs, escenario=ESCENARIOS[a.escenario])
    etiquetas = senal.etiquetas[corte:]
    buf = BufferCircular(cfg.canales, int(4 * cfg.fs))
    dec = Decodificador(buf)
    proc = Procesador(cfg, matriz, tope_uv=32767 * sim.lsb_uv)
    suma, cuenta = np.zeros((len(CLASES), cfg.canales)), np.zeros(len(CLASES))
    for i in range(int(a.segundos / 0.1)):
        correr(sim, dec.alimentar, 0.1, tiempo_real=not a.rapido)
        proc.actualizar(buf)
        real = etiquetas[(sim.k * sim.n - 1) % len(etiquetas)]
        if proc.activacion_valida.all():
            suma[real] += proc.activacion
            cuenta[real] += 1
        if (i + 1) % 5 == 0:
            barras = " ".join(
                f"{m} {v:4.2f} {'#' * int(min(v, 1) * 8):<8}" if ok else f"{m}  --- {'':<8}"
                for m, v, ok in zip(mov, proc.activacion, proc.activacion_valida, strict=True)
            )
            cal = "".join(LETRA[int(c)] for c in proc.calidad)
            print(f"t={(i + 1) / 10:5.1f} s | real: {CLASES[real]:<10} | {barras}| contacto {cal}")
    print("\nActivación media por movimiento real (filas) y canal (columnas):")
    print("  " + " " * 11 + " ".join(f"{m:>6}" for m in mov))
    for c, nombre in enumerate(CLASES):
        if cuenta[c]:
            print(f"  {nombre:<11}" + " ".join(f"{v:6.2f}" for v in suma[c] / cuenta[c]))
    finales = ", ".join(NOMBRES[int(c)] for c in proc.calidad)
    print(f"Contacto final: {finales}; atrasos {proc.atrasos}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
