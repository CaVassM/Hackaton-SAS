import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

W, H = 1340, 1030
fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor="#fcfcfb")
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis("off")
INK, SUB, LINE, BLUE = "#0b0b0b", "#52514e", "#c8c8c0", "#2a78d6"

def caja(x, y, w, h, t, s, azul=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=14", fc="#e6f0fa" if azul else "#fcfcfb", ec=BLUE if azul else LINE, lw=3 if azul else 2))
    ax.text(x + w / 2, y + h * 0.37, t, ha="center", va="center", fontsize=15.5, fontweight="bold", color=INK)
    ax.text(x + w / 2, y + h * 0.69, s, ha="center", va="center", fontsize=12.5, color=SUB)

def flecha(pts):
    for a, b in zip(pts[:-2], pts[1:-1]):
        ax.plot([a[0], b[0]], [a[1], b[1]], color=LINE, lw=2, solid_capstyle="butt")
    ax.annotate("", xy=pts[-1], xytext=pts[-2], arrowprops=dict(arrowstyle="-|>", color=LINE, lw=2, mutation_scale=16, shrinkA=0, shrinkB=0))

ax.text(42, 42, "Tres caminos separados se juntan en la tabla del modelo", fontsize=19, fontweight="bold", color=INK, va="center")
for cx, t in ((230, "TERRENO · hecho"), (672, "LLUVIA · cambia cada hora"), (1114, "EVENTOS · hecho (versión 1)")):
    ax.text(cx, 99, t, ha="center", va="center", fontsize=13.5, color=SUB, fontweight="bold")
X = {"t": 42, "l": 485, "e": 927}; BW = 376; BH = 100
Y = [127, 304, 481]
caja(X["t"], Y[0], BW, BH, "FABDEM", "alturas cada 30 × 30 m, sin edificios")
caja(X["t"], Y[1], BW, BH, "Polígonos", "17 quebradas (cuencas)")
caja(X["t"], Y[2], BW, BH, "Tabla 1: quebradas", "área y pendiente media")
caja(X["l"], Y[0], BW, BH, "IMERG Early", "cada 30 min, ~11 km, llega ~4 h tarde")
caja(X["l"], Y[1], BW, BH, "Lluvia por hora", "medias horas × 0.5, hora local")
caja(X["l"], Y[2], BW, BH, "Promedio ponderado", "5 celdas, pesos por quebrada")
caja(X["l"], 658, BW, BH, "Tabla 2: lluvia horaria", "25 variables de lluvia (con 4 h de retraso)")
caja(X["e"], Y[0], BW, BH, "Reportes INDECI y prensa", "fecha, hora y quebrada")
caja(X["e"], Y[1], BW, BH, "Tabla 0: catálogo", "130 filas, 26 fechas")
caja(X["e"], Y[2], BW, BH, "Etiquetas y", "¿huaico en las próximas H h?")
caja(318, 852, 708, BH, "Tabla 3: tabla del modelo", "tabla 2 + tabla 1, repetida por horizonte H · 2.86 millones de filas", azul=True)
for cx in (230, 1114):
    flecha([(cx, Y[0] + BH), (cx, Y[1])]); flecha([(cx, Y[1] + BH), (cx, Y[2])])
flecha([(672, Y[0] + BH), (672, Y[1])]); flecha([(672, Y[1] + BH), (672, Y[2])]); flecha([(672, Y[2] + BH), (672, 658)])
flecha([(418, Y[1] + 50), (451, Y[1] + 50), (451, Y[2] + 50), (485, Y[2] + 50)])
flecha([(1114, Y[2] + BH), (1114, 707), (861, 707)])
flecha([(672, 658 + BH), (672, 852)])
flecha([(230, Y[2] + BH), (230, 902), (318, 902)])
fig.savefig("flujo.png", dpi=100, facecolor=fig.get_facecolor()); print("ok")
