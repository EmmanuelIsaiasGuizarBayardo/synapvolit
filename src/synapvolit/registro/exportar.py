"""Exportación al cerrar la sesión: CSV limpios construidos solo desde los eventos.

* ``<codigo>/<sesion>_ejercicios.csv``: una fila por ejercicio, con tiempos relativos al inicio.
* ``<codigo>/resumen_sesiones.csv``: una fila por sesión (se agrega a las anteriores).

Son **seudonimizados**, no anónimos: no contienen nombres ni horas, pero el código del paciente
los vincula con su expediente en la clínica. Quien tenga la tabla de códigos puede reidentificar.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .metricas import resumen

COLUMNAS_EJERCICIO = [
    "ejercicio",
    "t_inicio_s",
    "t_fin_s",
    "movimiento",
    "resultado",
    "tiempo_reaccion_s",
    "intensidad_pico",
    "coactivacion_media",
    "fraccion_senal_valida",
    "mdf_hz",
]
COLUMNAS_RESUMEN = [
    "sesion",
    "fecha",
    "minutos_sesion",
    "minutos_efectivos",
    "minutos_prescritos",
    "adherencia",
    "ejercicios",
    "aciertos",
    "fallos",
    "sin_respuesta",
    "fatiga_pct_min",
    "fatiga_n",
]


def exportar(
    eventos: list[dict], carpeta: Path, sesion: str, minutos_prescritos: float = 30.0
) -> dict:
    """Escribe los dos CSV y devuelve el resumen con las rutas escritas."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    inicios = {e["id"]: e for e in eventos if e["tipo"] == "ejercicio_inicio"}
    filas = []
    for e in eventos:
        if e["tipo"] != "ejercicio_fin" or e.get("id") not in inicios:
            continue
        i = inicios[e["id"]]
        filas.append(
            {
                "ejercicio": e["id"],
                "t_inicio_s": i["t"],
                "t_fin_s": e["t"],
                "movimiento": i.get("movimiento"),
                "resultado": e.get("resultado"),
                "tiempo_reaccion_s": e.get("rt_s"),
                "intensidad_pico": e.get("intensidad_pico"),
                "coactivacion_media": e.get("coactivacion_media"),
                "fraccion_senal_valida": e.get("fraccion_valida"),
                "mdf_hz": e.get("mdf_hz"),
            }
        )
    ruta_ej = carpeta / f"{sesion}_ejercicios.csv"
    with open(ruta_ej, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLUMNAS_EJERCICIO)
        w.writeheader()
        w.writerows({k: ("" if v is None else v) for k, v in fila.items()} for fila in filas)
    r = resumen(eventos, minutos_prescritos)
    inicio = eventos[0] if eventos and eventos[0]["tipo"] == "sesion_inicio" else {}
    fila = {
        "sesion": sesion,
        "fecha": inicio.get("fecha", ""),
        **{k: r.get(k) for k in COLUMNAS_RESUMEN[2:10]},
        "fatiga_pct_min": r["fatiga"].get("pendiente_pct_min"),
        "fatiga_n": r["fatiga"].get("n"),
    }
    ruta_res = carpeta / "resumen_sesiones.csv"
    nuevo = not ruta_res.exists()
    with open(ruta_res, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLUMNAS_RESUMEN)
        if nuevo:
            w.writeheader()
        w.writerow({k: ("" if v is None else v) for k, v in fila.items()})
    return {**r, "archivos": [str(ruta_ej), str(ruta_res)]}
