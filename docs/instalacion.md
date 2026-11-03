# Instalación y reproducción en otra computadora

Esta guía deja funcionando, en una computadora nueva, todo lo que se usó en el proyecto: el motor
SynapVolit, el dataset GRABMyo, la conversión a señal de demostración, las validaciones y el juego
WristQuest conectado al motor. Los pasos replican lo que ya se corrió en el equipo del proyecto
(Windows con PowerShell 5.1); no se ha probado todavía en una computadora limpia, así que si un
paso falla, anota cuál y el mensaje.

## 0. Qué necesitas

| Requisito | Para qué | Cómo instalarlo |
|---|---|---|
| Windows 10 u 11 y PowerShell | Los comandos de esta guía | Ya vienen con Windows |
| Git (incluye Git LFS) | Clonar los repositorios | `winget install --id Git.Git -e` |
| uv | Instala Python y las bibliotecas fijadas en `uv.lock` | `winget install --id astral-sh.uv -e` |
| Chrome o Edge | Abrir el juego | Ya suele estar |
| Internet | Clonar y descargar el dataset | |

Cierra y vuelve a abrir PowerShell tras instalar, y comprueba:

```powershell
git --version
uv --version
```

No hace falta instalar Python aparte: `uv` lo descarga solo.

## 1. Clonar los dos repositorios en la misma carpeta

Deben quedar como carpetas hermanas (`SynapVolit` y `WristQuest`): el lanzador del juego busca el
motor en `..\SynapVolit`.

```powershell
New-Item -ItemType Directory -Force C:\Proyectos\DUNNE | Out-Null
Set-Location C:\Proyectos\DUNNE
git lfs install
git clone https://github.com/EmmanuelIsaiasGuizarBayardo/synapvolit.git SynapVolit
git clone https://github.com/EmmanuelIsaiasGuizarBayardo/wristquest.git WristQuest
```

Git LFS solo guarda los PNG del arte en `WristQuest\assets\sprites`. Para jugar no hacen falta: el
arte ya viene incrustado en `web\wristquest.html`.

## 2. Instalar las dependencias del motor y comprobarlas

```powershell
Set-Location C:\Proyectos\DUNNE\SynapVolit
uv sync
uv run pytest -q
```

Deben pasar todas las pruebas; una se omite si no hay compilador de C++ (es la que compara el
firmware con el motor byte a byte). Si una falla, no sigas: el resto depende de que esto pase.

## 3. Descargar el dataset GRABMyo

**Dataset**: GRABMyo v1.1.0, PhysioNet, licencia CC BY 4.0, DOI 10.13026/89dm-f662. Se descarga sin
cuenta. Se usan los gestos 11 (extensión), 12 (flexión), 13 (supinación), 14 (pronación) y 17
(reposo), los 7 ensayos de cada uno.

Elige cuánto descargar cambiando las dos primeras líneas:

* **Demostración del juego** (una persona, una sesión): `$sesiones = 1` y `$participantes = 1`.
* **Validación entre sesiones** (la del póster): `$sesiones = 1, 2` y `$participantes = 1..5`.

El script se puede interrumpir y repetir: salta los archivos que ya existen.

```powershell
Set-Location C:\Proyectos\DUNNE\SynapVolit
$sesiones = 1
$participantes = 1
$ProgressPreference = "SilentlyContinue"
$base = "https://physionet.org/files/grabmyo/1.1.0"
$raiz = "data\raw\grabmyo\1.1.0"
New-Item -ItemType Directory -Force $raiz | Out-Null
Invoke-WebRequest "$base/SHA256SUMS.txt" -OutFile "$raiz\SHA256SUMS.txt" -UseBasicParsing
foreach ($s in $sesiones) {
    foreach ($p in $participantes) {
        $dir = "$raiz\Session$s\session${s}_participant$p"
        New-Item -ItemType Directory -Force $dir | Out-Null
        foreach ($g in 11, 12, 13, 14, 17) {
            foreach ($t in 1..7) {
                foreach ($ext in "hea", "dat") {
                    $archivo = "session${s}_participant${p}_gesture${g}_trial$t.$ext"
                    if (-not (Test-Path "$dir\$archivo")) {
                        Invoke-WebRequest "$base/Session$s/session${s}_participant$p/$archivo" -OutFile "$dir\$archivo" -UseBasicParsing
                    }
                }
            }
        }
    }
}
```

