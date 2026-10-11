#!/bin/bash
# Re-corre toda la cadena del modelo tras un cambio de etiquetas (paso 9.2). Se detiene en cada error y deja el log en salida/correr_todo_log.txt.
# Uso (desde modelo/):  bash correr_todo.sh
cd "$(dirname "$0")"
LOG=salida/correr_todo_log.txt
paso() { echo "=== $(date +%H:%M:%S) $* ===" | tee -a $LOG; "$@" >> $LOG 2>&1 || { echo "FALLÓ: $*" | tee -a $LOG; exit 1; }; }
: > $LOG
paso python3 auditoria.py
paso python3 baseline_logistica.py base
paso python3 baseline_logistica.py log1p
paso python3 arboles.py xgb
paso python3 arboles.py rf
paso python3 referencias_simples.py
paso python3 comparar_modelos.py
paso python3 ingenieria.py
paso python3 ingenieria_reporte.py
paso python3 ingenieria_confirmacion.py
paso python3 restringido.py
paso python3 restringido_reporte.py
paso python3 oof.py
paso python3 diagnostico_eventos.py
paso python3 umbrales.py
paso python3 verificar_umbrales.py
paso python3 diagnostico_era5_ciegos.py
paso python3 techo_sin_latencia.py
echo "=== $(date +%H:%M:%S) TODO LISTO ===" | tee -a $LOG
