"""Conversión de GRABMyo (PhysioNet, CC BY 4.0) al CSV de cuatro canales del simulador.

GRABMyo registra 43 adultos sanos en tres sesiones con dos anillos de 8 pares bipolares en el
antebrazo, a 2048 Hz. Incluye justo los movimientos de WristQuest: extensión (gesto 11),
flexión (12), supinación (13), pronación (14) y reposo (17), con 7 ensayos de 5 s cada uno.

Qué hace esta conversión, y nada más:

1. Lee los originales de ``data/raw/`` (nunca escribe ahí).
2. Elige 4 de los 16 canales del antebrazo, uno por movimiento, por especificidad de su RMS
   (o los que indique ``--canales``). Los anillos no apuntan a músculos concretos: el canal
   "de pronación" es el par que más se activa en pronación, no el pronador redondo aislado.
3. Encadena por ensayo: 2 s de reposo y luego el movimiento, para extensión, flexión,
   pronación y supinación. Resta la media de cada segmento y une los segmentos con
   transiciones de coseno de 20 ms, para no introducir escalones que no están en la señal.
4. Remuestrea a ``--fs`` (2000 Hz por defecto) con filtro polifásico antialias.
5. Escribe en ``data/processed/`` el CSV y un JSON con toda la procedencia.

Uso::

    uv run python -m synapvolit.datasets.grabmyo --sesion 1 --participante 1
"""

from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import resample_poly

GESTOS = {11: 1, 12: 2, 14: 3, 13: 4}  # gesto de GRABMyo → clase del contrato (orden del flujo)
REPOSO = 17
CANALES_ANTEBRAZO = 16  # F1-F16: columnas 1-16 del registro
RANURAS = ("extension", "flexion", "pronacion", "supinacion")  # c0..c3, como en el brazalete
UNIDADES_A_UV = {"uV": 1.0, "µV": 1.0, "mV": 1e3, "V": 1e6}
VERSION_DATASET = "1.1.0"
DOI = "10.13026/89dm-f662"


def ruta_registro(raiz: Path, sesion: int, part: int, gesto: int, ensayo: int) -> Path:
    """Ruta (sin extensión) de un registro WFDB de GRABMyo."""
    base = f"session{sesion}_participant{part}"
    return raiz / f"Session{sesion}" / base / f"{base}_gesture{gesto}_trial{ensayo}"


def leer_registro(ruta: Path) -> tuple[np.ndarray, float]:
    """Canales del antebrazo en µV y su frecuencia de muestreo."""
    import wfdb  # importación local: solo la conversión depende de wfdb

    rec = wfdb.rdrecord(str(ruta))
    unidad = (rec.units or ["mV"])[0]
    if unidad not in UNIDADES_A_UV:
        raise ValueError(f"unidad desconocida en {ruta}: {unidad}")
    x = rec.p_signal[:, :CANALES_ANTEBRAZO] * UNIDADES_A_UV[unidad]
    return x - x.mean(axis=0), float(rec.fs)


def elegir_canales(segmentos: dict[int, list[np.ndarray]]) -> tuple[list[int], dict]:
    """Un canal por movimiento: el que más se activa en él y menos en los otros tres.

    La activación de cada canal es su RMS en el movimiento dividido entre su RMS en reposo; la
    especificidad divide esa activación entre la media de las de los otros movimientos. Se
    asigna de forma voraz, primero la pareja canal-movimiento más específica.
    """
    rms = {
        g: np.mean([np.sqrt(np.mean(s**2, axis=0)) for s in segs], axis=0)
        for g, segs in segmentos.items()
    }
    act = {g: rms[g] / rms[REPOSO] for g in GESTOS}
    esp = {g: act[g] / np.mean([act[h] for h in GESTOS if h != g], axis=0) for g in GESTOS}
    asignado: dict[int, int] = {}
    libres = set(range(CANALES_ANTEBRAZO))
    while len(asignado) < len(GESTOS):
        g, c = max(
            ((g, c) for g in GESTOS if g not in asignado for c in libres),
            key=lambda gc: esp[gc[0]][gc[1]],
        )
        asignado[g] = c
        libres.discard(c)
    canales = [asignado[g] for g in sorted(GESTOS, key=GESTOS.get)]
    informe = {
        RANURAS[i]: {"canal": f"F{c + 1}", "especificidad": round(float(esp[g][c]), 2)}
        for i, (g, c) in enumerate((g, asignado[g]) for g in sorted(GESTOS, key=GESTOS.get))
    }
    return canales, informe


def _unir(trozos: list[np.ndarray], m: int) -> np.ndarray:
    """Concatena con transiciones de coseno de ``m`` muestras entre trozos consecutivos."""
    rampa = 0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, m))[:, None]
    salida = [trozos[0]]
    for t in trozos[1:]:
        prev = salida[-1]
        mezcla = prev[-m:] * (1 - rampa) + t[:m] * rampa
        salida[-1] = prev[:-m]
        salida += [mezcla, t[m:]]
    return np.concatenate(salida)