Para saber cuánto ocupa lo descargado:

```powershell
"{0:N0} MB" -f ((Get-ChildItem data\raw -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
```

### Comprobar la integridad

PhysioNet publica la suma SHA-256 de cada archivo; este comando compara las de lo descargado:

```powershell
$revisados = 0; $malos = 0
foreach ($linea in Get-Content "$raiz\SHA256SUMS.txt") {
    $p = $linea -split '\s+', 2
    if ($p.Count -ne 2 -or $p[1] -notmatch '\.(dat|hea)$') { continue }
    $archivo = Join-Path $raiz ($p[1].Trim() -replace '/', '\')
    if (-not (Test-Path $archivo)) { continue }
    $revisados++
    if ((Get-FileHash $archivo -Algorithm SHA256).Hash -ne $p[0].ToUpper()) {
        $malos++
        Write-Warning "No coincide: $archivo"
    }
}
"$revisados archivos revisados, $malos con diferencias"
```

Si algún archivo no coincide, bórralo y vuelve a correr el script de descarga. (La validación del
paso 8 hace esta misma comprobación sola antes de empezar.)

## 4. Convertir una persona a señal de demostración

```powershell
uv run python -m synapvolit.datasets.grabmyo --sesion 1 --participante 1
```

Lee los registros, elige los 4 canales más informativos (selección hacia adelante con LDA, validada
por ensayo), remuestrea de 2048 a 2000 Hz y escribe `data\processed\grabmyo\s1_p01.csv`. Imprime
qué canales eligió; para el participante 1 deben ser **F15, F10, F1 y F7**.

Sin este archivo el motor no arranca y avisa: "Falta la señal de demostración".

## 5. Comprobar la cadena de procesamiento

```powershell
uv run python -m synapvolit.transporte --escenario limpio --segundos 10
uv run python -m synapvolit.procesamiento --rapido
uv run python -m synapvolit.clasificacion
```

La última entrena con los ensayos 1 a 3 y evalúa los 4 a 7 por la ruta en línea completa. Con el
participante 1 debe imprimir, entre otras cosas:

```
Entrenado con los ensayos 1-3. Exactitud validada por repeticiones: 95%
Decisiones en línea, ensayos 4-7 (785 decisiones a 8 Hz):
  exactitud global: 86%
```

Si coincide, la computadora nueva reproduce el resultado del equipo. Las versiones de todas las
bibliotecas están fijadas en `uv.lock`, por eso debe salir igual.

## 6. Jugar con la señal simulada

El juego necesita el motor corriendo y abrirse con `?motor=...`. El lanzador hace las dos cosas:

```powershell
Set-Location C:\Proyectos\DUNNE\WristQuest
.\scripts\iniciar_demo_simulado.cmd
```

(También con doble clic en ese archivo.) Arranca el motor, sirve el juego y abre el navegador en la
dirección correcta. Para cerrar, pulsa Enter en la ventana: el motor guarda la sesión abierta.

En el juego: **Jugar → Acceso → elige un perfil → Calibrar** (la calibración completa dura unos
2 minutos). El pie de pantalla dice "FUENTE SIMULADA": el motor reproduce sEMG real del dataset, y
las flechas del teclado hacen que el paciente simulado ejecute cada movimiento.

### Si prefieres hacerlo a mano (dos terminales)

Terminal A, el motor:

```powershell
Set-Location C:\Proyectos\DUNNE\SynapVolit
uv run python -m synapvolit.servidor --fuente simulada
```

Terminal B, el juego:

```powershell
Set-Location C:\Proyectos\DUNNE\WristQuest
uv run python -m http.server 8000 --bind 127.0.0.1 --directory web
```

Y abre `http://127.0.0.1:8000/wristquest.html?motor=ws://127.0.0.1:8765`.

**Si la pantalla de calibración dice "Sin conexión con el motor"**, el juego se abrió sin motor o
sin el `?motor=...` en la dirección: es el comportamiento esperado de la demo en línea de GitHub
Pages y de abrir `wristquest.html` con doble clic. Usa el lanzador.

