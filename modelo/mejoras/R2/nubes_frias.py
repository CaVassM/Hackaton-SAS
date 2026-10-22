"""R2: prueba go/no-go de nubes frías (GPM_MERGIR) para las tormentas "ciegas" de IMERG. NO entra al modelo. Nada se ajusta: no hay entrenamiento.

Instante de referencia t0 = primera hora del huaico (tormentas) o instante al azar (controles). Ventanas: imágenes con t0-6h < tiempo <= t0 (y 3 h).
Zonas: QUEBRADAS = rectángulo de los 17 polígonos + 0.02° (lat -12.013 a -11.871, lon -76.846 a -76.625); ALTA/ESTE = lon > -76.625 (cuenca alta
de Santa Eulalia y del Rímac, todo el recuadro en latitud).
Variables por imagen: Tb mínima (K), fracción de píxeles < 235 K y < 220 K. En la ventana: mínimo de Tb_min, máximo de las fracciones.
PRINCIPAL (fijada antes de mirar): Tb mínima sobre las QUEBRADAS en 6 h (más fría = más señal). Las otras 11 son exploratorias.
Tormenta ciega: mediana de sus quebradas con IMERG < 0.1 mm en las 6 h previas (8 de 14); estricta: ninguna quebrada >= 0.1 mm (5).
Detección al 5 % de falsas alarmas: puntaje > percentil 95 de los controles.
Criterio GO: AUC >= 0.75 en ciegas o >= 1/3 de las ciegas detectadas al 5 %.
Salidas en modelo/mejoras/R2/: nubes_frias_auc.csv, nubes_frias_tormentas.csv, nubes_frias.png
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parents[1]))
from comun import cargar_lluvia_horaria  # noqa: E402

DATOS = AQUI / "datos"
UTC = pd.Timedelta(hours=5)
QLAT, QLON = (-12.013, -11.871), (-76.846, -76.625)
PRINCIPAL = "tbmin_quebradas_6h"
RNG = np.random.default_rng(0)


def tiempos(tab, horas):
    """Tiempos UTC de las 2*(horas+1) imágenes de cada fila (como en descargar_mergir.py)."""
    base = (tab.t0_local + UTC).dt.floor("h")
    k = np.arange(2 * (horas + 1))
    return base.to_numpy()[:, None] - np.timedelta64(horas, "h") + (k // 2) * np.timedelta64(1, "h") + (k % 2) * np.timedelta64(30, "m")


def variables(ruta, tab):
    z = np.load(ruta)
    tb = z["tb"].astype("float32")
    tb[tb < 0] = np.nan
    lat, lon = z["lat"], z["lon"]
    T = tiempos(tab, int(z["horas"]))
    t0 = (tab.t0_local + UTC).to_numpy()[:, None]
    mq = ((lat[:, None] >= QLAT[0]) & (lat[:, None] <= QLAT[1])) & ((lon[None, :] >= QLON[0]) & (lon[None, :] <= QLON[1]))
    ma = np.broadcast_to(lon[None, :] > QLON[1], mq.shape)
    out = {}
    for zona, m in (("quebradas", mq), ("alta", ma)):
        x = tb[:, :, m]                                     # (n, imágenes, píxeles)
        por_img = {"tbmin": np.nanmin(x, axis=2), "f235": np.nanmean(x < 235, axis=2), "f220": np.nanmean(x < 220, axis=2)}
        for h in (3, 6):
            v = (T > t0 - np.timedelta64(h, "h")) & (T <= t0)
            for nom, a in por_img.items():
                a = np.where(v, a, np.nan)
                out[f"{nom}_{zona}_{h}h"] = np.nanmin(a, axis=1) if nom == "tbmin" else np.nanmax(a, axis=1)
    return pd.DataFrame(out, index=tab.index)


def puntaje(col, x):
    return -x if col.startswith("tbmin") else x       # más alto = más señal


def main():
    pd.set_option("display.width", 220)
    ev = pd.read_csv(DATOS / "instantes_tormentas.csv", parse_dates=["fecha", "t0_local"])
    ct = pd.read_csv(DATOS / "instantes_controles.csv", parse_dates=["t0_local"])
    fe, fc = variables(DATOS / "mergir_tormentas.npz", ev), variables(DATOS / "mergir_controles.npz", ct)
    # IMERG en las 6 h previas (media de las 17 quebradas, sin retraso): para describir y para el subgrupo de controles con lluvia
    R = cargar_lluvia_horaria().pivot(index="hora", columns="quebrada_id", values="mm").mean(axis=1)
    im = lambda t: float(R.loc[t - pd.Timedelta(hours=6): t - pd.Timedelta(hours=1)].sum()) if t - pd.Timedelta(hours=6) in R.index else np.nan
    ct["imerg_6h"] = ct.t0_local.dt.floor("h").map(im)
    grupos = {"todas (14)": ev.index, "ciegas (8)": ev.index[ev.ciega], "ciegas estrictas (5)": ev.index[ev.ciega_estricta]}
    controles = {"todos": ct.index, "con lluvia IMERG >= 0.1 mm en 6 h": ct.index[ct.imerg_6h >= 0.1]}
    filas = []
    for col in fe.columns:
        for cn, ci in controles.items():
            sc = puntaje(col, fc.loc[ci, col].dropna().to_numpy())
            tau = np.quantile(sc, 0.95)
            for gn, gi in grupos.items():
                se = puntaje(col, fe.loc[gi, col].to_numpy())
                y = np.r_[np.ones(len(se)), np.zeros(len(sc))]
                s = np.r_[se, sc]
                auc = roc_auc_score(y, s)
                bs = [roc_auc_score(np.r_[np.ones(len(se)), np.zeros(len(sc))], np.r_[RNG.choice(se, len(se)), RNG.choice(sc, len(sc))]) for _ in range(500)]
                filas.append(dict(variable=col, principal=col == PRINCIPAL, controles=cn, n_controles=len(sc), grupo=gn, AUC=round(auc, 3),
                                  AUC_ic90=f"{np.quantile(bs, .05):.2f}-{np.quantile(bs, .95):.2f}", detectadas_5pct=int((se > tau).sum()), de=len(se)))
    r = pd.DataFrame(filas)
    r.to_csv(AQUI / "nubes_frias_auc.csv", index=False)
    tor = pd.concat([ev[["id", "fecha", "t0_local", "bloques", "imerg_6h_mediana", "ciega", "ciega_estricta"]], fe.round(3)], axis=1)
    tor.to_csv(AQUI / "nubes_frias_tormentas.csv", index=False)

    print(f"Controles: {len(ct)} ({int((ct.imerg_6h >= 0.1).sum())} con IMERG >= 0.1 mm en 6 h) | tormentas 14, ciegas {int(ev.ciega.sum())}, estrictas {int(ev.ciega_estricta.sum())}")
    p = r[r.controles == "todos"].pivot(index="variable", columns="grupo", values=["AUC", "detectadas_5pct"])
    print("\nAUC y detectadas al 5 % (controles: todos)\n" + p.to_string())
    print("\nPRINCIPAL\n" + r[r.principal][["controles", "grupo", "AUC", "AUC_ic90", "detectadas_5pct", "de"]].to_string(index=False))
    print("\nPor tormenta (principal y fracción < 235 K en la zona alta, 6 h):")
    print(tor[["fecha", "t0_local", "ciega", "imerg_6h_mediana", PRINCIPAL, "f235_quebradas_6h", "f235_alta_6h", "tbmin_alta_6h"]].to_string(index=False))
    print("Percentiles 5/50/95 de los controles:", {c: np.nanpercentile(fc[c], [5, 50, 95]).round(2).tolist() for c in (PRINCIPAL, "f235_alta_6h", "tbmin_alta_6h")})
    figura(fe, fc, ev)


def figura(fe, fc, ev):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ejes = plt.subplots(1, 2, figsize=(11, 4.4), facecolor="#fcfcfb")
    for ax, (col, et) in zip(ejes, ((PRINCIPAL, "Tb mínima sobre las quebradas, 6 h previas (K)"), ("tbmin_alta_6h", "Tb mínima en la zona alta/este, 6 h previas (K)"))):
        ax.set_facecolor("#fcfcfb")
        v = fc[col].dropna()
        ax.hist(v, bins=np.arange(180, 311, 5), color="#b7d3f6", edgecolor="#fcfcfb", label=f"controles (n={len(v)})")
        q5 = np.nanpercentile(v, 5)
        ax.axvline(q5, color="#52514e", ls="--", lw=1.2, label="5 % de falsas alarmas")
        top = ax.get_ylim()[1]
        for i, r in ev.iterrows():
            c = "#eb6834" if r.ciega else "#2a78d6"
            ax.plot(fe.loc[i, col], top * (0.15 + 0.06 * (i % 12)), "o", ms=8, color=c, mec="#fcfcfb", mew=1.5)
        ax.plot([], [], "o", color="#eb6834", ms=8, label="tormenta ciega para IMERG")
        ax.plot([], [], "o", color="#2a78d6", ms=8, label="tormenta que IMERG sí vio")
        ax.set_xlabel(et, color="#52514e")
        ax.set_title("Más a la izquierda = nube más fría (más convectiva)", loc="left", fontsize=10, color="#0b0b0b")
        ax.grid(axis="x", color="#e4e3df", lw=0.8)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.set_yticks([])
    ejes[0].legend(frameon=False, fontsize=8.5, loc="upper left")
    fig.suptitle("GPM_MERGIR: nubes frías antes de los 14 huaicos vs 500 instantes sin huaico (misma hora del día)", x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(AQUI / "nubes_frias.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
