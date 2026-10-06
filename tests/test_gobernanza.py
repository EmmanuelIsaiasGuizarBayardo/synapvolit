"""Pruebas de gobernanza: autoría, versión y declaraciones completas.

Archivo del estandar DUNNE: se actualiza con 'copier update'.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
MARCA = "[COMPLETAR"
# Se genera desde copier.yml: una sola linea, aunque exceda el ancho.
AFILIACION_OFICIAL = "División Universitaria de Neuroingeniería (DUNNE), Departamento de Ingeniería en Sistemas Biomédicos (DISB), División de Ingeniería Mecánica e Industrial (DIMEI), Facultad de Ingeniería (FI), Universidad Nacional Autónoma de México (UNAM)"  # noqa: E501


def _cff() -> dict:
    """Lee CITATION.cff."""
    return yaml.safe_load((RAIZ / "CITATION.cff").read_text(encoding="utf-8"))


def _nombre(autor: dict) -> str:
    """Nombre completo de un autor del CFF, como aparece en CREDITS.md."""
    return f"{autor.get('given-names', '')} {autor.get('family-names', '')}".strip()


def test_sin_marcas_pendientes() -> None:
    """Ninguna declaración obligatoria queda a medias."""
    archivos = ["CITATION.cff", "CREDITS.md", "README.md"]
    pendientes = [f for f in archivos if MARCA in (RAIZ / f).read_text(encoding="utf-8")]
    assert not pendientes, f"Completa las marcas [COMPLETAR: ...] en: {', '.join(pendientes)}"


def test_readme_declara_datos_de_personas() -> None:
    """El README tiene la sección que declara qué se capta de las personas."""
    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    assert re.search(r"^## Datos de personas\s*$", readme, flags=re.MULTILINE), (
        "El README debe tener una sección '## Datos de personas' con la declaración"
    )


def test_existe_la_guia_del_operador() -> None:
    """La guía del operador existe; los operadores rotan."""
    assert (RAIZ / "docs" / "operacion.md").is_file(), (
        "Falta docs/operacion.md: montaje, verificación previa, estados y cierre"
    )


def test_autores_del_cff_en_creditos() -> None:
    """Cada autor que aparece al citar tiene su sección de roles."""
    creditos = (RAIZ / "CREDITS.md").read_text(encoding="utf-8")
    secciones = set(re.findall(r"^### (.+?)\s*$", creditos, flags=re.MULTILINE))
    faltan = [_nombre(a) for a in _cff()["authors"] if _nombre(a) not in secciones]
    assert not faltan, f"Autores de CITATION.cff sin sección en CREDITS.md: {faltan}"


def test_nombres_de_pila_sin_apellidos() -> None:
    """Los nombres de pila no repiten los apellidos."""
    repetidos = [
        _nombre(a)
        for a in _cff()["authors"]
        if a.get("family-names") and a.get("given-names", "").endswith(a["family-names"])
    ]
    assert not repetidos, f"Nombres de pila que repiten los apellidos: {repetidos}"


def test_version_del_cff_coincide_con_pyproject() -> None:
    """La versión que se cita es la que se distribuye."""
    pyproject = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    esperada = pyproject["project"]["version"]
    assert str(_cff()["version"]) == esperada, f"CITATION.cff debe declarar la versión {esperada}"


def test_afiliaciones_a_dunne_son_oficiales() -> None:
    """Toda afiliación que menciona a DUNNE usa el nombre oficial, sin variantes."""
    distintas = [
        _nombre(a)
        for a in _cff()["authors"]
        if "DUNNE" in a.get("affiliation", "") and a["affiliation"] != AFILIACION_OFICIAL
    ]
    assert not distintas, f"Afiliación a DUNNE distinta de la oficial en: {distintas}"
