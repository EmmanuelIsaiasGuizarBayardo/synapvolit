# SynapVolit

Motor de adquisición, procesamiento y decodificación de sEMG para aplicaciones de DUNNE.

## Estructura

```
data/raw/          INMUTABLE. Datos crudos, idealmente en layout BIDS-EEG. No versionado.
data/processed/    Derivados: épocas, features, matrices filtradas. No versionado.
notebooks/         Exploración interactiva. No contiene lógica reutilizable.
results/           Figuras y métricas. No versionado.
src/synapvolit/   Código fuente. Paquete instalable.
tests/             Pruebas.
tools/             Utilidades del repositorio.
```

## Puesta en marcha

Requisitos: Git y [uv](https://docs.astral.sh/uv/). Funciona igual en Windows, Mac y Linux.

```
uv sync
uv run pre-commit install
```

`uv sync` crea `.venv`, instala desde `uv.lock` e instala el paquete en modo editable.

**Sin uv, solo con pip:**

```
python -m venv .venv
# Windows:    .venv\Scripts\activate
# Mac/Linux:  source .venv/bin/activate
pip install -r requirements.txt
pip install -e . --no-deps
```

## Importar desde libretas

El paquete está instalado en modo editable, así que no hace falta tocar `sys.path`:

```python
from synapvolit.reproducibility import set_seed, get_run_context
```

## Dependencias

`pyproject.toml` → `uv.lock` (fuente de verdad) → `requirements.txt` (export).

Para agregar una dependencia: `uv add <paquete>`. Al hacer commit, un hook regenera
`uv.lock` y `requirements.txt`; si los modifica, el commit se detiene a propósito y
basta con volver a agregar los archivos.

## Licencia

El código se distribuye bajo la licencia MIT (`LICENSE`).

## Estados de la señal

Cada canal se evalúa cada 10 ms como bueno, dudoso o malo (sin contacto, señal plana, recorte o red eléctrica), con histéresis de 250 ms para empeorar y 500 ms para mejorar. Nada que dependa de la señal se usa con contacto malo. Umbrales, justificación y costo medido: `docs/procesamiento.md`.
## Datos de personas

<!-- Declaración obligatoria: qué se capta, de quién, dónde vive y cuánto dura.
     Si el proyecto sí guarda datos, reemplaza el párrafo por qué se guarda,
     dónde, por cuánto tiempo y con qué consentimiento. -->

**Señal de personas.** En operación, el motor recibe en tiempo real la sEMG de cuatro canales del antebrazo de quien usa el brazalete y, cuando exista, la orientación de su IMU. Esa señal se mantiene en memoria mientras dura la sesión y no se escribe a disco; ningún componente del motor la persiste todavía.

**Datos públicos para simulación.** Para desarrollar y probar sin hardware se usa GRABMyo v1.1.0 (PhysioNet, CC BY 4.0): sEMG de antebrazo de 43 adultos sanos, identificados solo por número, recolectada con aprobación ética de la Universidad de Waterloo (ORE 31346). Los originales se descargan a data/raw/ y el derivado que reproduce el simulador, un CSV de cuatro canales por persona y sesión, se escribe en data/processed/. Git ignora ambas carpetas, de modo que este repositorio no contiene datos de personas. Los derivados se conservan mientras dure el desarrollo y se regeneran en cualquier momento desde los originales; la procedencia se registra en data/raw/README.md y en el JSON de cada derivado.

Cuando el motor guarde perfiles de calibración o registros de sesión, esta declaración se actualizará en el mismo cambio que los introduzca.

**Marco legal.** Pendiente.

## Créditos

Los roles de cada persona, en taxonomía CRediT, están en `CREDITS.md`. Para citar
el proyecto, GitHub genera la referencia desde `CITATION.cff` con el botón
**Cite this repository**. Para contribuir, ver `CONTRIBUTING.md`.

## Estándar DUNNE

Este proyecto nació de la plantilla DUNNE. Las reglas que le aplican están en
`docs/estandar/` y los comandos de uso frecuente en `docs/comandos.md`.
`AGENTS.md` le entrega ese contexto a Claude Code y a la mayoría de los
asistentes de código.

Para traer las mejoras más recientes del estándar, con el árbol de trabajo limpio:

```
uvx copier update --trust
```
