"""Prueba del DECODIFICADOR y del RECORTE de 02_descargar_persiann_ccs.py con archivos SINTÉTICOS servidos desde localhost.
No usa ni produce datos reales de PERSIANN-CCS; solo comprueba (a) el parseo del índice, (b) la lectura del tipo de dato desde un README de ejemplo,
(c) que fila/columna -> latitud/longitud (59.98 - 0.04 i ; 0.02 + 0.04 j) sea la correcta, (d) la conversión de escala y NODATA, (e) el ensamblado mensual.
Salida: salida/prueba_sintetica_decodificador.txt
"""
import gzip
import http.server
import importlib.util
import socketserver
import tempfile
import threading
from datetime import datetime
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("desc", AQUI / "scripts" / "02_descargar_persiann_ccs.py")
desc = importlib.util.module_from_spec(spec); spec.loader.exec_module(desc)
log = []


def say(s):
    print(s); log.append(s)


def hacer_servidor(raiz, formato, capa="plano"):
    """formato: 'i2x100' o 'f4'. Crea 24 horas del 2015-03-23 (día juliano 82) con un patrón conocido."""
    sl_f, sl_c, lat, lon = desc.indices_recorte(desc.bbox())
    carpeta = raiz / "2015" if capa == "anio" else raiz
    carpeta.mkdir(exist_ok=True)
    if capa == "anio":   # el índice real tiene 2000/ con archivos 'rgccs0003820.bin.gz' (otro prefijo) además de 2015/ con 'rgccs1h…'
        (raiz / "2000").mkdir(exist_ok=True)
        (raiz / "2000" / "rgccs0003820.bin.gz").write_bytes(gzip.compress(b"x"))
    for h in range(24):
        if formato == "i2x100":
            a = np.zeros((desc.NFIL, desc.NCOL), ">i2"); a[:] = desc.NODATA
            a[sl_f, sl_c] = ((np.arange(sl_f.start, sl_f.stop)[:, None] * 7 + np.arange(sl_c.start, sl_c.stop)[None, :] * 13 + h) % 2000).astype(">i2")   # 0..19.99 mm x 100
        else:
            a = np.full((desc.NFIL, desc.NCOL), desc.NODATA, ">f4")
            a[sl_f, sl_c] = (((np.arange(sl_f.start, sl_f.stop)[:, None] * 7 + np.arange(sl_c.start, sl_c.stop)[None, :] * 13 + h) % 2000) / 100).astype(">f4")
        (carpeta / f"rgccs1h1508{2:01d}{h:02d}.bin.gz").write_bytes(gzip.compress(a.tobytes(), 1))
    (raiz / "readme.hrly").write_text("hrly global ccs data, row centric format. big-endian short integers, units mm/hr x 100, NODATA -9999. 3000 x 9000" if formato == "i2x100"
                                      else "hrly ccs: 4-byte floats big-endian in mm/hr, NODATA -9999")


