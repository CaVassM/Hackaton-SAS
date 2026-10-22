"""R2: descarga GPM_MERGIR (temperatura de brillo infrarroja Tb, K; 4 km, 30 min) SOLO para las ventanas necesarias, por OPeNDAP (el servidor recorta).

Recuadro: lat -12.2 a -11.6, lon -77.0 a -76.3 (16 x 20 píxeles). Credenciales: _netrc de Earthdata (earthaccess, nunca en el código).
Leer el archivo directo NO sirve: sus bloques internos son de 1649 x 2474 píxeles (166 s por hora); OPeNDAP tarda ~1 s.

Diseño (fijado antes de descargar):
  - 14 tormentas = fechas con bloques de huaico en H=6 (modelo/salida/diagnostico_eventos_H6.csv). Hora de referencia t0 = primera hora útil
    del catálogo ese día en las 17 quebradas (hora local; UTC = local + 5 h). Se baja de t0 - 12 h a t0.
  - Controles: 500 instantes de ene-abr 2015-2026, en días a más de 2 días de CUALQUIER fecha del catálogo (también distritos vecinos),
    con la hora local de una tormenta al azar +-1 h. Se baja de t0 - 6 h a t0. Semilla 0.
Salida: modelo/mejoras/R2/datos/mergir_<tipo>.npz  (tb: (n, 2*horas, 16, 20) int16 en K, NaN como -1; lat, lon; tabla de instantes en .csv)
Uso: python modelo/mejoras/R2/descargar_mergir.py [--hilos 8]
"""
import argparse
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]
DATOS = AQUI / "datos"
DATOS.mkdir(exist_ok=True)
BASE = "https://disc2.gesdisc.eosdis.nasa.gov/opendap/MERGED_IR/GPM_MERGIR.1"
LAT0, LAT1, LON0, LON1 = -12.2, -11.6, -77.0, -76.3
N_CONTROLES = 500
H_EVENTO, H_CONTROL = 12, 6
UTC = pd.Timedelta(hours=5)


def instantes():
    b = pd.read_csv(RAIZ / "modelo" / "salida" / "diagnostico_eventos_H6.csv", parse_dates=["fecha"])
    c = pd.read_csv(RAIZ / "catalogo_huaicos_chosica" / "catalogo_huaicos_chosica.csv", parse_dates=["fecha"])
    u = c[c.en_piloto & c.usable_horario]
    t0 = u.assign(t=u.fecha + pd.to_timedelta(u.hora_inicio + ":00")).groupby("fecha").t.min()
    g = b.groupby("fecha").agg(bloques=("quebrada", "size"), imerg_6h_mediana=("mm_6h_real", "median"), imerg_6h_max=("mm_6h_real", "max"),
                               bloques_ciegos=("mm_6h_real", lambda s: int((s < 0.1).sum())))
    ev = g.assign(t0_local=t0.reindex(g.index)).reset_index()
    assert ev.t0_local.notna().all()
    ev["ciega"] = ev.imerg_6h_mediana < 0.1           # principal: la mayoría de sus quebradas no vio lluvia IMERG en las 6 h previas
    ev["ciega_estricta"] = ev.imerg_6h_max < 0.1      # ninguna quebrada la vio
    ev["tipo"], ev["id"] = "tormenta", [f"E{i:02d}" for i in range(len(ev))]

    rng = np.random.default_rng(0)
    excluir = set()
    for d in c.fecha.unique():
        for k in range(-2, 3):
            excluir.add(pd.Timestamp(d) + pd.Timedelta(days=k))
    dias = [d for d in pd.date_range("2015-01-01", "2026-04-30") if d.month <= 4 and d not in excluir]
    horas = ev.t0_local.dt.hour.to_numpy()
    filas = []
    for i, d in enumerate(rng.choice(dias, N_CONTROLES, replace=False)):
        h = int(np.clip(rng.choice(horas) + rng.integers(-1, 2), 0, 23))
        filas.append(dict(id=f"C{i:03d}", tipo="control", t0_local=pd.Timestamp(d) + pd.Timedelta(hours=h)))
    return ev, pd.DataFrame(filas)


def _coords(s, url):
    out = []
    for v in ("lat", "lon"):
        txt = s.get(url + f".ascii?{v}", timeout=120).text.split("\n", 1)[1]
        out.append(np.array([float(x) for x in txt.split("\n")[0].split(",")[1:]]))
    return out


def url_hora(t_utc):
    return f"{BASE}/{t_utc:%Y}/{t_utc.dayofyear:03d}/merg_{t_utc:%Y%m%d%H}_4km-pixel.nc4"


def bajar_hora(s, t_utc, i, j, reintentos=5):
    q = f".ascii?Tb[0:1][{i[0]}:{i[-1]}][{j[0]}:{j[-1]}]"
    for k in range(reintentos):
        try:
            r = s.get(url_hora(t_utc) + q, timeout=120)
            if r.status_code == 404:
                return np.full((2, len(i), len(j)), np.nan)
            r.raise_for_status()
            filas = [l for l in r.text.splitlines() if l.startswith("Tb[")]
            a = np.array([[float(x) for x in l.split(",")[1:]] for l in filas]).reshape(2, len(i), len(j))
            a[(a < 150) | (a > 340)] = np.nan   # relleno
            return a
        except Exception:
            time.sleep(2 * (k + 1))
    raise RuntimeError(f"falló {url_hora(t_utc)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hilos", type=int, default=8)
    a = ap.parse_args()
    import earthaccess

    earthaccess.login(strategy="netrc")
    s = earthaccess.get_requests_https_session()
    lat, lon = _coords(s, url_hora(pd.Timestamp("2015-03-23 19:00")))
    i = np.where((lat >= LAT0) & (lat <= LAT1))[0]
    j = np.where((lon >= LON0) & (lon <= LON1))[0]
    print(f"grilla {len(lat)} x {len(lon)} | recuadro {len(i)} x {len(j)} píxeles", flush=True)
    ev, ct = instantes()
    for tipo, tab, horas in (("tormentas", ev, H_EVENTO), ("controles", ct, H_CONTROL)):
        ruta = DATOS / f"mergir_{tipo}.npz"
        tab.to_csv(DATOS / f"instantes_{tipo}.csv", index=False)
        if ruta.exists():
            print(f"{ruta.name} ya existe", flush=True)
            continue
        t0 = time.time()
        # horas UTC [t0-horas, t0] (la hora t0 incluye las medias horas t0:00 y t0:30; se recorta luego al instante exacto)
        tareas = [(n, k, (r.t0_local + UTC).floor("h") - pd.Timedelta(hours=horas - k)) for n, r in enumerate(tab.itertuples()) for k in range(horas + 1)]
        tb = np.full((len(tab), 2 * (horas + 1), len(i), len(j)), np.nan, dtype="float32")
        with ThreadPoolExecutor(a.hilos) as ex:
            for c, ((n, k, t), x) in enumerate(zip(tareas, ex.map(lambda x: bajar_hora(s, x[2], i, j), tareas))):
                tb[n, 2 * k: 2 * k + 2] = x
                if c % 500 == 0:
                    print(f"  {tipo}: {c}/{len(tareas)} horas ({time.time() - t0:.0f} s)", flush=True)
        np.savez_compressed(ruta, tb=np.where(np.isnan(tb), -1, tb).astype("int16"), lat=lat[i], lon=lon[j], horas=horas)
        print(f"{ruta.name}: {tb.shape}, NaN {100 * np.isnan(tb).mean():.2f} %, {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
