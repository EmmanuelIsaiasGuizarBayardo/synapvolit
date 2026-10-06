# Registro de sesiones (event sourcing)

El motor guarda **hechos**, no métricas: un archivo JSON Lines por sesión, de solo agregar, en
`%LOCALAPPDATA%\SynapVolit\pacientes\<código>\` (o la carpeta de `--datos`). Cada línea tiene
`n` (orden), `t` (segundos desde el inicio, reloj monotónico del motor) y `tipo`.

| `tipo` | Quién lo origina | Campos |
|---|---|---|
| `sesion_inicio` | Orden `sesion iniciar` | `codigo`, `fecha`, `hora`, `fuente`, `fs`, `calibrado`, `exactitud` |
| `calibracion` | El motor, al terminar una calibración | `exactitud` |
| `senal` | El motor, cuando cambia (filtro de 250 ms) | `valida`: hay decisión del clasificador con señal fresca |
| `ejercicio_inicio` | El juego | `id`, `movimiento` |
| `ejercicio_fin` | El juego + resumen del motor | `id`, `resultado`, `rt_s`, `intensidad_pico`, `coactivacion_media`, `fraccion_valida`, `mdf_hz` |
| `pausa`, `reanudar` | El juego (ayuda abierta) | |
| `sesion_fin` | Orden `sesion terminar`, apagado del motor o 60 s sin interfaz | `motivo` |

No se guarda sEMG cruda (minimización de datos). Escribir a disco y exportar corre en hilos: el
registro nunca frena la señal.

## Métricas, calculadas solo desde los eventos

* **Minutos efectivos** = medida de (ejercicio ∩ señal válida) − pausas. **Adherencia** =
  efectivos / prescritos (30 min por defecto, `minutos_prescritos` al iniciar).
* **Índice de fatiga (exploratorio)**: pendiente de Theil-Sen de la frecuencia mediana del agonista,
  normalizada a las tres primeras de cada movimiento, en % por minuto. Requiere al menos 6
  ejercicios en 2 minutos. No está validado en niños con PC: es una alerta, no un diagnóstico.

## Exportación al cerrar

* `<sesion>_ejercicios.csv`: una fila por ejercicio, tiempos relativos al inicio.
* `resumen_sesiones.csv`: una fila por sesión, acumulada.

Los CSV están **seudonimizados**: sin nombres ni horas, pero el código vincula los datos con la
persona en la clínica.

## Perfil de calibración

Tras una calibración completa con sesión abierta, el motor guarda `perfil.json` en la carpeta del
paciente: reposo y referencias por canal y movimiento, pesos del LDA, exactitud, fecha y la
configuración de rasgos. Es JSON legible (nunca `pickle`) y se escribe de forma atómica.

En la sesión siguiente se carga, pero no se usa hasta pasar una **verificación de ~23 s** (una
repetición de cada movimiento): el LDA guardado debe acertar al menos el 80% con la señal de hoy y
la referencia de cada canal agonista debe quedar entre 0.5 y 2 veces la guardada. Si no pasa, se
pide la calibración completa. Un perfil creado con otra configuración de rasgos se rechaza.
