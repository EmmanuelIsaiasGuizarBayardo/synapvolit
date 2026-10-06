"""Máquina de calibración con reloj falso: tiempos exactos y sin red."""

import numpy as np

from synapvolit.procesamiento import BUENO, MALO
from synapvolit.servidor.calibracion import (
    CANCELADA,
    CONTACTO,
    ERROR,
    LISTA,
    REPOSO,
    MaquinaCalibracion,
    Protocolo,
)

CORTO = Protocolo(reposo_s=2.0, preparar_s=0.2, contraccion_s=1.0, descanso_s=1.0, repeticiones=2)
BIEN = np.full(4, BUENO, np.int8)


def _correr(maq, hasta, *, ganancia=1.0, calidad=BIEN, fresca=lambda t: True, t0=0.0):
    """Paciente obediente: el canal del movimiento pedido sube a 100 µV; el reposo es de 5 µV."""
    pasos, t, rng = [], t0, np.random.default_rng(0)
    while t < hasta and maq.fase not in (LISTA, ERROR, CANCELADA):
        env = np.full(4, 5.0)
        if maq.objetivo:
            env[maq.objetivo - 1] = 5.0 + 95.0 * ganancia
        rasgos = np.r_[np.log1p(env), np.log1p(env * 0.3)] + rng.normal(0, 0.05, 8)  # ruido real
        maq.avanzar(t, env, np.ones(4, bool), calidad, fresca(t), rasgos, True)
        pasos.append(maq.paso)
        t += 0.01
    return pasos, t


def test_calibracion_completa():
    maq = MaquinaCalibracion(4)
    maq.iniciar(CORTO, 0.0)
    pasos, t = _correr(maq, 60)
    assert maq.fase == LISTA and not maq.advertencias
    assert np.allclose(maq.matriz.reposo_uv, 5.0) and np.allclose(maq.matriz.referencia_uv, 100.0)
    assert list(dict.fromkeys(pasos)) == [1, 2, 3, 4, 5, 6, 7]  # los seis pasos de la pantalla
    assert abs(t - CORTO.duracion_s) < 0.1  # 1 + 2 + 2.2 × 2 × 4 = 20.6 s
    assert maq.modelo is not None and maq.modelo.exactitud == 1.0  # el LDA se entrena al final


def test_sin_contacto_termina_en_error_y_dice_el_canal():
    maq = MaquinaCalibracion(4)
    maq.iniciar(Protocolo(espera_contacto_s=3.0), 0.0)
    mala = BIEN.copy()
    mala[1] = MALO
    _correr(maq, 10, calidad=mala)
    assert maq.fase == ERROR and "flexion" in maq.mensaje


def test_hueco_breve_se_tolera_y_uno_largo_aborta():
    maq = MaquinaCalibracion(4)
    maq.iniciar(CORTO, 0.0)
    _correr(
        maq, 60, fresca=lambda t: not 1.5 < t < 2.0
    )  # 0.5 s sin datos durante el reposo (1-3 s)
    assert maq.fase == LISTA
    maq.iniciar(CORTO, 0.0)
    _correr(maq, 60, fresca=lambda t: not 1.5 < t < 4.0)
    assert maq.fase == ERROR and "perdió la señal" in maq.mensaje


def test_movimiento_debil_da_advertencia():
    maq = MaquinaCalibracion(4)
    maq.iniciar(CORTO, 0.0)
    _correr(maq, 60, ganancia=0.04)  # el agonista llega a 8.8 µV: 1.8 veces el reposo
    assert maq.fase == LISTA and len(maq.advertencias) == 4


def test_cancelar():
    maq = MaquinaCalibracion(4)
    maq.iniciar(CORTO, 0.0)
    _correr(maq, 1.5)
    assert maq.fase == REPOSO
    maq.cancelar(1.5)
    assert maq.fase == CANCELADA and maq.objetivo == 0


def test_contacto_exige_un_segundo_seguido():
    maq = MaquinaCalibracion(4)
    maq.iniciar(CORTO, 0.0)
    _correr(maq, 0.99)
    assert maq.fase == CONTACTO
    _correr(maq, 1.02, t0=0.99)
    assert maq.fase == REPOSO
