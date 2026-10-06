"""Pruebas de humo: el paquete es importable y determinista."""

from __future__ import annotations

import numpy as np

from synapvolit.reproducibility import get_run_context, set_seed
from synapvolit.utils import zscore_por_canal


def test_paquete_importable() -> None:
    """El paquete debe resolverse sin manipular sys.path."""
    import synapvolit

    assert synapvolit.__name__ == "synapvolit"


def test_semilla_es_determinista() -> None:
    """Dos corridas con la misma semilla producen la misma secuencia."""
    # Se usa la API legada a proposito: lo que se verifica es justamente que
    # set_seed haya sembrado el estado global de NumPy.
    set_seed(123)
    a = np.random.rand(5)  # noqa: NPY002
    set_seed(123)
    b = np.random.rand(5)  # noqa: NPY002
    np.testing.assert_array_equal(a, b)


def test_zscore_centra_y_escala() -> None:
    """Tras normalizar, cada canal tiene media ~0 y desviacion ~1."""
    rng = np.random.default_rng(0)
    epochs = rng.normal(loc=5.0, scale=3.0, size=(4, 8, 256))
    out = zscore_por_canal(epochs)
    np.testing.assert_allclose(out.mean(axis=-1), 0.0, atol=1e-6)
    np.testing.assert_allclose(out.std(axis=-1), 1.0, atol=1e-3)


def test_contexto_de_corrida() -> None:
    """El contexto se construye aunque no haya repositorio git."""
    ctx = get_run_context(seed=7)
    assert ctx.seed == 7
    assert isinstance(ctx.git_dirty, bool)
