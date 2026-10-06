<!-- Archivo del estandar DUNNE, generado por la plantilla. No se edita aqui:
     se actualiza con 'uvx copier update --trust'. -->

# Módulo: señal externa

Aplica porque el proyecto lee en tiempo real una señal de hardware o de otra
fuente externa.

## Ausencia explícita

- **REGLA DURA.** La ausencia de datos se representa de forma explícita, con `None` o una bandera de validez, nunca con un valor que podría ser una lectura legítima. Un cero de "todavía no hay datos" que entra como concentración nula es el error que esta regla previene, y ocurre también a mitad de sesión, cuando la conexión se cae.

```python
@dataclass(frozen=True)
class Lectura:
    valor: float | None  # None: no hay dato. Nunca 0.
    t: float

    @property
    def valida(self) -> bool:
        return self.valor is not None
```

- **REGLA DURA.** Nada que dependa de la señal se ejecuta mientras la señal no sea válida. La compuerta se aplica en dos niveles: en la interfaz y en la lógica que consume la señal.

## Fuente simulada y pruebas

- **REGLA DURA.** Existe una fuente simulada que produce las mismas tramas que el hardware real, sembrable y con escenarios de falla: desconexión, pérdida de contacto y ruido. Se elige con un selector visible, nunca con un modo escondido.
- **REGLA DURA.** Ninguna prueba necesita el hardware. Los dobles recomendados son tramas sintéticas para el intérprete del protocolo, una fuente guionizada con reloj controlado para la máquina de estados, y la fuente simulada para la ruta completa.

## Arquitectura

- **PREFERENCIA.** El intérprete del protocolo es puro: sin puerto, sin hilos y sin reloj. Recibe bytes y entrega eventos, y por eso se prueba con tramas sintéticas.
- **PREFERENCIA.** Cada fuente tiene un solo dueño, que abre y cierra el puerto; los consumidores piden una sesión. Dos partes que piden la misma fuente reciben la misma sesión, lo que elimina por construcción el bloqueo del puerto.
- **PREFERENCIA.** Los estados de la señal y sus umbrales se documentan en el README y se prueban con un reloj controlado: los que dependen del tiempo, como "sin datos desde hace 3 s", no se prueban bien con el reloj real.
- **PREFERENCIA.** El protocolo se documenta y, si se implementa a mano, se valida contra una implementación independiente.
- Las restricciones del entorno de operación, como una versión de sistema operativo con Bluetooth inestable, se documentan en el README.

## Lista de verificación

- [ ] Ningún valor de "sin datos" se confunde con una lectura válida.
- [ ] Nada consume la señal antes de que sea válida.
- [ ] La fuente simulada cubre las fallas que el hardware real no permite provocar.
- [ ] `uv run pytest -q` pasa sin hardware conectado.
