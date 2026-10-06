# data/raw — INMUTABLE

Esta carpeta no se modifica nunca mediante scripts. Todo derivado se escribe en
`data/processed/`.

## Convención

Organizar según **BIDS-EEG** (Pernet et al., 2019). Estructura mínima:

```
data/raw/
├── dataset_description.json
├── participants.tsv
└── sub-01/
    └── eeg/
        ├── sub-01_task-<tarea>_eeg.<ext>
        ├── sub-01_task-<tarea>_events.tsv
        └── sub-01_task-<tarea>_channels.tsv
```

Para convertir o leer: `mne-bids` (`pip install mne-bids`).

## Procedencia

| Dataset | Origen | Fecha de descarga | Licencia |
|---------|--------|-------------------|----------|
|         |        |                   |          |
