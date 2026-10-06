# Contrato motor ↔ interfaz por WebSocket, versión 2

```powershell
uv run python -m synapvolit.servidor --fuente simulada          # paciente simulado (GRABMyo)
uv run python -m synapvolit.servidor --fuente serie --puerto-serie COM3
```

El motor escucha en `ws://127.0.0.1:8765` y solo acepta páginas locales (`file://`,
`http://127.0.0.1`, `http://localhost`): cualquier otro origen se cierra con el código 1008, para
que un sitio web abierto en el mismo navegador no pueda leer la sEMG. El juego se abre con
`?motor=ws://127.0.0.1:8765`.

## Del motor a la interfaz

| `tipo` | Cuándo | Campos |
|---|---|---|
| `hola` | Al conectar | `version`, `fuente` (`simulada` o `serie`), `fs`, `canales`, `movimientos` |
| `estado` | Al cambiar y cada 1 s | `activa` (llegan datos frescos), `calibrado`, `calidad` (por canal: `bueno`, `dudoso`, `malo`, `sin evaluar`), `perdidas`, `descartadas`, `error_fuente` |
| `niveles` | ~30 Hz | `t` (ms), `env_uv` y `act` por canal |
| `calibracion` | Al cambiar de fase y cada 100 ms mientras dura | `fase`, `paso` (1-6), `movimiento`, `repeticion`, `de`, `progreso`, `restante_s`, `mensaje`, `duracion_s`, `activa` |
| `calibracion_resultado` | Al terminar, fallar o cancelar | `ok`, `mensaje`, `reposo_uv`, `referencia_uv`, `advertencias`, `exactitud` (validada por repeticiones; `null` con una sola) |
| `decodificador` | 8 Hz, solo calibrado, con señal fresca y fuera de la calibración | `clase` (0 reposo, 1 extensión, 2 flexión, 3 pronación, 4 supinación), `confianza`, `intensidad`, `coactivacion` (`null` si no es separable), `probabilidades`, `t` |
| `error` | Orden inválida | `detalle` |

Si no hay decisión válida, simplemente no se envía `decodificador`: el juego vuelve al teclado y lo anuncia. Cualquier otro valor ausente o inválido llega como `null`: una envolvente sin suficientes muestras
válidas, una activación sin calibración o cualquier dato con más de 250 ms sin señal nueva.

## De la interfaz al motor

| `cmd` | Parámetros | Efecto |
|---|---|---|
| `calibrar` | Opcionales: `repeticiones` (1-10), `reposo_s`, `preparar_s`, `contraccion_s`, `descanso_s` | Inicia la calibración guiada |
| `cancelar` | | La detiene |
| `simular` | `clase` (0-4) | Solo con fuente simulada: el paciente simulado hace ese movimiento (el juego lo envía con las flechas) |
| `ping` | | Responde `{"tipo":"pong"}` |

## Por qué ninguna orden frena la señal

Todo corre en un solo bucle de eventos, en tareas independientes:

* La fuente entrega bytes en cuanto llegan (la lectura del puerto serie corre en un hilo).
* El bucle de procesamiento corre cada ~10 ms: aplica las órdenes pendientes, procesa todo lo
  nuevo, avanza la calibración y publica. Cada paso dura menos de 1 ms.
* Las órdenes solo se encolan en el manejador de la conexión; se ejecutan en el siguiente paso.
* Cada cliente tiene una cola de salida de 64 mensajes; si se llena, se descarta el más viejo.

Las pruebas lo verifican: durante una calibración siguen llegando más de 20 niveles por segundo,
y un cliente que no lee durante 1.5 s no retrasa el procesamiento.

## Calibración

`contacto (1 s estable) → reposo → [preparar → contracción → descanso] × repeticiones × 4 movimientos`.
Con los valores por defecto dura ~1.7 min; la versión rápida (1 repetición), ~40 s. La matriz
vive en memoria. Con la fuente simulada, el motor reproduce sEMG real del movimiento que se pide.