def correr(formato, capa="plano"):
    tmp = Path(tempfile.mkdtemp())
    hacer_servidor(tmp, formato, capa)
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(tmp), **k)
    handler.log_message = lambda *a: None
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    desc.CARPETA = Path(tempfile.mkdtemp())   # la salida sintética NO se mezcla con datos reales
    class A: url_base = base; dtype = None; escala = None; prefijo = "rgccs1h"; convencion = "inicio"
    cfg = desc.configurar(A)
    say(f"[{formato}/{capa}] estructura del índice: {'subcarpetas por año' if cfg['capa'] else 'archivos en la carpeta'} | formato inferido del README de ejemplo: {cfg['dtype']} escala {cfg['escala']} | prefijo {cfg['pref']} | nombre con hora {cfg['con_hora']} | primer archivo {cfg['primero']}")
    if capa == "anio":
        u = desc.url_archivo(cfg, datetime(2015, 3, 23, 5))
        say(f"[{formato}/{capa}] prefijo del año 2015 (el primer archivo del índice es de 2000 con otro prefijo): {u.rsplit('/', 1)[-1]}")
        assert u.endswith("2015/rgccs1h1508205.bin.gz"), u
    ok, faltan = desc.dia_a_npz(base, datetime(2015, 3, 23).date(), cfg, 4)
    say(f"[{formato}] día 2015-03-23: completo={ok}, horas faltantes={faltan}")
    ruta, n = desc.ensamblar_mes(2015, 3, cfg)
    import xarray as xr
    da = xr.open_dataset(ruta)["mm_h"]
    # valor esperado en el píxel (i,j) global a la hora h: ((7 i + 13 j + h) % 2000)/100
    pruebas = []
    for h in (0, 5, 23):
        for (la, lo) in ((cfg["lat"][0], cfg["lon"][0]), (cfg["lat"][-1], cfg["lon"][-1]), (cfg["lat"][len(cfg["lat"]) // 2], cfg["lon"][len(cfg["lon"]) // 2])):
            i = int(round((desc.LAT0 - la) / desc.PASO)); j = int(round((lo + 360 - desc.LON0) / desc.PASO))
            esp = ((7 * i + 13 * j + h) % 2000) / 100
            obt = float(da.sel(time=datetime(2015, 3, 23, h), lat=la, lon=lo))
            pruebas.append(abs(esp - obt) < 1e-4)
    say(f"[{formato}] recorte {len(cfg['lat'])} x {len(cfg['lon'])} píxeles, lat {cfg['lat'].min()}..{cfg['lat'].max()}, lon {cfg['lon'].min()}..{cfg['lon'].max()} | {n} horas | píxeles verificados contra la fórmula: {sum(pruebas)}/{len(pruebas)}")
    say(f"[{formato}] valores: mínimo {float(da.min()):.2f}, máximo {float(da.max()):.2f} mm/h, NaN {float(da.isnull().mean()) * 100:.1f} % (esperado 0 dentro del recorte)")
    srv.shutdown()
    return all(pruebas)


README_REAL = """hrly global ccs data is in row centric format.

name scheme:
        rgccs1h0934923.bin.gz
w/ YYDDDHH  date/time
The HH represents the beginning of the hrly time period like so:
        HH:00 to HH:59

data are organized into YYYY subdirectories.

Format is:
    binary in row centric format.
    short integer
    data are big-endian.
    units mm/hr *100

coverage is:
60N to 60S and 0 to 360 Longitude
3000 rows x 9000 cols

first value is NW most pixel centered at .02 lon and 59.98 N lat.
"""   # texto REAL de readme.hrly (lo pegó el usuario el 12/10/2026)


def readme_real():
    d, e = desc.inferir_formato(README_REAL)
    ok = (d, e) == (">i2", 100)
    say(f"[README real] formato inferido: {d} escala {e} (esperado >i2 escala 100): {ok}")
    return ok


def indice_no_reconocido():
    """Un índice con nombres que no siguen el patrón debe DETENERSE e imprimir el HTML real (diagnóstico), no fallar con IndexError."""
    tmp = Path(tempfile.mkdtemp()); (tmp / "datos_raros_20150323.txt").write_text("x")
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(tmp), **k)
    handler.log_message = lambda *a: None
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        desc.explorar(f"http://127.0.0.1:{srv.server_address[1]}/")
        ok = False
    except SystemExit as e:
        ok = "DIAGNÓSTICO" in str(e) or "No reconozco" in str(e)
    srv.shutdown()
    say(f"[índice no reconocido] se detiene con mensaje de diagnóstico: {ok}")
    return ok


if __name__ == "__main__":
    r1, r2, r3 = correr("i2x100"), correr("f4"), correr("i2x100", "anio")
    r4 = indice_no_reconocido()
    r5 = readme_real()
    say(f"RESULTADO: {'OK' if r1 and r2 and r3 and r4 and r5 else 'FALLÓ'} (esto valida el código, NO los datos de PERSIANN-CCS)")
    (AQUI / "salida" / "prueba_sintetica_decodificador.txt").write_text("\n".join(log) + "\n")
