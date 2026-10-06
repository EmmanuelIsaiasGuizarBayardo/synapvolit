# Datos de simulación: GRABMyo

El simulador reproduce sEMG real de **GRABMyo** (Jiang, Pradhan y He, 2024), publicado en
PhysioNet bajo CC BY 4.0. Se eligió sobre NinaPro DB2 porque registra justo los movimientos de
WristQuest (extensión, flexión, supinación, pronación y reposo), es de acceso abierto sin
registro y tiene tres sesiones por persona, útiles para probar la recalibración entre días.

| Gesto de GRABMyo | Clase del contrato |
|---|---|
| 11 Wrist Extension | 1 extensión |
| 12 Wrist Flexion | 2 flexión |
| 14 Forearm Pronation | 3 pronación |
| 13 Forearm Supination | 4 supinación |
| 17 Rest | 0 reposo |

Limitación: los electrodos son dos anillos alrededor del antebrazo, no electrodos sobre
músculos concretos. El canal asignado a "pronación" es el par que más se activa en pronación,
no el pronador redondo aislado.

## 1. Descarga (una persona, una sesión: ~45 MB)

Los originales van a `data/raw/grabmyo/1.1.0/`, que Git ignora. Esta carpeta no la modifica
ningún script del repositorio: la descarga es un paso manual que se registra en
`data/raw/README.md`.

```powershell
$ProgressPreference = "SilentlyContinue"   # en PowerShell 5.1 la barra de progreso vuelve lenta la descarga
$base = "https://physionet.org/files/grabmyo/1.1.0"
$s = 1; $p = 1
$dir = "data\raw\grabmyo\1.1.0\Session$s\session${s}_participant$p"
New-Item -ItemType Directory -Force $dir | Out-Null
foreach ($g in 11, 12, 13, 14, 17) {
    foreach ($t in 1..7) {
        foreach ($ext in "hea", "dat") {
            $archivo = "session${s}_participant${p}_gesture${g}_trial$t.$ext"
            Invoke-WebRequest "$base/Session$s/session${s}_participant$p/$archivo" -OutFile "$dir\$archivo" -UseBasicParsing
        }
    }
}
```

## 2. Conversión

```powershell
uv run python -m synapvolit.datasets.grabmyo --sesion 1 --participante 1
```

Escribe `data/processed/grabmyo/s1_p01.csv` y su `.json` con la procedencia: canales elegidos,
especificidad de cada uno y transformaciones aplicadas.

## 3. Simulación

```powershell
uv run python -m synapvolit.transporte --escenario limpio --segundos 10
uv run python -m synapvolit.transporte --escenario fallas --segundos 30
```

## Desviación de la preferencia BIDS

El estándar prefiere convertir los datasets a BIDS al ingresar. GRABMyo se conserva en su
formato WFDB original porque el simulador solo necesita un derivado de cuatro canales, y el
formato original se lee con una biblioteca mantenida (`wfdb`). Si el motor llega a entrenar
modelos con varios datasets, se convertirá a BIDS en ese momento.

## Validación entre sesiones

Descarga varias personas y dos sesiones (cada persona y sesión ocupa ~45 MB):

```powershell
$ProgressPreference = "SilentlyContinue"
$base = "https://physionet.org/files/grabmyo/1.1.0"
$raiz = "data\raw\grabmyo\1.1.0"
Invoke-WebRequest "$base/SHA256SUMS.txt" -OutFile "$raiz\SHA256SUMS.txt" -UseBasicParsing
foreach ($s in 1, 2) {
    foreach ($p in 1..5) {
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
uv run python -m synapvolit.validacion --participantes 1 2 3 4 5 --sesiones 1 2
```

La validación compara primero cada archivo con `SHA256SUMS.txt` y se detiene si alguno no coincide.
Los escenarios que reporta están descritos en `src/synapvolit/validacion.py`.
