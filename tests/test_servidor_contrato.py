"""Validación de órdenes y mensajes con ausencia explícita."""

import json

import numpy as np
import pytest

from synapvolit.servidor import ErrorOrden, leer_orden, origen_permitido
from synapvolit.servidor.contrato import m_niveles


def test_ordenes_validas():
    assert leer_orden('{"cmd":"cancelar"}') == {"cmd": "cancelar"}
    assert leer_orden('{"cmd":"simular","clase":3}')["clase"] == 3
    p = leer_orden('{"cmd":"calibrar","repeticiones":1,"contraccion_s":2}')["protocolo"]
    assert p.repeticiones == 1 and p.contraccion_s == 2.0 and p.reposo_s == 5.0


@pytest.mark.parametrize(
    "texto",
    [
        "no es json",
        "[1,2]",
        '{"cmd":"borrar"}',
        '{"cmd":"simular","clase":9}',
        '{"cmd":"simular","clase":true}',
        '{"cmd":"calibrar","repeticiones":0}',
        '{"cmd":"calibrar","reposo_s":"5"}',
    ],
)
def test_ordenes_invalidas_dan_error_claro(texto):
    with pytest.raises(ErrorOrden):
        leer_orden(texto)


def test_niveles_invalidos_son_null():
    m = json.loads(
        m_niveles(
            5,
            np.array([10.0, 20.0, 30.0, 40.0]),
            np.array([1, 0, 1, 1], bool),
            np.zeros(4),
            np.zeros(4, bool),
        )
    )
    assert m["env_uv"] == [10.0, None, 30.0, 40.0] and m["act"] == [None] * 4


@pytest.mark.parametrize(
    ("origen", "ok"),
    [
        (None, True),
        ("null", True),
        ("http://127.0.0.1:8000", True),
        ("http://localhost:5173", True),
        ("https://ejemplo.com", False),
        ("http://127.0.0.1.ejemplo.com", False),
    ],
)
def test_solo_paginas_locales(origen, ok):
    assert origen_permitido(origen) is ok
