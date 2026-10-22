"""Descarga el ICEN oficial (Índice Costero El Niño, IGP/ENFEN) a modelo/v3/datos/raw/icen/ICEN.txt.

Fuente: http://met.igp.gob.pe/datos/ICEN.txt (enlazado desde met.igp.gob.pe/variabclim/indices.html). Formato: comentarios con '%' y columnas año, mes, ICEN.
La copia usada para entrenar el modelo v3 (bajada el 12/10/2026, último dato jul-2026) está versionada en git; volver a bajarla puede traer valores
revisados y meses nuevos. Uso: python modelo/v3/datos/descargar_icen.py [--forzar]
"""
import sys
import urllib.request
from pathlib import Path

URL = "http://met.igp.gob.pe/datos/ICEN.txt"
DEST = Path(__file__).resolve().parent / "raw" / "icen" / "ICEN.txt"


def main():
    if DEST.exists() and "--forzar" not in sys.argv:
        print(f"Ya existe {DEST} (usa --forzar para reemplazarlo).")
        return
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        datos = r.read()
    if b"ICEN" not in datos[:400]:
        raise SystemExit("La respuesta no parece el archivo del ICEN; revisa la URL.")
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_bytes(datos)
    filas = [l for l in datos.decode("utf-8", "ignore").splitlines() if l.strip() and not l.startswith("%")]
    print(f"ICEN guardado en {DEST}: {len(filas)} meses, último {filas[-1].split()[:2]}")


if __name__ == "__main__":
    main()
