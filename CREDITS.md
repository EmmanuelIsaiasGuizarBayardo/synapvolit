# Créditos

SynapVolit es un proyecto de la División Universitaria de Neuroingeniería (DUNNE), Departamento de Ingeniería en Sistemas Biomédicos (DISB), División de Ingeniería Mecánica e Industrial (DIMEI), Facultad de Ingeniería (FI), Universidad Nacional Autónoma de México (UNAM).

Los roles siguen la taxonomía [CRediT](https://credit.niso.org/), la que usan las
revistas académicas. Cada persona tiene sus roles y una narrativa que coincide
con ellos. La narrativa describe aportaciones, no cargos.

---

## Contribuciones

### Emmanuel Isaías Guízar Bayardo

*Conceptualization · Methodology · Software · Validation · Data curation · Project administration · Writing – original draft*

Concibió y diseñó la arquitectura de SynapVolit: el protocolo binario entre el microcontrolador y Python, la cadena de procesamiento y la frontera con las aplicaciones de DUNNE. Desarrolló y validó el motor, y preparó la conversión de los datos públicos con que se simula.

<!-- Por cada persona más: una sección "### Nombres Apellidos", sus roles en
     cursiva y su narrativa. Si además es autora, va en CITATION.cff con el mismo
     nombre. Lo que CRediT no cubre, como operar demostraciones o facilitar
     talleres, va en una seccion "## Operación y divulgación". -->

---

## Trabajo de terceros

<!-- Describe en prosa cada pieza ajena y si el proyecto la deriva (la adapta o
     la reimplementa) o la integra (la usa tal cual). La referencia formal va
     solo en 'references' de CITATION.cff; las bibliotecas y sus versiones ya
     están en pyproject.toml y uv.lock. -->

Los datos de simulación provienen de GRABMyo v1.1.0 (Jiang, Pradhan y He, 2024; PhysioNet; CC BY 4.0; https://doi.org/10.13026/89dm-f662). El conversor selecciona cuatro canales del antebrazo, resta la media de cada segmento, une los ensayos con transiciones de 20 ms y remuestrea de 2048 a 2000 Hz; los originales no se redistribuyen.

---

## Cómo citar

GitHub genera la referencia desde `CITATION.cff` con el botón **Cite this
repository**. No se mantiene una cita escrita a mano: se desfasaría con cada versión.

## Cómo se actualiza

Quien contribuya agrega su sección, con los roles que correspondan, en el mismo
*pull request* que su aportación.
