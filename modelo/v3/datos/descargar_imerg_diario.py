"""IMERG Early DIARIO (GPM_3IMERGDE V07, día UTC, mm/día) recortado a lat -30..-8, lon -81..-67 (Perú y norte de Chile), 2001-01-01 a 2026-04-30.

Para C1 (clima de cada cuenca) y E (modelo diario multizona: el MISMO producto en todas las zonas, Chosica incluida).
El OPeNDAP de GPM (gpm1.gesdisc) respondía 503; se lee el archivo por rangos (bloques de 1 MB). Sus bloques internos son de media esfera
(3600 lon x 900 lat), así que cada día baja unos MB. Credenciales: _netrc (earthaccess), nunca en el código.
Caché por día en datos/raw/imerg_diario/_cache/AAAA/AAAAMMDD.npy (float32 (lat, lon), NaN = sin dato); grilla en grilla.npz.
Uso: python modelo/v3/datos/descargar_imerg_diario.py [--procesos 16] [--desde 2001] [--hasta 2026]
"""
import argparse
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
DEST = AQUI / "raw" / "imerg_diario"
LAT, LON = (-30.0, -8.0), (-81.0, -67.0)
FIN = pd.Timestamp("2026-04-30")
_FS = None


def _fs():
    global _FS
    if _FS is None:
        import earthaccess

        earthaccess.login(strategy="netrc")
        _FS = earthaccess.get_fsspec_https_session()
    return _FS


def leer(dia, url, reintentos=5):
    import xarray as xr

    ruta = DEST / "_cache" / dia[:4] / f"{dia}.npy"
    if ruta.exists():
        return dia, "ya"
    for k in range(reintentos):
        try:
            with _fs().open(url, block_size=1024 * 1024, cache_type="blockcache") as f, xr.open_dataset(f, engine="h5netcdf") as ds:
                v = ds["precipitation"].isel(time=0).sel(lat=slice(*LAT), lon=slice(*LON)).transpose("lat", "lon").load().values.astype("float32")
            v[v < 0] = np.nan
            ruta.parent.mkdir(parents=True, exist_ok=True)
            tmp = ruta.with_suffix(".tmp.npy")
            np.save(tmp, v)
            tmp.replace(ruta)
            return dia, "ok"
        except Exception as e:  # noqa: BLE001
            err = repr(e)[:120]
            time.sleep(5 * (k + 1))
    return dia, f"FALLO {err}"


def urls(anio):
    import earthaccess

    earthaccess.login(strategy="netrc")
    fin = min(pd.Timestamp(f"{anio}-12-31"), FIN)
    res = earthaccess.search_data(short_name="GPM_3IMERGDE", version="07", temporal=(f"{anio}-01-01", fin.strftime("%Y-%m-%d")))
    out = {}
    for r in res:
        u = r.data_links()[0]
        d = u.split("3IMERG.")[1][:8]
        out[d] = u
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procesos", type=int, default=16)
    ap.add_argument("--desde", type=int, default=2001)
    ap.add_argument("--hasta", type=int, default=2026)
    a = ap.parse_args()
    DEST.mkdir(parents=True, exist_ok=True)
    log = open(DEST / "descarga.log", "a", encoding="utf-8")
    tareas = {}
    for anio in range(a.desde, a.hasta + 1):
        u = urls(anio)
        tareas.update(u)
        print(f"{anio}: {len(u)} días", flush=True)
    pend = {d: u for d, u in tareas.items() if not (DEST / "_cache" / d[:4] / f"{d}.npy").exists()}
    print(f"{len(tareas)} días; pendientes {len(pend)}", flush=True)
    t0, n, fallos = time.time(), 0, []
    with ProcessPoolExecutor(a.procesos) as ex:
        fut = [ex.submit(leer, d, u) for d, u in sorted(pend.items())]
        for f in as_completed(fut):
            d, est = f.result()
            n += 1
            if est.startswith("FALLO"):
                fallos.append(d)
                log.write(f"{d} {est}\n")
            if n % 200 == 0:
                msg = f"{n}/{len(pend)} días | {(time.time() - t0) / 60:.0f} min | ~{(time.time() - t0) / n * (len(pend) - n) / 60:.0f} min restantes | fallos {len(fallos)}"
                print(msg, flush=True)
                log.write(msg + "\n")
                log.flush()
    # coordenadas (una vez) para documentar la grilla
    lat = np.round(np.arange(-89.95, 90, 0.1), 2)
    lon = np.round(np.arange(-179.95, 180, 0.1), 2)
    np.savez(DEST / "grilla.npz", lat=lat[(lat >= LAT[0]) & (lat <= LAT[1])], lon=lon[(lon >= LON[0]) & (lon <= LON[1])])
    print(f"TERMINADO en {(time.time() - t0) / 60:.0f} min; fallos {len(fallos)}: {fallos[:10]}", flush=True)
    log.write(f"TERMINADO fallos={len(fallos)}\n")


if __name__ == "__main__":
    main()
