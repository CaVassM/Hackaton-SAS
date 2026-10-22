"""Auditoría independiente de lo construido hasta la tabla 3. Cada chequeo recalcula con otro método y compara.
Uso: python modelo/auditoria.py
"""
import glob

import numpy as np
import pandas as pd

from comun import RAIZ, cargar_etiquetas, cargar_features, cargar_lluvia_horaria, eventos_catalogo

OK, MAL = "OK  ", "FALLA"
resultados = []


def reportar(nombre, ok, detalle=""):
    resultados.append(ok)
    print(f"[{OK if ok else MAL}] {nombre}" + (f" — {detalle}" if detalle else ""))


# ---------------------------------------------------------------- 1. pesos: las áreas por celda suman el área de la quebrada
def chequeo_pesos():
    p = pd.read_csv(RAIZ / "lluvia" / "pesos_imerg.csv")
    q = pd.read_csv(RAIZ / "terreno" / "quebradas.csv").set_index("quebrada_id")
    suma = p.groupby("quebrada_id").area_km2_en_celda.sum()
    dif = ((suma - q.area_km2.reindex(suma.index)).abs() / q.area_km2.reindex(suma.index)).max()
    reportar("Pesos: Σ área por celda = área de la quebrada (quebradas.csv)", dif < 0.02 and len(suma) == 17, f"diferencia máxima {100 * dif:.2f} %, {len(suma)} quebradas")
    reportar("Pesos: cada quebrada suma 1", bool(np.allclose(p.groupby('quebrada_id').peso.sum(), 1)))


# ---------------------------------------------------------------- 2. conversión de unidades y huso: suma y ciclo diurno
def chequeo_lluvia():
    import xarray as xr
    R = cargar_lluvia_horaria().pivot(index="hora", columns="quebrada_id", values="mm")
    p = pd.read_csv(RAIZ / "lluvia" / "pesos_imerg.csv").query("quebrada_id == 'quirio'")
    tot = 0.0
    for f in sorted(glob.glob(str(RAIZ / "lluvia" / "datos" / "early" / "imerg_early_2016-0[1-4].nc"))):
        with xr.open_dataset(f) as ds:
            da = ds["mm_h"].load()
        for r in p.itertuples():
            tot += r.peso * 0.5 * float(da.sel(lat=r.lat_centro, lon=r.lon_centro, method="nearest").sum())
    # horas locales: ene–abr 2016 completo en hora de Perú vs. el mismo periodo en UTC (diferencia solo en los bordes de 5 h)
    rq = R["quirio"]["2016-01-01 05:00":"2016-04-30 18:00"].sum()
    reportar("Lluvia: Σ horaria (mm) de Quirio ene–abr 2016 = 0.5 × Σ tasas IMERG ponderadas", abs(rq - tot) / tot < 0.02, f"{rq:.0f} mm vs {tot:.0f} mm (bordes de 5 h aparte)")
    h = R[(R.index.month.isin([12, 1, 2, 3, 4]))].mean(axis=1).groupby(R[(R.index.month.isin([12, 1, 2, 3, 4]))].index.hour).mean()
    pico = int(h.idxmax()); tarde = float(h.loc[12:20].sum() / h.sum())
    reportar("Huso horario: el máximo diario de lluvia cae por la tarde en hora local (típico de la sierra)", 11 <= pico <= 20,
             f"hora pico {pico}:00, {100 * tarde:.0f} % de la lluvia entre 12 y 20 h; mínimo a las {int(h.idxmin())}:00")


