"""R2, diagnóstico EXPLORATORIO (no cambia el criterio GO): ¿hubo nubes frías DESPUÉS de la hora de referencia en las 8 tormentas ciegas?

Motivo: varias horas del catálogo son vagas ("la tarde" -> 12:00, inicio de la ventana): las 6 h previas a t0 caerían de mañana.
Se baja MERGIR de t0 a t0 + 8 h y se compara la Tb mínima sobre las quebradas y la zona alta con la de 6 h ANTES de t0 y con los controles.
Salida: modelo/mejoras/R2/despues_t0.csv
"""
import numpy as np
import pandas as pd

from descargar_mergir import DATOS, LAT0, LAT1, LON0, LON1, UTC, _coords, bajar_hora, url_hora
from nubes_frias import QLAT, QLON

HORAS = 8


def main():
    import earthaccess

    earthaccess.login(strategy="netrc")
    s = earthaccess.get_requests_https_session()
    lat, lon = _coords(s, url_hora(pd.Timestamp("2015-03-23 19:00")))
    i, j = np.where((lat >= LAT0) & (lat <= LAT1))[0], np.where((lon >= LON0) & (lon <= LON1))[0]
    la, lo = lat[i], lon[j]
    mq = ((la[:, None] >= QLAT[0]) & (la[:, None] <= QLAT[1])) & ((lo[None, :] >= QLON[0]) & (lo[None, :] <= QLON[1]))
    ma = np.broadcast_to(lo[None, :] > QLON[1], mq.shape)
    ev = pd.read_csv(DATOS / "instantes_tormentas.csv", parse_dates=["fecha", "t0_local"])
    c = pd.read_csv(DATOS.parents[3] / "catalogo_huaicos_chosica" / "catalogo_huaicos_chosica.csv", parse_dates=["fecha"])
    filas = []
    for r in ev[ev.ciega].itertuples():
        tb = np.stack([bajar_hora(s, (r.t0_local + UTC).floor("h") + pd.Timedelta(hours=k), i, j) for k in range(HORAS + 1)]).reshape(-1, len(i), len(j))
        conf = "".join(sorted(set(c[(c.fecha == r.fecha) & c.en_piloto & c.usable_horario].conf_temporal)))
        hora_min = np.nanmin(tb[:, mq], axis=1)
        filas.append(dict(fecha=r.fecha.date(), t0_local=r.t0_local, conf_temporal=conf,
                          tbmin_quebradas_t0_mas8h=float(np.nanmin(tb[:, mq])), tbmin_alta_t0_mas8h=float(np.nanmin(tb[:, ma])),
                          f235_quebradas_max_t0_mas8h=float(np.nanmax(np.nanmean(tb[:, mq] < 235, axis=1))),
                          hora_local_mas_fria=(r.t0_local.floor("h") + pd.Timedelta(minutes=30 * int(np.nanargmin(hora_min)))).strftime("%H:%M")))
    out = pd.DataFrame(filas).merge(pd.read_csv(DATOS.parent / "nubes_frias_tormentas.csv", parse_dates=["fecha"])
                                    .assign(fecha=lambda d: d.fecha.dt.date)[["fecha", "tbmin_quebradas_6h", "tbmin_alta_6h"]], on="fecha")
    out.to_csv(DATOS.parent / "despues_t0.csv", index=False)
    pd.set_option("display.width", 220)
    print(out.to_string(index=False))
    print("Referencia controles (6 h antes): Tb mín quebradas p5/p50 = 217/257.5 K")


if __name__ == "__main__":
    main()
