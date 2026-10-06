"""Registro de eventos y métricas como consultas puras, con tiempos exactos."""

import csv
import json

import numpy as np
import pytest

from synapvolit.registro import (
    Registro,
    exportar,
    frecuencia_mediana,
    indice_fatiga,
    interseccion,
    leer,
    restar,
    resumen,
)


def _ev(*filas):
    return [{"n": i, "t": t, "tipo": tipo, **campos} for i, (t, tipo, campos) in enumerate(filas)]


def test_operaciones_de_intervalos():
    assert interseccion([(0, 10), (20, 30)], [(5, 25)]) == [(5, 10), (20, 25)]
    assert restar([(0, 10)], [(2, 3), (5, 6)]) == [(0, 2), (3, 5), (6, 10)]
    assert restar([(0, 10)], [(-5, 20)]) == []


def test_minutos_efectivos_son_ejercicio_con_senal_menos_pausas():
    ev = _ev(
        (0, "sesion_inicio", {}),
        (0, "senal", {"valida": True}),
        (10, "ejercicio_inicio", {"id": 1, "movimiento": "extension"}),
        (12, "pausa", {}),
        (13, "reanudar", {}),
        (15, "senal", {"valida": False}),
        (18, "senal", {"valida": True}),
        (20, "ejercicio_fin", {"id": 1, "resultado": "acierto"}),
        (25, "ejercicio_inicio", {"id": 2, "movimiento": "flexion"}),
        (30, "sesion_fin", {}),
    )  # el ejercicio 2 nunca terminó: se cierra en sesion_fin
    r = resumen(ev, minutos_prescritos=1.0)
    # ejercicio 1: (10-15) + (18-20) - pausa(12-13) = 6 s; ejercicio 2: 25-30 con señal = 5 s
    assert r["minutos_efectivos"] == pytest.approx(11 / 60, abs=0.005)
    assert r["adherencia"] == pytest.approx(11 / 60, abs=0.01)
    assert r["aciertos"] == 1 and r["ejercicios"] == 1


def test_registro_en_disco_y_lectura_tolerante(tmp_path):
    reloj = iter(np.arange(0, 100, 0.5)).__next__
    reg = Registro(tmp_path, "PRUEBA01", reloj, fuente="simulada")
    reg.anotar("pausa")
    reg.volcar()
    reg.anotar("reanudar")
    reg.cerrar("cliente")
    with open(reg.archivo, "a", encoding="utf-8") as f:
        f.write('{"n": 99, "t": 1')  # línea cortada por un apagón
    ev = leer(reg.archivo)
    assert [e["tipo"] for e in ev] == ["sesion_inicio", "pausa", "reanudar", "sesion_fin"]
    assert reg.archivo.parent.name == "PRUEBA01"
    with pytest.raises(ValueError):
        Registro(tmp_path, "Juan Pérez", reloj)  # nunca un nombre: solo códigos


def test_exportacion_seudonimizada(tmp_path):
    ev = _ev(
        (0, "sesion_inicio", {"codigo": "P-07", "fecha": "2026-10-06", "hora": "10:15"}),
        (1, "senal", {"valida": True}),
        (2, "ejercicio_inicio", {"id": 1, "movimiento": "flexion"}),
        (
            4,
            "ejercicio_fin",
            {"id": 1, "resultado": "acierto", "rt_s": 0.8, "intensidad_pico": 0.7},
        ),
        (5, "sesion_fin", {}),
    )
    r = exportar(ev, tmp_path / "P-07", "s1")
    filas = list(csv.DictReader(open(r["archivos"][0], encoding="utf-8")))
    assert filas[0]["movimiento"] == "flexion" and filas[0]["t_inicio_s"] == "2"
    texto = (
        open(r["archivos"][0], encoding="utf-8").read()
        + open(r["archivos"][1], encoding="utf-8").read()
    )
    assert "10:15" not in texto and "P-07" not in texto  # sin hora ni código dentro de los archivos
    exportar(ev, tmp_path / "P-07", "s2")
    assert (
        len(list(csv.DictReader(open(r["archivos"][1], encoding="utf-8")))) == 2
    )  # resumen acumulado


def test_frecuencia_mediana_de_un_tono():
    fs = 2000.0
    t = np.arange(int(fs)) / fs
    x = np.sin(2 * np.pi * 120 * t) + 0.01 * np.random.default_rng(0).standard_normal(len(t))
    assert abs(frecuencia_mediana(x, fs) - 120) < 8  # resolución de Welch con 128 ms


def test_indice_de_fatiga_detecta_una_caida_de_1_por_ciento_por_minuto():
    ev = [
        {
            "tipo": "ejercicio_fin",
            "t": 30.0 * i,
            "movimiento": "flexion",
            "mdf_hz": 100 * (1 - 0.01 * 0.5 * i),
        }
        for i in range(20)
    ]
    f = indice_fatiga(ev)
    assert f["pendiente_pct_min"] == pytest.approx(-1.0, abs=0.05) and f["ic95"][1] < 0
    assert indice_fatiga(ev[:5])["pendiente_pct_min"] is None


def test_eventos_son_json_por_linea(tmp_path):
    reg = Registro(tmp_path, "ABC", iter(np.arange(0, 9, 1.0)).__next__)
    reg.cerrar("cliente")
    for linea in reg.archivo.read_text(encoding="utf-8").splitlines():
        assert json.loads(linea)["tipo"]