# ---------------------------------------------------------------- 3. features contra una implementación independiente (sumas directas)
def chequeo_features(n=300, semilla=3):
    R = cargar_lluvia_horaria().pivot(index="hora", columns="quebrada_id", values="mm").asfreq("h")
    F = cargar_features().set_index(["quebrada_id", "hora"])
    rng = np.random.default_rng(semilla)
    cand = F[F.lluvia_14d.notna() & F.lluvia_efectiva.notna() & F.horas_desde_lluvia.notna()].sample(n, random_state=semilla).index
    kh = 0.84 ** (1 / 24)
    peor = {}
    for q, t in cand:
        s = R[q]
        d = lambda a, b: s.loc[t - pd.Timedelta(hours=a): t - pd.Timedelta(hours=b)].to_numpy()  # horas con etiqueta t-a ... t-b
        v3, v3p = d(7, 5), d(10, 8)
        esperado = {
            "lluvia_3h": v3.sum(), "lluvia_6h": d(10, 5).sum(), "lluvia_24h": d(28, 5).sum(), "int_max_24h": d(28, 5).max(),
            "tendencia_3h": v3.sum() - v3p.sum(), "horas_lluvia_24h": float((d(28, 5) >= 0.1).sum()),
            "lluvia_7d": d(172, 5).sum(), "lluvia_14d": d(340, 5).sum(),
        }
        # lluvia_efectiva: Σ k^edad × R, desde el inicio del tramo continuo de datos
        tramo = s.loc[:t - pd.Timedelta(hours=5)]
        ini = tramo.index[np.where(tramo.isna().to_numpy())[0].max() + 1] if tramo.isna().any() else tramo.index[0]
        v = tramo.loc[ini:].to_numpy()[::-1]
        esperado["lluvia_efectiva"] = float((v * kh ** np.arange(len(v))).sum())
        hs = np.where(v >= 0.1)[0]
        esperado["horas_desde_lluvia"] = float(min(hs[0], 336)) if len(hs) else 336.0
        y = t.year if t.month >= 6 else t.year - 1
        esperado["lluvia_temporada"] = float(s.loc[pd.Timestamp(f"{y}-12-01"): t - pd.Timedelta(hours=5)].sum())
        for k, e in esperado.items():
            dif = abs(float(F.loc[(q, t), k]) - e) / max(1.0, abs(e))
            peor[k] = max(peor.get(k, 0), dif)
    ok = all(v < 1e-3 for v in peor.values())
    reportar(f"Features: {n} filas al azar recalculadas con sumas directas coinciden", ok,
             "error relativo máx por feature: " + ", ".join(f"{k} {v:.1e}" for k, v in peor.items()))


# ---------------------------------------------------------------- 3b. variables nuevas contra una implementación independiente
def chequeo_features_nuevas(n=300, semilla=11):
    import features_lluvia as fl

    R = cargar_lluvia_horaria().pivot(index="hora", columns="quebrada_id", values="mm").asfreq("h")
    Rcel = fl.lluvia_celdas(RAIZ / "lluvia" / "datos" / "early", pd.read_csv(RAIZ / "lluvia" / "pesos_imerg.csv"))
    F = cargar_features().set_index(["quebrada_id", "hora"])
    cand = F[F[fl.FEATURES_NUEVAS].notna().all(axis=1)].sample(n, random_state=semilla).index
    peor = {}

    def pico3(v, ventanas):  # v: lluvia horaria de las horas t-(ventanas+6) ... t-5 ; máximo de las sumas de 3 horas consecutivas
        return max(v[i:i + 3].sum() for i in range(ventanas))

    for q, t in cand:
        s, h = R[q], pd.Timedelta(hours=1)
        d = lambda a, b, ser=s: ser.loc[t - a * h: t - b * h].to_numpy()
        tramo = s.loc[:t - 5 * h]
        ini = tramo.index[np.where(tramo.isna().to_numpy())[0].max() + 1] if tramo.isna().any() else tramo.index[0]
        v = tramo.loc[ini:].to_numpy()[::-1]  # de la hora más reciente hacia atrás
        s24, s7d = d(28, 5).sum(), d(172, 5).sum()
        hs = np.where(v >= 2.0)[0]
        esp = {
            "max_3h_24h": pico3(d(30, 5), 24), "max_3h_72h": pico3(d(78, 5), 72),
            "horas_desde_lluvia_fuerte": float(min(hs[0], 336)) if len(hs) else 336.0,
            "lluvia_48h": d(52, 5).sum(), "lluvia_72h": d(76, 5).sum(),
            "api_k70": float((v * (0.70 ** (1 / 24)) ** np.arange(len(v))).sum()), "api_k92": float((v * (0.92 ** (1 / 24)) ** np.arange(len(v))).sum()),
            "dias_lluviosos_7d": float(sum(d(28 + 24 * k, 5 + 24 * k).sum() >= 1.0 - fl.TOL_UMBRAL for k in range(7))),
            "tendencia_24h": s24 - d(52, 29).sum(), "frac_24h_en_7d": s24 / (s7d + 1.0),
            "lluvia_24h_sobre_api": s24 / (float((v * (0.84 ** (1 / 24)) ** np.arange(len(v))).sum()) + 1.0),
            "reg_max_24h": max(d(28, 5, Rcel[c]).sum() for c in Rcel.columns),
            "reg_max_3h_24h": max(pico3(d(30, 5, Rcel[c]), 24) for c in Rcel.columns),
        }
        for k, e in esp.items():
            dif = abs(float(F.loc[(q, t), k]) - e) / max(1.0, abs(e))
            peor[k] = max(peor.get(k, 0), dif)
    reportar(f"Variables nuevas: {n} filas al azar recalculadas con sumas directas coinciden", all(v < 1e-3 for v in peor.values()),
             "error relativo máx: " + ", ".join(f"{k} {v:.0e}" for k, v in peor.items()))


