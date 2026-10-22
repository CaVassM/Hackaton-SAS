#!/bin/bash
# Versión rápida de la re-corrida tras el paso 9.2: solo lo que decide el modelo final (V1 y V1+D como referencias, restringido, OOF, niveles, diagnósticos).
# Las ablaciones de ingeniería (ingenieria.py completo), la confirmación con logística/RF y el techo sin latencia quedan para después (correr_todo.sh).
cd "$(dirname "$0")"
LOG=salida/correr_rapido_log.txt
paso() { echo "=== $(date +%H:%M:%S) $* ===" | tee -a $LOG; "$@" >> $LOG 2>&1 || { echo "FALLÓ: $*" | tee -a $LOG; exit 1; }; }
: > $LOG
cat > /tmp/v1d.py <<'P'
import pandas as pd
from ingenieria import correr
from tabla3 import FEATURES_V1, GRUPOS_NUEVOS, RUTA
t = pd.read_parquet(RUTA).reset_index(drop=True)
D = GRUPOS_NUEVOS["D regional"]
for s, n in ((0, "V1_mas_D"), (1, "V1_mas_D_semilla1"), (2, "V1_mas_D_semilla2")):
    correr(t, FEATURES_V1 + D, n, s)
P
paso env PYTHONPATH=. python3 /tmp/v1d.py
paso python3 restringido.py
paso python3 restringido_reporte.py
paso python3 oof.py
paso python3 diagnostico_eventos.py
paso python3 umbrales.py
paso python3 verificar_umbrales.py
paso python3 diagnostico_era5_ciegos.py
echo "=== $(date +%H:%M:%S) RAPIDO LISTO ===" | tee -a $LOG