def convertir(
    raiz: Path,
    destino: Path,
    sesion: int,
    participante: int,
    *,
    ensayos: range = range(1, 8),
    canales: list[int] | None = None,
    fs_salida: float = 2000.0,
    reposo_s: float = 2.0,
) -> Path:
    """Convierte un participante y una sesión; devuelve la ruta del CSV escrito."""
    seg: dict[int, list[np.ndarray]] = {g: [] for g in (*GESTOS, REPOSO)}
    fs = None
    for g in seg:
        for t in ensayos:
            ruta = ruta_registro(raiz, sesion, participante, g, t)
            if not ruta.with_suffix(".hea").exists():
                raise FileNotFoundError(
                    f"Falta {ruta}.hea: revisa la descarga en data/raw/ (docs/datos.md)"
                )
            x, fs = leer_registro(ruta)
            seg[g].append(x)
    informe = None
    if canales is None:
        canales, informe = elegir_canales(seg)
    m = round(0.020 * fs)
    trozos, etiquetas = [], []
    for i in range(len(ensayos)):
        for g, clase in GESTOS.items():
            rep = seg[REPOSO][i][: round(reposo_s * fs), canales]
            mov = seg[g][i][:, canales]
            trozos += [rep - rep.mean(axis=0), mov - mov.mean(axis=0)]
            etiquetas += [np.zeros(len(rep), np.int8), np.full(len(mov), clase, np.int8)]
    x = _unir(trozos, m)
    # cada transición toma la etiqueta del segmento que entra: m muestras menos al final de cada uno
    y = np.concatenate([e[:-m] for e in etiquetas[:-1]] + [etiquetas[-1]])
    r = Fraction(fs_salida / fs).limit_denominator(1000)
    x = resample_poly(x, r.numerator, r.denominator, axis=0).astype(np.float32)
    idx = np.minimum((np.arange(len(x)) * fs / fs_salida).astype(np.int64), len(y) - 1)
    y = y[idx]
    destino.mkdir(parents=True, exist_ok=True)
    csv = destino / f"s{sesion}_p{participante:02d}.csv"
    tabla = pd.DataFrame(x, columns=[f"c{i}" for i in range(4)])
    tabla.insert(0, "etiqueta", y)
    tabla.to_csv(csv, index=False, float_format="%.2f")
    meta = {
        "dataset": "GRABMyo",
        "version": VERSION_DATASET,
        "doi": DOI,
        "licencia": "CC BY 4.0",
        "sesion": sesion,
        "participante": participante,
        "ensayos": list(ensayos),
        "fs": fs_salida,
        "fs_original": fs,
        "unidades": "uV",
        "canales_origen": [f"F{c + 1}" for c in canales],
        "ranuras": list(RANURAS),
        "seleccion": informe or "manual",
        "clases": {"0": "reposo", **{str(v): RANURAS[v - 1] for v in GESTOS.values()}},
        "transformaciones": [
            "media restada por segmento",
            "transiciones de coseno de 20 ms",
            f"remuestreo polifásico {fs:g} → {fs_salida:g} Hz",
            f"reposo recortado a {reposo_s:g} s",
        ],
    }
    csv.with_suffix(".json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return csv


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Convierte GRABMyo al CSV de cuatro canales del simulador."
    )
    ap.add_argument("--raiz", type=Path, default=Path("data/raw/grabmyo") / VERSION_DATASET)
    ap.add_argument("--destino", type=Path, default=Path("data/processed/grabmyo"))
    ap.add_argument("--sesion", type=int, default=1)
    ap.add_argument("--participante", type=int, default=1)
    ap.add_argument("--canales", default="auto", help='"auto" o cuatro canales como F3,F7,F1,F5')
    ap.add_argument("--fs", type=float, default=2000.0)
    a = ap.parse_args(argv)
    canales = (
        None
        if a.canales == "auto"
        else [int(c.strip().lstrip("Ff")) - 1 for c in a.canales.split(",")]
    )
    try:
        csv = convertir(
            a.raiz, a.destino, a.sesion, a.participante, canales=canales, fs_salida=a.fs
        )
    except FileNotFoundError as e:
        print(f"No se pudo convertir: {e}", file=sys.stderr)
        return 2
    meta = json.loads(csv.with_suffix(".json").read_text(encoding="utf-8"))
    print(f"Escrito {csv} ({meta['fs']:g} Hz)")
    for ranura, info in meta["seleccion"].items() if isinstance(meta["seleccion"], dict) else []:
        print(f"  {ranura:<11} ← {info['canal']:<4} especificidad {info['especificidad']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
