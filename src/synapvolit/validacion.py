"""Validación entre sesiones con GRABMyo: ¿cuánto se degrada el decodificador de un día a otro?

Uso::

    uv run python -m synapvolit.validacion --participantes 1 2 3 --sesiones 1 2

Para cada participante, con los canales elegidos en la sesión 1 (los electrodos de GRABMyo se
colocan en las mismas posiciones anatómicas cada día), compara cinco escenarios. Todos se evalúan
con la cadena del tiempo real (decisiones a 8 Hz):

=================  ===========================================  ==========================
Escenario          Entrena con                                   Evalúa con
=================  ===========================================  ==========================
intra S1           S1, ensayos 1-3                               S1, ensayos 4-7
entre sesiones     S1, ensayos 1-7 (el perfil guardado)          S2, ensayos 2-7
verificación       el perfil, con los criterios del motor        S2, ensayo 1 (~28 s)
adaptado           perfil + el ensayo 1 de S2 como datos extra   S2, ensayos 2-7
recalibrado        S2, ensayos 1-3                               S2, ensayos 4-7
=================  ===========================================  ==========================

La pregunta clínica: si la verificación rechaza las sesiones donde "entre sesiones" cae, es un
buen filtro; si además "adaptado" recupera casi lo de "recalibrado", 30 s bastan cada día.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np

from .clasificacion.evaluacion import entrenar_desde, evaluar_flujo, rasgos_de
from .clasificacion.verificacion import verificar_perfil
from .datasets.grabmyo import VERSION_DATASET, construir_flujo, elegir_canales, leer_sesion
from .procesamiento import ConfigProcesamiento

ESCENARIOS = ("intra S1", "entre sesiones", "adaptado", "recalibrado")


def verificar_sumas(raiz: Path) -> tuple[int, list[str]]:
    """Compara lo descargado con ``SHA256SUMS.txt`` de PhysioNet (si está en ``raiz``)."""
    sumas = raiz / "SHA256SUMS.txt"
    if not sumas.exists():
        return 0, []
    revisados, malos = 0, []
    for linea in sumas.read_text(encoding="utf-8").splitlines():
        partes = linea.split(maxsplit=1)
        if len(partes) != 2 or not partes[1].endswith((".dat", ".hea")):
            continue
        ruta = raiz / partes[1].strip()
        if not ruta.exists():
            continue
        revisados += 1
        if hashlib.sha256(ruta.read_bytes()).hexdigest() != partes[0].lower():
            malos.append(partes[1].strip())
    return revisados, malos


def validar_participante(raiz: Path, p: int, s1: int, s2: int, cfg: ConfigProcesamiento) -> dict:
    seg1, fs = leer_sesion(raiz, s1, p)
    seg2, _ = leer_sesion(raiz, s2, p)
    canales, _ = elegir_canales(seg1, fs)

    def flujo(seg, ensayos):
        return construir_flujo(seg, fs, canales, ensayos, cfg.fs)

    r = {"canales": [f"F{c + 1}" for c in canales]}
    # intra S1
    m, mod = entrenar_desde([rasgos_de(*flujo(seg1, range(3)), cfg)])
    r["intra S1"] = evaluar_flujo(mod, m, *flujo(seg1, range(3, 7)), cfg)["exactitud"]
    # perfil guardado: toda la sesión 1
    matriz, modelo = entrenar_desde([rasgos_de(*flujo(seg1, range(7)), cfg)])
    x2, y2 = flujo(seg2, range(1, 7))
    r["entre sesiones"] = evaluar_flujo(modelo, matriz, x2, y2, cfg)["exactitud"]
    # verificación con el ensayo 1 de S2 (los mismos criterios que el motor)
    v = rasgos_de(*flujo(seg2, [0]), cfg)
    ver = verificar_perfil(
        matriz, modelo, v["env"], v["envv"], v["y"], v["rasgos"], v["etq"], v["tasa"]
    )
    r["verificacion"] = ver
    # adaptado: matriz de hoy (ensayo 1 de S2) y LDA con S1 + ese ensayo
    m_hoy, mod_ad = entrenar_desde([v, rasgos_de(*flujo(seg1, range(7)), cfg)])
    r["adaptado"] = evaluar_flujo(mod_ad, m_hoy, x2, y2, cfg)["exactitud"]
    # recalibrado: calibración completa del día 2
    m3, mod3 = entrenar_desde([rasgos_de(*flujo(seg2, range(3)), cfg)])
    r["recalibrado"] = evaluar_flujo(mod3, m3, *flujo(seg2, range(3, 7)), cfg)["exactitud"]
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Validación entre sesiones del decodificador con GRABMyo."
    )
    ap.add_argument("--raiz", type=Path, default=Path("data/raw/grabmyo") / VERSION_DATASET)
    ap.add_argument("--participantes", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--sesiones", type=int, nargs=2, default=[1, 2], metavar=("CALIBRA", "EVALUA"))
    a = ap.parse_args(argv)
    revisados, malos = verificar_sumas(a.raiz)
    if malos:
        print(f"Archivos dañados (no coinciden con SHA256SUMS.txt): {', '.join(malos[:5])}")
        return 2
    print(
        f"Integridad: {revisados} archivos verificados con SHA256SUMS.txt"
        if revisados
        else "Integridad: sin SHA256SUMS.txt en la carpeta; no se verificó"
    )
    cfg = ConfigProcesamiento()
    filas = {}
    for p in a.participantes:
        try:
            filas[p] = r = validar_participante(a.raiz, p, *a.sesiones, cfg)
        except FileNotFoundError as e:
            print(f"Participante {p}: se omite ({e})")
            continue
        v = r["verificacion"]
        print(f"\nParticipante {p} (canales {', '.join(r['canales'])})")
        for esc in ESCENARIOS:
            print(f"  {esc:<15} {r[esc]:.0%}")
        estado = "PASA" if v["ok"] else "NO PASA"
        print(
            f"  verificación    {estado}: exactitud {v['exactitud']:.0%}, amplitud "
            + " ".join(f"{x:.2f}" for x in v["razon_amplitud"])
        )
    if len(filas) > 1:
        print("\nPromedio (desviación estándar) entre participantes:")
        for esc in ESCENARIOS:
            vals = np.array([f[esc] for f in filas.values()])
            print(f"  {esc:<15} {vals.mean():.0%} ({vals.std(ddof=1):.0%})")
        pasan = sum(f["verificacion"]["ok"] for f in filas.values())
        print(f"  la verificación pasó en {pasan} de {len(filas)} participantes")
    return 0 if filas else 2


if __name__ == "__main__":
    sys.exit(main())
