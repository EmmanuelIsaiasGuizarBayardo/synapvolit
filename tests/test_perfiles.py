"""Perfil del paciente: guardado atómico, compatibilidad de rasgos y verificación."""

import json

import numpy as np
import pytest

from synapvolit.clasificacion import ModeloLDA
from synapvolit.procesamiento import BUENO, ConfigProcesamiento, MatrizCalibracion
from synapvolit.registro import cargar_perfil, guardar_perfil
from synapvolit.servidor.calibracion import ERROR, LISTA, MaquinaCalibracion, Protocolo

CORTO = Protocolo(reposo_s=2.0, preparar_s=0.2, contraccion_s=1.0, descanso_s=1.0, repeticiones=2)
BIEN = np.full(4, BUENO, np.int8)


def _correr(maq, ganancia=1.0, permutar=False, hasta=60):
    t, rng = 0.0, np.random.default_rng(0)
    while t < hasta and maq.fase not in (LISTA, ERROR):
        env = np.full(4, 5.0)
        if maq.objetivo:
            c = maq.objetivo - 1
            env[(c + 1) % 4 if permutar else c] = (
                5.0 + 95.0 * ganancia
            )  # permutar = electrodos movidos
        rasgos = np.r_[np.log1p(env), np.log1p(env * 0.3)] + rng.normal(0, 0.05, 8)
        maq.avanzar(t, env, np.ones(4, bool), BIEN, True, rasgos, True)
        t += 0.01
    return maq


def _calibrado():
    maq = MaquinaCalibracion(4)
    maq.iniciar(CORTO, 0.0)
    return _correr(maq)


def test_guardar_y_cargar_ida_y_vuelta(tmp_path):
    maq, cfg = _calibrado(), ConfigProcesamiento()
    guardar_perfil(tmp_path, maq.matriz, maq.modelo, cfg)
    matriz, modelo, info = cargar_perfil(tmp_path, cfg)
    assert np.allclose(matriz.mvc_uv, maq.matriz.mvc_uv) and np.allclose(modelo.w, maq.modelo.w)
    assert info["exactitud"] == maq.modelo.exactitud and not list(tmp_path.glob("*.tmp"))
    assert cargar_perfil(tmp_path / "otro", cfg) is None


def test_perfil_de_otra_configuracion_se_rechaza(tmp_path):
    maq = _calibrado()
    guardar_perfil(tmp_path, maq.matriz, maq.modelo, ConfigProcesamiento(fs=2000.0))
    with pytest.raises(ValueError, match="fs"):
        cargar_perfil(tmp_path, ConfigProcesamiento(fs=3000.0))
    (tmp_path / "perfil.json").write_text("{no es json", encoding="utf-8")
    with pytest.raises(ValueError, match="dañado"):
        cargar_perfil(tmp_path, ConfigProcesamiento())


def test_verificacion_pasa_con_la_misma_colocacion():
    base = _calibrado()
    maq = MaquinaCalibracion(4)
    maq.iniciar(CORTO, 0.0, verificar=(base.matriz, base.modelo))
    _correr(maq)
    assert maq.fase == LISTA and maq.verificacion["ok"] and maq.modelo is base.modelo


def test_verificacion_falla_si_se_movieron_los_electrodos_o_cambio_la_amplitud():
    base = _calibrado()
    movido = MaquinaCalibracion(4)
    movido.iniciar(CORTO, 0.0, verificar=(base.matriz, base.modelo))
    _correr(movido, permutar=True)
    assert movido.fase == ERROR and "exactitud" in movido.mensaje
    debil = MaquinaCalibracion(4)
    debil.iniciar(CORTO, 0.0, verificar=(base.matriz, base.modelo))
    _correr(debil, ganancia=0.3)
    assert (
        debil.fase == ERROR
        and "amplitud" in debil.mensaje
        and debil.verificacion["razon_amplitud"][0] < 0.5
    )


def test_perfil_es_json_legible_sin_senal(tmp_path):
    maq = _calibrado()
    ruta = guardar_perfil(tmp_path, maq.matriz, maq.modelo, ConfigProcesamiento())
    d = json.loads(ruta.read_text(encoding="utf-8"))
    assert set(d) == {"version", "fecha", "config", "matriz", "modelo"}


def test_modelo_invalido_se_construye(tmp_path):
    m = ModeloLDA(np.zeros((5, 8)), np.zeros(5), np.arange(5), None)
    guardar_perfil(
        tmp_path, MatrizCalibracion(np.ones(4), np.full((4, 4), 9.0)), m, ConfigProcesamiento()
    )
    assert cargar_perfil(tmp_path, ConfigProcesamiento())[1].exactitud is None
