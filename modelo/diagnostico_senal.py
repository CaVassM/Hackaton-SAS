"""Paso 1: diagnóstico de la señal de lluvia (control de calidad; NO se usa para elegir variables).

Compara lluvia_24h y lluvia_14d de IMERG Early entre días CON huaico y días SIN huaico, a nivel (quebrada, día), usando la fila de las 12:00 locales
(lo que el modelo sabría a mediodía: lluvia hasta las 07:00, sin información posterior al evento).
  - Con huaico: (fecha, quebrada) del catálogo con quebrada del piloto y sin marca `dudoso` (la hora puede no ser usable).
  - Sin huaico: (quebrada, día) en que las 24 etiquetas de H=24 valen 0 (excluye el día anterior al evento, el posterior y los días con eventos
    sin hora o sin quebrada, que van en NaN).
Salidas en modelo/salida/: diagnostico_senal.png, diagnostico_senal_resumen.csv, diagnostico_dias_con_huaico.csv
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from comun import SALIDA, cargar_etiquetas, cargar_features, cargar_lluvia_horaria, eventos_catalogo

AZUL, NARANJA, TEXTO, TEXTO2, GRILLA, FONDO = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def main():
    f = cargar_features()
    f12 = f[f.hora.dt.hour == 12].assign(fecha=lambda d: d.hora.dt.normalize())
    ev = eventos_catalogo()
    ev = ev[(ev.fecha.dt.month >= 12) | (ev.fecha.dt.month <= 4)]

    e = cargar_etiquetas(24).assign(fecha=lambda d: d.hora.dt.normalize())
    g = e.groupby(["quebrada_id", "fecha"]).y.agg(n="size", ceros=lambda s: (s == 0).sum()).reset_index()
    ctrl = g[(g.n == 24) & (g.ceros == 24)][["quebrada_id", "fecha"]]

    con = f12.merge(ev, on=["fecha", "quebrada_id"])
    sin = f12.merge(ctrl, on=["fecha", "quebrada_id"])
    con = con[con.lluvia_24h.notna()]
    sin = sin[sin.lluvia_24h.notna()]

    filas = []
    for var in ("lluvia_24h", "lluvia_14d"):
        for nombre, d in (("con huaico", con), ("sin huaico", sin)):
            v = d[var].dropna()
            filas.append(dict(variable=var, grupo=nombre, n_quebrada_dia=len(v), fechas_distintas=d.loc[v.index, "fecha"].nunique(),
                              mediana_mm=round(v.median(), 2), p25_mm=round(v.quantile(.25), 2), p75_mm=round(v.quantile(.75), 2),
                              pct_cero=round(100 * (v == 0).mean(), 1)))
    res = pd.DataFrame(filas)
    res.to_csv(SALIDA / "diagnostico_senal_resumen.csv", index=False)
    print(res.to_string(index=False))

    # boxplot (escala symlog: hay muchos ceros)
    fig, ejes = plt.subplots(1, 2, figsize=(10, 4.8), facecolor=FONDO)
    for ax, var, titulo in zip(ejes, ("lluvia_24h", "lluvia_14d"), ("Lluvia de las últimas 24 h disponibles", "Lluvia de los últimos 14 días")):
        datos = [con[var].dropna().to_numpy(), sin[var].dropna().to_numpy()]
        bp = ax.boxplot(datos, widths=0.5, patch_artist=True, medianprops=dict(color=TEXTO, lw=2),
                        flierprops=dict(marker="o", markersize=3, alpha=.35, markeredgecolor=TEXTO2), whiskerprops=dict(color=TEXTO2), capprops=dict(color=TEXTO2))
        for patch, c in zip(bp["boxes"], (NARANJA, AZUL)):
            patch.set(facecolor=c, alpha=.75, edgecolor=TEXTO2)
        ax.set_yscale("symlog", linthresh=1)
        ax.set_xticks([1, 2], [f"con huaico\n(n={len(datos[0])})", f"sin huaico\n(n={len(datos[1])})"], color=TEXTO)
        for i, d in enumerate(datos, 1):
            ax.annotate(f"mediana {np.median(d):.1f} mm", (i, np.median(d)), xytext=(28, 6), textcoords="offset points", fontsize=9, color=TEXTO)
        ax.set_title(titulo, loc="left", color=TEXTO, fontsize=11)
        ax.set_ylabel("mm (escala log)", color=TEXTO2)
        ax.set_facecolor(FONDO)
        ax.grid(axis="y", color=GRILLA, lw=.8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.tick_params(colors=TEXTO2)
    fig.suptitle("IMERG Early a las 12:00 locales, dic–abr 2014-2026 (QC de la señal)", x=0.01, ha="left", color=TEXTO, fontsize=12)
    fig.tight_layout()
    fig.savefig(SALIDA / "diagnostico_senal.png", dpi=150)

    # días con huaico y lluvia_24h = 0: ¿es la latencia o IMERG no vio lluvia?
    R = cargar_lluvia_horaria().set_index(["quebrada_id", "hora"]).mm
    def mm_previas(r):
        if pd.isna(r.hora_evento):
            return np.nan
        t = r.fecha + pd.Timedelta(hours=int(r.hora_evento))
        ser = R.loc[r.quebrada_id]
        return round(float(ser.loc[t - pd.Timedelta(hours=24): t - pd.Timedelta(hours=1)].sum()), 2)  # 24 h antes del evento, SIN latencia
    lista = con.copy()
    lista["mm_24h_antes_sin_latencia"] = lista.apply(mm_previas, axis=1)
    lista = lista[["fecha", "quebrada_id", "hora_evento", "lluvia_24h", "lluvia_14d", "mm_24h_antes_sin_latencia"]].sort_values(["fecha", "quebrada_id"])
    lista.to_csv(SALIDA / "diagnostico_dias_con_huaico.csv", index=False)
    cero = lista[lista.lluvia_24h == 0]
    print(f"\nFechas con huaico: {lista.fecha.nunique()} | (quebrada, día) con huaico: {len(lista)} | con lluvia_24h == 0: {len(cero)} "
          f"({cero.fecha.nunique()} fechas)")
    print(cero.groupby("fecha").agg(quebradas=("quebrada_id", lambda s: ", ".join(s)), hora=("hora_evento", "min"), lluvia_14d=("lluvia_14d", "median"),
                                    mm_24h_antes_sin_latencia=("mm_24h_antes_sin_latencia", "median")).round(2).to_string())
    casi = lista[lista.lluvia_24h < 1]
    print(f"\nCasi sin lluvia (lluvia_24h < 1 mm): {len(casi)} (quebrada, día) en {casi.fecha.nunique()} fechas")
    print(casi.groupby("fecha").agg(quebradas=("quebrada_id", lambda s: ", ".join(s)), hora=("hora_evento", "min"), lluvia_24h=("lluvia_24h", "median"),
                                    lluvia_14d=("lluvia_14d", "median"), mm_24h_antes_sin_latencia=("mm_24h_antes_sin_latencia", "median")).round(2).to_string())
    print("\nTodas las fechas con huaico (mediana entre sus quebradas):")
    print(lista.groupby("fecha").agg(n_q=("quebrada_id", "size"), hora=("hora_evento", "min"), lluvia_24h=("lluvia_24h", "median"),
                                     lluvia_14d=("lluvia_14d", "median")).round(1).to_string())


if __name__ == "__main__":
    main()
