"""Paso 7.2: calibrar las probabilidades, fijar los niveles de alerta y medir la anticipación.

Entrada: modelo/oof_restringido_todas.parquet (modelo restringido AMBAS; cada temporada predicha por un modelo que no la vio).
  1. Calibración (Platt por H, una recta global sobre los puntajes fuera de muestra; la anidada por temporada es inestable, ver calibrar()).
     Después se fuerza p(H=3) <= p(H=6) <= p(H=12) <= p(H=24) en cada (quebrada, hora): un huaico en 3 h también ocurre en 24 h.
  2. Niveles por presupuesto de alertas, con cortes calculados sobre todas las horas (solo puntajes, sin etiquetas):
     Amarillo = 5 % más alto (1 alerta cada 20 h por quebrada), Naranja = 2 % (1/50 h), Rojo = 1 % (1/100 h).
  3. Por nivel y H, sobre las 12 temporadas: bloques detectados, horas de alerta y episodios falsos por temporada,
     precisión observada y ANTICIPACIÓN (horas entre la primera alerta del bloque y el huaico; el huaico cae en la última hora del bloque,
     se toma su punto medio: t_último + 0.5 h).
Salidas en modelo/salida/: umbrales_niveles.csv, umbrales_calibracion.csv, umbrales_anticipacion.csv, umbrales_compromiso.png.
y=0 significa "sin noticia", no "seguro sin huaico": las falsas alarmas y la precisión son cotas pesimistas.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from comun import SALIDA
from metricas import episodios_falsos
from oof import RUTA_OOF_TODAS
from tabla3 import bloques

NIVELES = {"amarillo": 20, "naranja": 50, "rojo": 100}   # 1 alerta cada N horas por quebrada
HORIZONTES = (3, 6, 12, 24)
EPS = 1e-6


def logit(p):
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def calibrar(d):
    """Platt por H con UNA sola recta global sobre todos los puntajes fuera de muestra (2 parámetros por H).

    La versión anidada por temporada (ajustar con las otras 11) se probó y NO sirve: al dejar fuera 2014-15 (133 de 297 horas
    positivas de H=6) la pendiente sale 2.2 en vez de ~0.3, y mezclar rectas distintas rompe el orden de los puntajes entre temporadas.
    Una recta monótona no cambia el orden dentro de un H; solo reescribe el puntaje como probabilidad.
    """
    z, y, H = logit(d.p.to_numpy()), d.y.to_numpy(), d.H.to_numpy()
    pc = np.full(len(d), np.nan)
    for h in HORIZONTES:
        m = H == h
        lr = LogisticRegression(C=1e6, max_iter=500).fit(z[m].reshape(-1, 1), y[m])
        print(f"  H={h}: pendiente {lr.coef_[0, 0]:.3f}, intercepto {lr.intercept_[0]:.2f}")
        pc[m] = lr.predict_proba(z[m].reshape(-1, 1))[:, 1]
    return pc


def monotona_en_H(d, col):
    """Impone p(H=3) <= p(H=6) <= p(H=12) <= p(H=24) por (quebrada, hora) con un máximo acumulado."""
    anchas = d.pivot(index=["quebrada_id", "hora"], columns="H", values=col)[list(HORIZONTES)]
    acum = pd.DataFrame(np.fmax.accumulate(anchas.to_numpy(), axis=1), index=anchas.index, columns=anchas.columns)
    largo = acum.stack().rename(col + "_m").reset_index()
    return d.merge(largo, on=["quebrada_id", "hora", "H"], how="left")[col + "_m"].to_numpy()


def tabla_calibracion(d):
    filas = []
    for h in HORIZONTES:
        g = d[d.H == h]
        cortes = np.unique(np.quantile(g.pc, [0, .5, .8, .9, .95, .98, .99, 1]))
        g = g.assign(bin=pd.cut(g.pc, cortes, include_lowest=True))
        for b, x in g.groupby("bin", observed=True):
            filas.append(dict(H=h, bin=str(b), horas=len(x), p_media=x.pc.mean(), frecuencia_observada=x.y.mean(), positivos=int(x.y.sum())))
    return pd.DataFrame(filas)


def anticipacion(b, tau):
    """Por bloque: ¿hubo alerta (pc >= tau) y cuántas horas antes del huaico fue la primera?"""
    out = []
    for _, x in b.groupby("bloque"):
        x = x.sort_values("hora")
        al = x[x.pc >= tau]
        t_ult = x.hora.iloc[-1]
        out.append(dict(bloque=x.bloque.iloc[0], temporada=x.temporada.iloc[0], detectado=len(al) > 0,
                        anticipacion_h=((t_ult - al.hora.iloc[0]) / pd.Timedelta(hours=1) + 0.5) if len(al) else np.nan))
    return pd.DataFrame(out)


def main():
    d = pd.read_parquet(RUTA_OOF_TODAS)
    d["pc"] = calibrar(d)
    d["pc"] = monotona_en_H(d, "pc")
    n_temp = d.temporada.nunique()
    print(f"Filas: {len(d):,} | temporadas: {n_temp}")

    cal = tabla_calibracion(d)
    cal.to_csv(SALIDA / "umbrales_calibracion.csv", index=False)
    print("\nCALIBRACIÓN (p_media vs frecuencia observada, por tramo de puntaje)\n" +
          cal.assign(p_media=cal.p_media.round(4), frecuencia_observada=cal.frecuencia_observada.round(4)).to_string(index=False))

    b = bloques(d)
    filas, ant = [], []
    for h in HORIZONTES:
        g, bh = d[d.H == h], b[b.H == h]
        for nivel, N in NIVELES.items():
            tau = float(np.quantile(g.pc, 1 - 1 / N))
            a = g.pc >= tau
            eps = []
            for s, e in g.groupby("temporada"):
                ef, hf = episodios_falsos(e, e.pc >= tau)
                eps.append((ef, hf, int((e.pc >= tau).sum())))
            ant_h = anticipacion(bh, tau).assign(H=h, nivel=nivel)
            ant.append(ant_h)
            det = ant_h.detectado
            lead = ant_h.anticipacion_h.dropna()
            filas.append(dict(
                H=h, nivel=nivel, alerta_cada_N_horas=N, umbral_p=round(tau, 4), bloques=len(ant_h), detectados=int(det.sum()),
                pct_detectados=round(100 * det.mean(), 1), pct_con_1h_o_mas=round(100 * (ant_h.anticipacion_h >= 1).mean(), 1),
                anticipacion_mediana_h=round(float(lead.median()), 1) if len(lead) else np.nan,
                anticipacion_max_h=round(float(lead.max()), 1) if len(lead) else np.nan,
                horas_alerta_por_temporada=round(np.mean([e[2] for e in eps])), falsos_episodios_por_temporada=round(np.mean([e[0] for e in eps]), 1),
                precision_horas=round(float(g.y[a].mean()), 4), base=round(float(g.y.mean()), 4)))
    niveles = pd.DataFrame(filas)
    niveles.to_csv(SALIDA / "umbrales_niveles.csv", index=False)
    pd.concat(ant).to_csv(SALIDA / "umbrales_anticipacion.csv", index=False)
    print("\nNIVELES (12 temporadas; bloques de las 6 con eventos)\n" + niveles.to_string(index=False))

    graficar(d, b, niveles)
    print(f"\nGuardado en {SALIDA}: umbrales_niveles.csv, umbrales_calibracion.csv, umbrales_anticipacion.csv, umbrales_compromiso.png")


def graficar(d, b, niveles):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.5, 5), facecolor="#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    colores = {3: "#2a78d6", 6: "#eb6834", 12: "#1baf7a", 24: "#e87ba4"}
    for h in HORIZONTES:
        g, bh = d[d.H == h], b[b.H == h]
        mx = bh.groupby("bloque").pc.max().to_numpy()
        Ns = np.array([5, 10, 20, 50, 100, 200, 500])
        taus = [np.quantile(g.pc, 1 - 1 / n) for n in Ns]
        ax.plot(Ns, [100 * (mx >= t).mean() for t in taus], color=colores[h], lw=2, label=f"H={h} h")
        for nivel, N in NIVELES.items():
            tau = np.quantile(g.pc, 1 - 1 / N)
            ax.plot([N], [100 * (mx >= tau).mean()], "o", color=colores[h], ms=7, mec="white")
    ax.set_xscale("log")
    ax.invert_xaxis()
    ax.set_xticks([500, 200, 100, 50, 20, 10, 5])
    ax.set_xticklabels(["1/500", "1/200", "1/100\nrojo", "1/50\nnaranja", "1/20\namarillo", "1/10", "1/5"])
    ax.set_xlabel("Presupuesto de alertas (1 alerta cada N horas por quebrada)", color="#52514e")
    ax.set_ylabel("% de huaicos (bloques) detectados", color="#52514e")
    ax.set_title("Más alertas, más huaicos detectados (12 temporadas, validación por temporada)", loc="left", color="#0b0b0b", fontsize=11)
    ax.grid(axis="y", color="#e4e3df", lw=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(SALIDA / "umbrales_compromiso.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
