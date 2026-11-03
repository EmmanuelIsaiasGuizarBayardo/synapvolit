# Clasificación e intensidad

Esta guía describe cómo decide el motor qué movimiento hace la persona, con qué datos se ha
validado y qué no se ha validado. Lo medido viene de salidas reales en el equipo del proyecto; lo
que no está hecho se dice como tal.

## Resumen

Cada 125 ms el motor entrega una de **cinco clases** (reposo, extensión, flexión, pronación,
supinación) a partir de 4 canales de sEMG, junto con una **intensidad** y una **co-contracción**.

| Etapa | Entrada | Salida | Frecuencia |
|---|---|---|---|
| Filtros (pasa-banda 20 a 450 Hz, muesca 60 Hz) | sEMG cruda, 2 kHz | señal filtrada | 2 kHz |
| Rasgos | señal filtrada | 8 rasgos | cada 10 ms |
| LDA y suavizado | 8 rasgos | clase y confianza | 8 Hz |
| Intensidad y co-contracción | envolvente RMS y calibración | dos números | 8 Hz |

## Por qué un LDA

El análisis discriminante lineal (LDA) es el clasificador de referencia en el reconocimiento de
patrones de sEMG (Hudgins et al., 1993; Englehart y Hudgins, 2003; Scheme y Englehart, 2011). Se
eligió porque:

* aprende con pocos datos: una calibración de unos 2 minutos por paciente;
* se entrena en unos 0.1 s;
* decidir cuesta 5 × 8 productos y un softmax, así que no estorba al flujo de señal;
* sus pesos se pueden inspeccionar y guardar en un JSON.

Supone que cada clase es gaussiana con la misma covarianza y que las fronteras son lineales. No se
ha comparado con otros clasificadores (redes, SVM u otros): esa comparación no está hecha.

## Rasgos

Por canal, en una ventana de 150 ms de la envolvente: `log1p(RMS)` y `log1p(DASDV)`, donde DASDV
es la RMS de la primera diferencia. La RMS mide amplitud y la DASDV además refleja el contenido de
frecuencia. Con 4 canales son 8 rasgos. El mismo `Procesador` del tiempo real los calcula, así que
la calibración y el uso comparten exactamente la misma cadena.

La ventana avanza cada 10 ms, así que ventanas consecutivas se traslapan 93%: las muestras de
entrenamiento no son independientes entre sí. Esto no infla la exactitud reportada (la validación
separa por repetición, no por ventana), pero la covarianza se estima con datos muy correlacionados.

## Modelo

Para cada clase `k`, la función discriminante es

`δ_k(x) = xᵀ Σ⁻¹ μ_k − ½ μ_kᵀ Σ⁻¹ μ_k + ln π_k`

y la probabilidad es el softmax de las `δ_k`. Se entrena con
`LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")` de scikit-learn:

* **Covarianza `Σ`**: promedio de las covarianzas de cada clase, con encogimiento de Ledoit y Wolf
  (2004) hacia una matriz escalar, con el grado de encogimiento elegido automáticamente. Estabiliza
  la estimación con pocos datos y rasgos correlacionados (la RMS y la DASDV de un mismo canal).
* **Probabilidades a priori `π_k`**: las frecuencias de clase del entrenamiento (el valor por
  defecto de scikit-learn). En la calibración guiada el reposo es la clase más abundante (reposo
  inicial más descansos), lo que puede inclinar las decisiones hacia reposo. No se ha cuantificado.

Se entrena al terminar la calibración guiada con:

* el reposo inicial y los descansos entre repeticiones, etiquetados como reposo;
* cada contracción;
* se descartan los primeros 0.5 s de cada contracción y de cada descanso (a lo más el 30% del
  tramo), porque ahí la persona todavía está empezando o terminando el movimiento. El reposo inicial
  no se recorta.

El entrenamiento y su validación cruzada corren en un hilo aparte (`run_in_executor`): el bucle
sigue procesando y publicando niveles. En línea no se llama a scikit-learn; una prueba verifica que
la decisión propia coincide con `predict_proba`.

## Decisión

Las probabilidades de los últimos 12 pasos de 10 ms (~120 ms) se promedian con una suma corriente.
La clase es la de mayor probabilidad media y la confianza, esa probabilidad. Si menos del 75% de los
pasos de la ventana tienen rasgos válidos, no hay decisión (el motor no publica nada). Se publica a
8 Hz.

## Validación: qué números hay y cuáles no mezclar

**1. Exactitud interna de la calibración** (la que muestra el juego como "Exactitud estimada").
Validación cruzada agrupada por repetición (`StratifiedGroupKFold`): ninguna ventana de una
repetición se usa a la vez para entrenar y evaluar. Con una sola repetición no hay estimación
honesta y se reporta como no disponible. Es optimista como medida de uso real: comparte sesión y
colocación de electrodos.