def chequeo_tabla3_nuevas(n=3000, semilla=13):
    from tabla3 import FEATURES_E, FEATURES_F
    t = pd.read_parquet(RAIZ / "modelo" / "tabla3_modelo.parquet")
    s = t.sample(n, random_state=semilla)
    ang = 2 * np.pi * s.hora.dt.hour / 24
    ok_e = np.allclose(s.hora_sen, np.sin(ang), atol=1e-5) and np.allclose(s.hora_cos, np.cos(ang), atol=1e-5)
    ok_f = np.allclose(s.lluvia_24h_x_log10area, s.lluvia_24h * s.log10_area_km2, equal_nan=True, rtol=1e-4) and \
        np.allclose(s.int3h_x_pendiente, s.max_3h_24h * s.pendiente_media, equal_nan=True, rtol=1e-4)
    reportar("Tabla 3: ciclo diario e interacciones coinciden con su definición", ok_e and ok_f, f"ciclo diario {ok_e}, interacciones {ok_f}")


# ---------------------------------------------------------------- 4. convención de la `hora` de las etiquetas contra el catálogo
def chequeo_etiquetas():
    c = pd.read_csv(RAIZ / "catalogo_huaicos_chosica" / "catalogo_huaicos_chosica.csv")
    a = pd.read_csv(RAIZ / "terreno" / "alias_catalogo.csv")[["nombre_catalogo", "quebrada_id"]]
    m = c.merge(a, left_on="quebrada", right_on="nombre_catalogo", how="left")
    m = m[m.quebrada_id.notna() & m.dudoso.isna() & m.usable_horario.eq(True) & m.hora_inicio.notna()].copy()
    m["t_ev"] = pd.to_datetime(m.fecha + " " + m.hora_inicio)
    m = m.drop_duplicates(["quebrada_id", "t_ev"])
    for H in (3, 6, 24):
        e = cargar_etiquetas(H)
        e1 = e[e.y == 1].groupby("quebrada_id").hora.apply(set).to_dict()
        igual = sup = mal = aislados = 0
        ejemplos = []
        for r in m.itertuples():
            otros = m[(m.quebrada_id == r.quebrada_id) & (m.t_ev != r.t_ev) & ((m.t_ev - r.t_ev).abs() < pd.Timedelta(hours=H + 24))]
            if len(otros):
                continue
            aislados += 1
            esperado = {t for t in pd.date_range(r.t_ev.floor("h") - pd.Timedelta(hours=H), r.t_ev.ceil("h"), freq="h")
                        if t < r.t_ev <= t + pd.Timedelta(hours=H)}
            real = {t for t in e1.get(r.quebrada_id, set()) if abs((t - r.t_ev) / pd.Timedelta(hours=1)) <= H + 24}
            if real == esperado:
                igual += 1
            elif esperado <= real:
                sup += 1
            else:
                mal += 1
                ejemplos.append((r.quebrada_id, str(r.t_ev), sorted(map(str, esperado))[:2], sorted(map(str, real))[:2]))
        reportar(f"Etiquetas H={H}: y=1 en las horas t con t < evento <= t+H (hora local, inicio de hora)", mal == 0 and aislados > 0,
                 f"{aislados} eventos aislados: {igual} idénticos, {sup} con horas extra, {mal} distintos" + (f" | ej: {ejemplos[:2]}" if mal else ""))


