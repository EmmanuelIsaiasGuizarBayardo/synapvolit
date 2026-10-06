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


def _rasgos(segmentos: dict[int, list[np.ndarray]], ventana: int):
    """log-RMS por ventana no traslapada, con su clase y su ensayo (para validar sin fuga)."""
    xs, ys, grupos = [], [], []
    for g, segs in segmentos.items():
        clase = 0 if g == REPOSO else GESTOS[g]
        for t, s in enumerate(segs):
            nv = len(s) // ventana
            v = s[: nv * ventana].reshape(nv, ventana, -1)
            xs.append(np.log(np.sqrt(np.mean(v**2, axis=1)) + 1e-9))
            ys.append(np.full(nv, clase))
            grupos.append(np.full(nv, t))
    return np.vstack(xs), np.concatenate(ys), np.concatenate(grupos)


def elegir_canales(segmentos: dict[int, list[np.ndarray]], fs: float) -> tuple[list[int], dict]:
    """Los cuatro canales que mejor separan las cinco clases, y qué movimiento representa cada uno.

    1. Selección hacia adelante: se agrega, uno a uno, el canal que más sube la exactitud de un
       LDA sobre log-RMS en ventanas de 150 ms. La validación agrupa por ensayo (GroupKFold): las
       ventanas de un mismo ensayo nunca están a la vez en entrenamiento y en evaluación.
    2. Asignación: cada canal elegido se asigna a un movimiento con el algoritmo húngaro,
       maximizando su activación relativa (RMS en el movimiento entre el máximo de ese canal en
       los cuatro movimientos). Es una asignación óptima global, no voraz.
    """
    from scipy.optimize import linear_sum_assignment
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.model_selection import GroupKFold, cross_val_score

    x, y, grupos = _rasgos(segmentos, round(0.150 * fs))
    cv = GroupKFold(n_splits=min(5, len(np.unique(grupos))))
    elegidos: list[int] = []
    exactitud = 0.0
    while len(elegidos) < len(GESTOS):
        puntajes = {
            c: cross_val_score(
                LinearDiscriminantAnalysis(), x[:, [*elegidos, c]], y, groups=grupos, cv=cv
            ).mean()
            for c in range(CANALES_ANTEBRAZO)
            if c not in elegidos
        }
        mejor = max(puntajes, key=puntajes.get)
        elegidos.append(mejor)
        exactitud = puntajes[mejor]
    orden = sorted(GESTOS, key=GESTOS.get)  # extensión, flexión, pronación, supinación

    def rms(segs: list[np.ndarray]) -> np.ndarray:
        return np.mean([np.sqrt(np.mean(s[:, elegidos] ** 2, axis=0)) for s in segs], axis=0)

    reposo = rms(segmentos[REPOSO])
    act = np.array([rms(segmentos[g]) / reposo for g in orden])  # (movimiento, canal elegido)
    rel = act / act.max(axis=0)
    _, col = linear_sum_assignment(-rel)
    canales = [elegidos[col[i]] for i in range(len(orden))]
    informe = {"exactitud_lda_5_clases": round(float(exactitud), 3)}
    for i, ranura in enumerate(RANURAS):
        informe[ranura] = {
            "canal": f"F{canales[i] + 1}",
            "activacion_relativa": round(float(rel[i, col[i]]), 2),
            "activacion_sobre_reposo": round(float(act[i, col[i]]), 2),
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
        canales, informe = elegir_canales(seg, fs)
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
    sel = meta["seleccion"]
    if isinstance(sel, dict):
        exac = sel["exactitud_lda_5_clases"]
        print(f"  exactitud LDA con 4 canales (5 clases, validada por ensayo): {exac:.0%}")
        for ranura in RANURAS:
            i = sel[ranura]
            rel, rep = i["activacion_relativa"], i["activacion_sobre_reposo"]
            txt = f"activación relativa {rel:.2f}, {rep:.1f}× el reposo"
            print(f"  {ranura:<11} <- {i['canal']:<4} {txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
