"""Replica el modelo final (v3: P1 = B1 en la zona + P2 por quebrada; niveles de la entrega) y verifica el resultado contra la referencia.

Uso (desde la raíz del repo, con el entorno de requirements.txt):
  python replicar.py                    # cadena completa con los insumos versionados en git + verificación (~2-5 min)
  python replicar.py --recalcular       # igual, pero mueve antes los cachés a un respaldo para recalcular TODO desde los insumos
  python replicar.py --desde-partes     # además reconstruye el catálogo y las etiquetas v1 desde las partes del catálogo
  python replicar.py --descargar        # además vuelve a bajar los insumos (IMERG Early requiere cuenta Earthdata en _netrc / .netrc)
  python replicar.py --con-referencias  # además regenera los modelos ANTERIORES que la Fase A usa solo como comparación (~40 min más)
  python replicar.py --solo-verificar   # solo compara las salidas actuales con la referencia
  python replicar.py --generar-referencia   # (mantenedor) guarda las salidas actuales como referencia
Pasos (cada uno es un script que también se puede correr solo; ver REPLICAR.md):
  [0] descargas opcionales  [1] catálogo + etiquetas v1 (opcional)  [2] etiquetas v2  [3] eventos de lluvia y A2 (Fase A)
  [4] B1 = intensidad + estado (Fase B1)  [5] modelo final: P1, umbrales y P2  [6] calibración (Platt, kappa y su rango; validación cruzada)
  [7] entrega al dashboard (ejemplo 2022-23, nivel oficial y nivel_con_lluvia, probabilidades calibradas)  [8] verificación
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent
PY = sys.executable
REF = RAIZ / "replicacion_referencia.json"
CAT = RAIZ / "catalogo_huaicos_chosica"
V3 = RAIZ / "modelo" / "v3"
CACHES = [V3 / "_cache", V3 / "A" / "fase_a_eventos.parquet", V3 / "B" / "fase_b1_eventos.parquet"]
INSUMOS = {
    "IMERG Early (60 meses, dic-abr 2014-15..2025-26)": (RAIZ / "lluvia" / "datos" / "early", "imerg_early_????-??.nc", 60),
    "ERA5-Land (Open-Meteo, 5 celdas)": (V3 / "datos" / "raw" / "openmeteo", "era5_land.parquet", 1),
    "ICEN (IGP/ENFEN)": (V3 / "datos" / "raw" / "icen", "ICEN.txt", 1),
}


def correr(nombre, args, cwd=RAIZ):
    print(f"\n=== {nombre}: {' '.join(str(a) for a in args)}", flush=True)
    t0 = time.time()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([PY, *map(str, args)], cwd=cwd, env=env)
    if r.returncode != 0:
        raise SystemExit(f"FALLÓ el paso «{nombre}» (código {r.returncode}). Revisa el mensaje de arriba.")
    print(f"    listo en {(time.time() - t0) / 60:.1f} min", flush=True)


def huella(ruta):
    """SHA-256 del contenido con saltos de línea normalizados (git puede convertir LF <-> CRLF al clonar en Windows)."""
    return hashlib.sha256(Path(ruta).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def resumen_actual():
    out = {"etiquetas": {}}
    for v, pat in (("v1", "etiquetas_horarias_H{H}.parquet"), ("v2", "etiquetas_horarias_v2_H{H}.parquet")):
        for H in (3, 6, 12, 24):
            e = pd.read_parquet(CAT / pat.format(H=H))
            out["etiquetas"][f"{v}_H{H}"] = dict(filas=len(e), positivos=int((e.y == 1).sum()), nan=int(e.y.isna().sum()))
    b1 = pd.read_csv(V3 / "B" / "fase_b1_resumen.csv")
    f = b1[b1.metodo.str.startswith("(a) A2 + estado (humedad 5 d)")].iloc[0]
    out["B1"] = dict(TSS=float(f.TSS), aciertos=int(f.aciertos), fallos=int(f.fallos), falsas=int(f.falsas))
    meta = json.loads((V3 / "final" / "metadatos_final.json").read_text(encoding="utf-8"))
    out["umbrales"] = {H: dict(rojo=u["rojo"], amarillo=u["amarillo"], rojo_TSS=u["rojo_TSS"]) for H, u in meta["umbrales"].items()}
    out["p2"] = pd.read_csv(V3 / "final" / "p2_final.csv", index_col=0).iloc[:, 0].round(6).to_dict()
    out["huella_modelo_p1"] = huella(V3 / "final" / "p1_b1.json")
    ej = RAIZ / "modelo" / "v3_1" / "entrega" / "ejemplo_2022_23_m3.csv"
    T = pd.read_csv(ej, usecols=["quebrada_id", "H", "nivel", "nivel_con_lluvia"])
    una = T[T.quebrada_id == "quirio"]
    cal = json.loads((V3 / "final" / "calibracion.json").read_text(encoding="utf-8"))["por_H"]
    out["calibracion"] = {H: {k: v[k] for k in ("a", "b", "kappa", "kappa_min", "kappa_max", "tasa_base")} for H, v in cal.items()}
    val = pd.read_csv(V3 / "final" / "calibracion_validacion.csv")
    out["calibracion_validacion"] = {f"H{r.H} {r.tramo_p_zona}": {k: (int(getattr(r, k)) if k in ("horas", "positivos") else float(getattr(r, k)))
                                                                  for k in ("horas", "positivos", "p_zona_media", "p_cal_media", "frecuencia_observada", "suma_p_cal")
                                                                  if pd.notna(getattr(r, k))} for r in val.itertuples()}
    out["ejemplo_2022_23"] = dict(filas=len(T), nivel={f"H{H}": g.nivel.value_counts().to_dict() for H, g in una.groupby("H")},
                                  nivel_con_lluvia={f"H{H}": g.nivel_con_lluvia.value_counts().to_dict() for H, g in una.groupby("H")}, huella=huella(ej))
    return out


def verificar():
    ref = json.loads(REF.read_text(encoding="utf-8"))
    act = resumen_actual()
    fallas = []

    def igual(nombre, a, b, tol=1e-6):
        if isinstance(a, dict):
            for k in a:
                igual(f"{nombre}.{k}", a[k], b.get(k) if isinstance(b, dict) else None, tol)
            return
        ok = (abs(a - b) <= tol * max(1.0, abs(a))) if isinstance(a, float) and b is not None else a == b
        if not ok:
            fallas.append(f"{nombre}: referencia {a} vs replicado {b}")

    for k in ("etiquetas", "B1", "umbrales", "p2", "calibracion", "calibracion_validacion"):
        igual(k, ref[k], act[k])
    igual("ejemplo_2022_23.filas", ref["ejemplo_2022_23"]["filas"], act["ejemplo_2022_23"]["filas"])
    igual("ejemplo_2022_23.nivel", ref["ejemplo_2022_23"]["nivel"], act["ejemplo_2022_23"]["nivel"])
    igual("ejemplo_2022_23.nivel_con_lluvia", ref["ejemplo_2022_23"]["nivel_con_lluvia"], act["ejemplo_2022_23"]["nivel_con_lluvia"])
    exacto = act["huella_modelo_p1"] == ref["huella_modelo_p1"] and act["ejemplo_2022_23"]["huella"] == ref["ejemplo_2022_23"]["huella"]
    print("\n=== VERIFICACIÓN contra replicacion_referencia.json")
    print(f"  B1 (validación LOSO por evento): TSS {act['B1']['TSS']} (ref. {ref['B1']['TSS']}), aciertos {act['B1']['aciertos']} de "
          f"{act['B1']['aciertos'] + act['B1']['fallos']}, falsas alarmas {act['B1']['falsas']}")
    print("  Umbral rojo por H: " + ", ".join(f"H={H}: {act['umbrales'][H]['rojo']:.5f}" for H in act["umbrales"]))
    print("  Calibración por H (a, b, kappa [mín, máx]): " + ", ".join(
        f"H={H}: {c['a']:.3f}, {c['b']:.3f}, {c['kappa']:.3f} [{c['kappa_min']:.3f}, {c['kappa_max']:.3f}]" for H, c in act["calibracion"].items()))
    print(f"  Modelo P1 y ejemplo idénticos byte a byte (salvo saltos de línea): {'SÍ' if exacto else 'NO'}")
    if fallas:
        print("  DIFERENCIAS:\n   - " + "\n   - ".join(fallas))
        print("RESULTADO: NO REPLICA (ver diferencias). Causas típicas: otra versión de xgboost/pandas (usa requirements.txt) o insumos re-descargados.")
        return False
    print("RESULTADO: REPLICA OK" + ("" if exacto else " (métricas, umbrales y niveles iguales; archivos no idénticos byte a byte)"))
    return True


def main():
    a = set(sys.argv[1:])
    if "--generar-referencia" in a:
        REF.write_text(json.dumps(resumen_actual(), indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"Referencia guardada en {REF.name}")
        return
    if "--solo-verificar" in a:
        sys.exit(0 if verificar() else 1)
    t0 = time.time()
    if "--descargar" in a:
        correr("[0] IMERG Early (Earthdata; ~8 h si falta todo; reanuda)", [RAIZ / "lluvia" / "descargar_masivo.py", "--procesos", "24", "--url-directa"])
        correr("[0] ERA5-Land vía Open-Meteo", [V3 / "datos" / "descargar_openmeteo.py", "--solo", "era5_land"])
        correr("[0] ICEN", [V3 / "datos" / "descargar_icen.py", "--forzar"])
    faltan = []
    for nombre, (carpeta, patron, n) in INSUMOS.items():
        k = len(list(carpeta.glob(patron)))
        print(f"Insumo {nombre}: {k}/{n} archivo(s) en {carpeta.relative_to(RAIZ)}")
        if k < n:
            faltan.append(nombre)
    if faltan:
        raise SystemExit("Faltan insumos: " + ", ".join(faltan) + ". Corre con --descargar o revisa REPLICAR.md.")
    if "--recalcular" in a:
        resp = V3 / f"_respaldo_cache_{time.strftime('%Y%m%d_%H%M%S')}"
        for c in CACHES:
            if c.exists():
                resp.mkdir(exist_ok=True)
                shutil.move(str(c), str(resp / c.name))
        print(f"Cachés movidos a {resp.relative_to(RAIZ) if resp.exists() else '(no había)'}: todo se recalcula desde los insumos.")
    elif any(c.exists() for c in CACHES):
        print("AVISO: hay cachés de una corrida anterior (modelo/v3/_cache, eventos): se REUTILIZAN. Usa --recalcular para rehacer todo.")
    if "--desde-partes" in a:
        # construir_catalogo.py deja un etiquetas_horarias_H6 POR NOMBRE (v0); etiquetas_por_quebrada.py lo reemplaza por el definitivo: SIEMPRE en este orden
        correr("[1] catálogo desde las partes", [CAT / "construir_catalogo.py"], cwd=CAT)
        correr("[1] etiquetas v1 por quebrada", [CAT / "etiquetas_por_quebrada.py"], cwd=CAT)
    correr("[2] etiquetas v2 (verifica que reproduce v1 bit a bit)", [CAT / "etiquetas_v2.py"])
    if "--con-referencias" in a:
        correr("[2b] modelos anteriores (solo comparación en la Fase A)", [RAIZ / "modelo" / "etiquetas_v2" / "correr.py"])
    correr("[3] Fase A: eventos de lluvia y modelos de intensidad", [V3 / "A" / "fase_a.py"])
    correr("[4] Fase B1: intensidad + estado", [V3 / "B" / "fase_b1.py"])
    correr("[5] modelo final: P1 (todas las temporadas), umbrales por H y P2", [V3 / "final" / "modelo_final.py", "entrenar"])
    correr("[6] calibración: Platt por H, kappa y su rango, validación cruzada por temporada", [V3 / "final" / "calibracion.py"])
    correr("[7] entrega al dashboard: ejemplo 2022-23 fuera de muestra, niveles y probabilidades calibradas", [RAIZ / "modelo" / "v3_1" / "entrega" / "entrega_dashboard.py", "ejemplo"])
    print(f"\nCadena completa en {(time.time() - t0) / 60:.1f} min")
    sys.exit(0 if verificar() else 1)


if __name__ == "__main__":
    main()