## 7. Con el brazalete real

Misma ruta, cambiando la fuente (sustituye COM3 por el puerto del brazalete):

```powershell
.\scripts\iniciar_demo.ps1 -Fuente serie -PuertoSerie COM3
```

Antes de conectar a una persona lee la advertencia de seguridad eléctrica de
`firmware/brazalete_esp32/README.md` en SynapVolit.

## 8. Reproducir la validación entre sesiones (opcional)

Requiere haber descargado las sesiones 1 y 2 de los participantes 1 a 5 (paso 3, segunda opción):

```powershell
Set-Location C:\Proyectos\DUNNE\SynapVolit
uv run python -m synapvolit.validacion --participantes 1 2 3 4 5 --sesiones 1 2
```

Primero verifica la integridad de los 700 archivos y se detiene si alguno no coincide. Resultado
esperado (exactitud por decisión a 8 Hz; entrenamiento y prueba separados por ensayo):

| Participante | Intra S1 | Entre sesiones | Adaptado | Recalibrado |
|---|---|---|---|---|
| P1 | 86% | 78% | 81% | 91% |
| P2 | 79% | 79% | 84% | 97% |
| P3 | 96% | 93% | 91% | 94% |
| P4 | 98% | 92% | 93% | 95% |
| P5 | 99% | 96% | 96% | 97% |
| Media (DE) | 92% (9%) | 88% (8%) | 89% (6%) | 95% (3%) |

La verificación de 20 s pasa en 4 de 5 participantes (no pasa P4). Intra S1 tiene una fuga de
selección de canales: elegir canales con los 7 ensayos incluye los 4 de prueba; el titular honesto
es "entre sesiones".

## 9. Dónde quedan los datos

| Qué | Dónde | ¿Va a Git? |
|---|---|---|
| Registros originales de GRABMyo | `SynapVolit\data\raw\` | No (ignorado) |
| Señal convertida | `SynapVolit\data\processed\` | No (ignorado) |
| Registros de sesión y perfiles de calibración | `%LOCALAPPDATA%\SynapVolit\pacientes\<código>` | No (fuera del repositorio) |
| Registros de cada ejecución del lanzador | `%TEMP%\wristquest_demo` | No |

Nunca subas datos de personas al repositorio. Para borrar los datos de un paciente, elimina su
carpeta en `%LOCALAPPDATA%\SynapVolit\pacientes`.

## 10. Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `uv` o `git` no se reconocen | Cierra y abre PowerShell tras instalar; si sigue, reinstala con `winget` |
| "Falta la señal de demostración" | No se hizo el paso 4, o se hizo con otra persona o sesión |
| "El motor se cerró al arrancar" (lanzador) | Abre `%TEMP%\wristquest_demo\motor.log` y `motor.err`; casi siempre es el punto anterior |
| "El puerto 8765 (o 8000) ya está en uso" | Quedó otro motor, servidor o el puente viejo abierto; ciérralo |
| "Sin conexión con el motor" en el juego | Ver el recuadro del paso 6 |
| La descarga se corta o da error | Repite el script del paso 3; salta lo ya descargado |
| Un archivo no coincide con SHA256SUMS | Bórralo y repite la descarga |
| Las pruebas del paso 2 fallan | Pega solo las últimas 20 líneas de la salida al pedir ayuda |

## 11. Registrar versiones para una publicación o póster

Para que un resultado sea reproducible, anota esto junto a él:

```powershell
git -C C:\Proyectos\DUNNE\SynapVolit rev-parse --short HEAD
git -C C:\Proyectos\DUNNE\WristQuest rev-parse --short HEAD
uv --version
```

Y cita el dataset (APA 7):

Jiang, N., Pradhan, A., & He, J. (2024). *Gesture Recognition and Biometrics ElectroMyogram
(GRABMyo)* (versión 1.1.0) [Conjunto de datos]. PhysioNet. https://doi.org/10.13026/89dm-f662

Pradhan, A., He, J., & Jiang, N. (2022). Multi-day dataset of forearm and wrist electromyogram for
hand gesture recognition and biometrics. *Scientific Data, 9*, 733.
https://doi.org/10.1038/s41597-022-01836-y