**2. Evaluación en línea con sEMG real** (dataset GRABMyo v1.1.0; ver `docs/instalacion.md`). Cada
decisión a 8 Hz se compara con el movimiento real, ignorando los 0.5 s posteriores a cada cambio.

| Escenario (por participante, n = 5) | Media (DE) |
|---|---|
| Intra sesión 1 (entrena con ensayos 1-3, prueba 4-7) | 92% (9%) |
| **Entre sesiones** (entrena con toda la sesión 1, prueba en la 2) | **88% (8%)** |
| Adaptado (perfil más un ensayo de la sesión 2) | 89% (6%) |
| Recalibrado (calibración completa de la sesión 2) | 95% (3%) |

Con el participante 1, intra sesión 1: exactitud global 86%, mediana de 370 ms desde el inicio del
movimiento hasta la primera decisión correcta, y la confusión principal es flexión con pronación
(39 de 148 flexiones se decidieron como pronación). El azar es 20% con cinco clases.

Límites que hay que declarar:

* Son **adultos sanos**, 5 personas (las primeras por número), un modelo por persona. No hay
  validación entre personas (*leave-one-subject-out*) ni datos de niños con PCEU.
* El flujo de prueba se arma concatenando grabaciones separadas de cada gesto; las transiciones no
  son movimientos continuos naturales.
* En "intra sesión 1" los 4 canales se eligieron con los 7 ensayos, incluidos los 4 de prueba: hay
  una fuga de selección de canales y esa cifra es optimista. El resultado a reportar es el de
  **entre sesiones**, que no tiene esa fuga.
* Con la PCB real los 4 canales irán en posiciones fijas, así que estas cifras no se transfieren
  directamente. La exactitud fuera de línea predice mal la usabilidad real (Scheme y Englehart,
  2011).
* F1, matriz de confusión agregada y la latencia total de la muestra a la pantalla no están medidas.

## Intensidad y co-contracción

Con `p_m = referencia_m − reposo` (el patrón de cuatro canales del movimiento `m`):

* **Intensidad**: `I = (e − r)·p_m / (p_m·p_m)`, el factor que mejor explica la envolvente actual
  como una fracción del patrón de calibración. Vale 0 en reposo y 1 a la fuerza de la calibración;
  se recorta a 1.5.
* **Co-contracción**: se ajusta `e − r ≈ a·p_m + c·p_antagonista` con ambos patrones a la vez y se
  reporta `c / a` (coeficientes negativos a 0, denominador mínimo de 0.05, resultado entre 0 y 1).
  Ajustarlos juntos evita contar como antagonista la parte compartida de los patrones (diafonía).
  Si los patrones son casi paralelos (número de condición mayor que 30), no se reporta.

Advertencias:

* La "referencia" es el **percentil 95 de la envolvente RMS** durante las contracciones de la
  calibración (mediana entre repeticiones). No es una contracción voluntaria máxima medida con
  dinamómetro: el "% MVC" del juego es relativo a esa calibración, no a la fuerza máxima de la
  persona.
* La intensidad y la co-contracción **no están validadas** contra fuerza ni contra una medición de
  referencia.

## Qué no está hecho

* Validación entre personas y con pacientes.
* Comparación con otros clasificadores.
* Intensidad y co-contracción contra una medida de referencia.
* Adaptación del modelo durante la sesión (el experimento "adaptado" fue fuera de línea y mejoró
  1 punto; no está en el motor).

## Reproducir

```
uv run python -m synapvolit.clasificacion
uv run python -m synapvolit.validacion --participantes 1 2 3 4 5 --sesiones 1 2
```

La primera entrena con los ensayos 1-3 y evalúa los 4-7 por la ruta en línea completa; con el
participante 1 debe dar 95% de exactitud validada por repeticiones y 86% en línea. La segunda
reproduce la tabla de arriba. Los pasos previos están en `docs/instalacion.md`.

## Referencias

Englehart, K., & Hudgins, B. (2003). A robust, real-time control scheme for multifunction
myoelectric control. *IEEE Transactions on Biomedical Engineering, 50*(7), 848-854.
https://doi.org/10.1109/TBME.2003.813539

Hudgins, B., Parker, P., & Scott, R. N. (1993). A new strategy for multifunction myoelectric
control. *IEEE Transactions on Biomedical Engineering, 40*(1), 82-94.
https://doi.org/10.1109/10.204774

Ledoit, O., & Wolf, M. (2004). A well-conditioned estimator for large-dimensional covariance
matrices. *Journal of Multivariate Analysis, 88*(2), 365-411.
https://doi.org/10.1016/S0047-259X(03)00096-4

Scheme, E., & Englehart, K. (2011). Electromyogram pattern recognition for control of powered
upper-limb prostheses: State of the art and challenges for clinical use. *Journal of Rehabilitation
Research and Development, 48*(6), 643-659. https://doi.org/10.1682/JRRD.2010.09.0177
