"""Etiquetas horarias v2: horas VAGAS (conf_temporal B) tratadas como RANGO. Archivos NUEVOS; las v1 no se tocan.

v1 (etiquetas_por_quebrada.py, carpeta del proyecto padre): y=1 si el INICIO de la ventana del evento cae en (t, t+H]. Con horas vagas
("la tarde" -> 12:00-18:00) eso adelanta los positivos al inicio del rango.
v2: para los 27 eventos B que generan positivos (17 quebradas, usable_horario), el rango [hora_inicio_v2, hora_fin_v2] de horas_B_v2.csv
(fuente releída; ver columnas decision, fuente_url, cita). Para la hora t (ventana (t, t+H]):
    y = 1    si (t, t+H] contiene TODO el rango (t < inicio y t + H >= fin)
    y = NaN  si lo toca parcialmente, y desde el inicio hasta 24 h después del fin (como v1)
    y = 0    si no lo toca
Todo lo demás (eventos A, sin hora, sin quebrada, quebradas fuera del piloto) se trata EXACTAMENTE como v1; se comprueba que con la regla v1
este script reproduce los parquets v1 bit a bit. Prohibido decidir horas con MERGIR/IMERG: solo las fuentes.
Uso: python catalogo_huaicos_chosica/etiquetas_v2.py   -> etiquetas_horarias_v2_H{3,6,12,24}.parquet
"""
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
DESDE, HASTA = "2015-01-01", "2026-06-30 23:00"
HORAS_POST = 24
HORIZONTES = (3, 6, 12, 24)


def catalogo():
    c = pd.read_csv(AQUI / "catalogo_huaicos_chosica.csv", dtype=str, keep_default_na=False)
    alias = pd.read_csv(RAIZ / "terreno" / "alias_catalogo.csv", dtype=str).fillna("")
    c["quebrada_id"] = c.quebrada.map(dict(zip(alias.nombre_catalogo, alias.quebrada_id))).fillna("")
    fuera = set(alias.loc[alias.motivo.str.contains("en_piloto = False"), "nombre_catalogo"])
    for col in ("en_piloto", "usable_horario"):
        c[col] = c[col].eq("True")
    return c, fuera


def _dt(fecha, hora):
    return pd.to_datetime(fecha + " " + hora, format="%Y-%m-%d %H:%M", errors="coerce")


def etiquetas(c, fuera, quebradas, H, rangos=None):
    """rangos: {id: (inicio, fin)} para los eventos que usan la regla de RANGO (v2). None = regla v1 para todos."""
    rangos = rangos or {}
    horas = pd.date_range(DESDE, HASTA, freq="h")
    y = pd.DataFrame(0.0, index=horas, columns=quebradas)
    pos = pd.DataFrame(False, index=horas, columns=quebradas)

    def marcar(df, a, b, cols, valor):
        a, b = max(a, horas[0]), min(b, horas[-1])
        if a <= b:
            df.loc[a:b, cols] = valor

    for _, ev in c[c.en_piloto].iterrows():
        if ev.quebrada in fuera:
            continue
        dia, qid = pd.Timestamp(ev.fecha), ev.quebrada_id
        cols = [qid] if qid else quebradas
        if ev.usable_horario and qid:
            ini, fin = _dt(ev.fecha, ev.hora_inicio), _dt(ev.fecha, ev.hora_fin)
            if ev.id in rangos:
                ini, fin = (_dt(ev.fecha, h) for h in rangos[ev.id])
            fin = fin if fin >= ini else fin + pd.Timedelta(days=1)
            if ev.id in rangos:
                Hd = pd.Timedelta(hours=H)
                # toca parcialmente: t < fin y t + H >= ini, sin contener -> NaN; contiene todo: t < ini y t + H >= fin -> 1
                marcar(y, (ini - Hd).floor("h"), (fin - pd.Timedelta(minutes=1)).floor("h"), cols, np.nan)
                primera, ultima = (fin - Hd).ceil("h"), (ini - pd.Timedelta(minutes=1)).floor("h")
                if primera <= ultima:
                    marcar(pos, primera, ultima, cols, True)
            else:
                marcar(pos, (ini - pd.Timedelta(hours=H)).ceil("h"), (ini - pd.Timedelta(minutes=1)).floor("h"), cols, True)
            marcar(y, ini.ceil("h"), fin + pd.Timedelta(hours=HORAS_POST), cols, np.nan)
        else:
            marcar(y, dia - pd.Timedelta(hours=H), dia + pd.Timedelta(hours=24 + HORAS_POST), cols, np.nan)
    y[pos] = 1.0
    largo = y.stack(future_stack=True).rename("y").reset_index()
    largo.columns = ["hora", "quebrada_id", "y"]
    largo.insert(2, "H", H)
    return largo


def bloques(e):
    p = e[e.y == 1].sort_values(["quebrada_id", "hora"])
    return int((p.groupby("quebrada_id").hora.diff() != pd.Timedelta(hours=1)).sum())


def main():
    c, fuera = catalogo()
    quebradas = sorted(pd.read_csv(RAIZ / "terreno" / "quebradas.csv").quebrada_id)
    hb = pd.read_csv(AQUI / "horas_B_v2.csv", dtype=str, keep_default_na=False)
    rangos = dict(zip(hb.id, zip(hb.hora_inicio_v2, hb.hora_fin_v2)))
    sel = c[c.id.isin(rangos)]
    assert len(sel) == 27 and (sel.conf_temporal == "B").all() and sel.usable_horario.all() and sel.quebrada_id.ne("").all()
    filas = []
    for H in HORIZONTES:
        v1 = pd.read_parquet(AQUI / f"etiquetas_horarias_H{H}.parquet")
        r1 = etiquetas(c, fuera, quebradas, H)
        assert r1.equals(v1), f"H={H}: la regla v1 de este script NO reproduce el parquet v1"
        v2 = etiquetas(c, fuera, quebradas, H, rangos)
        v2.to_parquet(AQUI / f"etiquetas_horarias_v2_H{H}.parquet", index=False)
        m = v1.merge(v2, on=["hora", "quebrada_id", "H"], suffixes=("_v1", "_v2"))
        filas.append(dict(H=H, y1_v1=int((v1.y == 1).sum()), y1_v2=int((v2.y == 1).sum()), bloques_v1=bloques(v1), bloques_v2=bloques(v2),
                          nan_v1=int(v1.y.isna().sum()), nan_v2=int(v2.y.isna().sum()),
                          filas_que_cambian=int((~((m.y_v1 == m.y_v2) | (m.y_v1.isna() & m.y_v2.isna()))).sum())))
    r = pd.DataFrame(filas)
    print("v1 reproducida bit a bit en los 4 H.\n" + r.to_string(index=False))
    r.to_csv(AQUI / "etiquetas_v2_resumen.csv", index=False)


if __name__ == "__main__":
    main()
