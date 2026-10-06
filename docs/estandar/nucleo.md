<!-- Archivo del estandar DUNNE, generado por la plantilla. No se edita aqui:
     se actualiza con 'uvx copier update --trust'. Los cambios al estandar se
     proponen en el repositorio de la plantilla. -->

# Estándar DUNNE: núcleo

Aplica a todo proyecto generado con la plantilla. Las reglas tienen dos niveles:

- **REGLA DURA:** no se negocia. Si una petición la contradice, se señala antes de actuar.
- **PREFERENCIA:** valor por defecto razonado. Se puede cambiar dejando la justificación en el README.

Lo que aplica a este proyecto es este núcleo más los módulos presentes en
`docs/estandar/`. Un módulo ausente no aplica, y no se importan reglas de otros
proyectos.

## Módulos de este proyecto

- `dunne.md`: nombre de la organización, titularidad, logotipo y repositorio.
- `investigacion.md`: datos, libretas, reproducibilidad y fuga de datos.
- `datos-de-personas.md`: declaración de lo que se capta de las personas.
- `operacion-en-vivo.md`: arranque sin fallas, estados accionables y lo que ve el público.
- `senal-externa.md`: ausencia explícita, compuerta, fuente simulada y pruebas sin hardware.

## Entorno

- **REGLA DURA.** Nada se instala en el Python del sistema. Todo vive en `.venv`, gestionado por uv.
- **REGLA DURA.** Las dependencias se agregan con `uv add`, nunca con `pip install` dentro del entorno: lo que no pasa por uv no queda en `uv.lock`.
- **PREFERENCIA.** Python 3.12, fijado en `.python-version`, por reproducibilidad y por el rezago del ecosistema científico. No es un requisito técnico de CUDA.

## Dependencias

- `uv.lock` es la fuente de verdad del entorno y se versiona.
- `requirements.txt` es un export para quien use pip. **REGLA DURA:** se regenera solo con `uv run python tools/export_requirements.py`, nunca con `uv export` directo ni a mano.
- Al commitear, un hook regenera ambos archivos. Si los modifica, el commit se detiene a propósito: se vuelven a agregar y se commitea otra vez.

## Estructura

- El código vive en `src/synapvolit/`, instalado en modo editable. **REGLA DURA:** se importa como paquete (`from synapvolit import ...`), nunca manipulando `sys.path`.
- Las pruebas viven en `tests/` y corren con pytest; las utilidades del repositorio, en `tools/`.
- **REGLA DURA.** Lo que produce un script no se edita a mano: se cambia el script y se vuelve a correr. Se versiona cuando alguien lo necesita sin poder correr el generador, como un servidor estático que lo entrega tal cual o quien instala con `requirements.txt`; en cualquier otro caso se regenera y queda fuera del repositorio.
- Hay dos clases de archivo. Los que llevan el aviso "Archivo del estándar DUNNE" los mantiene la plantilla, y sus cambios se proponen allá. `README.md`, `CITATION.cff`, `CREDITS.md`, `__init__.py` y, si existen, `main.py` y `utils.py` son del proyecto: la plantilla los crea una vez y no los vuelve a tocar.

## Datos de personas

- **REGLA DURA.** Ningún dato de una persona entra al repositorio, sea público o privado. El `.gitignore` bloquea los formatos de señal en cualquier ruta; es la primera barrera, no la única.
- Antes de cada push se revisa `git status`.

## Codificación y formato

- **REGLA DURA.** UTF-8 sin BOM y finales LF. `.gitattributes` lo impone y no se desactiva.
- Única excepción: un script `.ps1` para Windows PowerShell 5.1 va en UTF-8 **con** BOM, o sus acentos se corrompen al ejecutarse.
- Ruff revisa lint y formato; el hook y el CI lo verifican.

## Git y GitHub

- Rama principal `main`. El CI (Ruff y pytest) debe pasar antes de integrar cambios.
- **PREFERENCIA.** `.github/workflows/ci.yml` es del estándar. Los pasos propios del proyecto, como verificar que un documento derivado esté al día, van en un workflow aparte en la misma carpeta, donde las actualizaciones de la plantilla no chocan con ellos.

## Gobernanza

- **REGLA DURA.** `LICENSE` contiene solo el texto MIT. Nada se le agrega después: el detector de GitHub exige casi el texto exacto y dejaría el repositorio sin licencia reconocida. Las aclaraciones van en el README.
- `CITATION.cff` es la fuente de la cita; GitHub genera desde ahí el botón *Cite this repository*. Las referencias formales a datos y software de terceros viven solo en su sección `references`.
- `CREDITS.md` asigna a cada persona sus roles CRediT, con una narrativa que coincide con ellos. La narrativa describe aportaciones, no cargos.
- **REGLA DURA.** Todo autor del CFF tiene su sección en `CREDITS.md`, y la versión del CFF es la de `pyproject.toml`. `tests/test_gobernanza.py` lo verifica, y las marcas `[COMPLETAR: ...]` hacen fallar el CI hasta que se completan.
- **REGLA DURA.** Una versión se publica con `uv run python tools/publicar.py X.Y.Z "mensaje"`, nunca etiquetando a mano: sube el número, sincroniza el CFF, corre las pruebas, etiqueta y sube, y se detiene antes de etiquetar si algo falla. Una etiqueta publicada no se mueve; si salió mal, se publica la siguiente versión.
- Antes de cada presentación pública se publica una versión cuyo mensaje nombra el evento.

## Actualizar el estándar

- Con el árbol limpio: `uvx copier update --trust`. La actualización no toca el entorno: al terminar se corren `uv sync` y `uv run python tools/export_requirements.py`, se revisa con `git diff` y se commitea de inmediato, o la siguiente actualización encontrará el árbol sucio.
- `docs/estandar/`, `AGENTS.md`, `CLAUDE.md` y `.agents/rules/` se regeneran; no se editan. Las notas propias para asistentes van en la sección final de `AGENTS.md`, que la actualización conserva.

## Lista de verificación

- [ ] El entorno es el `.venv` del proyecto, no el Python del sistema.
- [ ] `uv.lock` está commiteado y coincide con `pyproject.toml`.
- [ ] `requirements.txt` salió del script de export.
- [ ] Ruff y pytest pasan.
- [ ] Ningún archivo con datos de personas está en el área de staging.