# ---------------------------------------------------------------- 5. catálogo: nombres sin alias y eventos por quebrada
def chequeo_catalogo():
    c = pd.read_csv(RAIZ / "catalogo_huaicos_chosica" / "catalogo_huaicos_chosica.csv")
    a = pd.read_csv(RAIZ / "terreno" / "alias_catalogo.csv")
    piloto = c[c.en_piloto.eq(True)]  # los distritos vecinos (en_piloto=False) no tienen alias: es lo esperado
    sin_alias = sorted(set(piloto.quebrada.dropna()) - set(a.nombre_catalogo))
    reportar("Catálogo: todos los nombres de quebrada del piloto (en_piloto=True) tienen fila en alias_catalogo.csv", not sin_alias, f"sin alias: {sin_alias}" if sin_alias else "")
    ev = eventos_catalogo()
    print(f"       eventos del piloto (fecha, quebrada) sin `dudoso`: {len(ev)} en {ev.fecha.nunique()} fechas; por quebrada: {ev.quebrada_id.value_counts().to_dict()}")


# ---------------------------------------------------------------- 6. integridad de la tabla 3
def chequeo_tabla3(n=2000, semilla=5):
    t = pd.read_parquet(RAIZ / "modelo" / "tabla3_modelo.parquet")
    f = cargar_features().set_index(["quebrada_id", "hora"])
    q = pd.read_csv(RAIZ / "terreno" / "quebradas.csv").set_index("quebrada_id")
    s = t.sample(n, random_state=semilla)
    ok_f = all(np.allclose(s[c].to_numpy(), f.loc[list(zip(s.quebrada_id, s.hora)), c].to_numpy(), equal_nan=True, rtol=1e-5) for c in ("lluvia_24h", "lluvia_14d", "lluvia_efectiva"))
    ok_t = np.allclose(s.log10_area_km2, np.log10(q.area_km2.reindex(s.quebrada_id).to_numpy()), rtol=1e-5) and np.allclose(s.pendiente_media, q.pendiente_media.reindex(s.quebrada_id).to_numpy(), rtol=1e-5)
    ok_y = True
    for H, g in s.groupby("H"):
        e = cargar_etiquetas(H).set_index(["quebrada_id", "hora"]).y
        ok_y &= bool(np.array_equal(e.loc[list(zip(g.quebrada_id, g.hora))].to_numpy(), g.y.to_numpy()))
    reportar("Tabla 3: features, terreno y etiquetas coinciden con sus fuentes en una muestra", ok_f and ok_t and ok_y, f"{n} filas: features {ok_f}, terreno {ok_t}, y {ok_y}")
    reportar("Tabla 3: sin terreno vacío, 17 quebradas, 4 horizontes, solo dic–abr", t[["log10_area_km2", "pendiente_media"]].notna().all().all() and t.quebrada_id.nunique() == 17
             and sorted(t.H.unique()) == [3, 6, 12, 24] and t.hora.dt.month.isin([12, 1, 2, 3, 4]).all())
    mono = True
    for (qd, h), g in t.groupby(["quebrada_id", "hora"]):
        pass
        break
    p = t.pivot_table(index=["quebrada_id", "hora"], columns="H", values="y", aggfunc="max")
    p = p.dropna()
    viol = int(((p[3] > p[6]) | (p[6] > p[12]) | (p[12] > p[24])).sum())
    reportar("Etiquetas: y(H=3) <= y(H=6) <= y(H=12) <= y(H=24) en cada fila (ventanas anidadas)", viol == 0, f"{len(p):,} (quebrada, hora) comparadas, {viol} violaciones")


if __name__ == "__main__":
    for f in (chequeo_pesos, chequeo_lluvia, chequeo_features, chequeo_features_nuevas, chequeo_etiquetas, chequeo_catalogo, chequeo_tabla3, chequeo_tabla3_nuevas):
        try:
            f()
        except Exception as e:
            reportar(f.__name__, False, f"EXCEPCIÓN {repr(e)[:200]}")
    print(f"\nRESULTADO: {sum(resultados)}/{len(resultados)} chequeos OK")
