#!/usr/bin/env python3
"""Serie inter-comparable: TODAS las observaciones en el mismo estimando
(share h2h en el electorado de Encarnación, votante probable) + nivel de HOY.

- Fuentes con nombres (Paraná nov, Meridiano abr, AG widget ago, AG comentarios
  ago): MRP completo (enlace + MI + multinivel + post-estratificación de urnas).
- Fuentes sin nombres (AG reacciones feb, Red Informativa jun): calibración por
  transferencia con el delta empírico del canal de bajo esfuerzo de la misma
  clase de casa (AG comentarios ago: crudo->MRP), banda ancha (sd 0.25 logit).
- Nivel de hoy: Kalman RW en logit (q=0.06/mes, mismo supuesto que la sesión
  serie) + suavizado RTS; a cada obs se le suma sd de casa 0.10 logit (residuo
  de selección no compartido) — 0.25 para las transferidas.

Salida: data/output/serie_calibrada.json + docs/serie_calibrada_20260808.html
"""
import html
import json
import math
from datetime import date

import numpy as np


def logit(p):
    return math.log(p / (1 - p))


def expit(x):
    return 1 / (1 + math.exp(-x))


def load():
    ag = json.load(open("data/output/resultados.json"))
    mrp = {k: json.load(open(f"data/interim/mrp_{k}.json"))
           for k in ("parena", "meridiano", "agcom")}
    return ag, mrp


HOUSE_SD = 0.10   # residuo de selección dentro de celda por casa (logit)
TRANSFER_SD = 0.25
Q_MONTH = 0.06    # RW en logit por mes (supuesto de la sesión serie, citado)


def build_obs(ag, mrp):
    # AG widget ago: theta Pereira = 1 - MRP_B(Cheba); sd desde el IC
    b = ag["mrp"]["B"]
    p_ago = 1 - b["mean"]
    sd_ago = (logit(1 - b["ic95"][0]) - logit(1 - b["ic95"][1])) / 3.92
    # delta de canal bajo-esfuerzo (AG comentarios ago): crudo -> MRP
    raw_agcom = mrp["agcom"]["n_h2h"] and None
    agc = mrp["agcom"]
    raw_p_agcom = 228 / (228 + 361)
    delta_low = agc["logit_mean"] - logit(raw_p_agcom)
    obs = [
        dict(id="parena_1125", fecha="2025-11-25", casa="Paraná (comentarios)",
             tipo="MRP", p=mrp["parena"]["theta_pereira"]["mean"],
             lo=mrp["parena"]["theta_pereira"]["ic95"][0],
             hi=mrp["parena"]["theta_pereira"]["ic95"][1],
             sd=math.hypot(mrp["parena"]["logit_sd"], HOUSE_SD)),
        dict(id="ag_0219", fecha="2026-02-19", casa="Analytics Group (reacciones)",
             tipo="transferida",
             p=expit(logit(902 / 2564) + delta_low), sd=TRANSFER_SD),
        dict(id="meridiano_0414", fecha="2026-04-14", casa="Meridiano (reacciones c/nombres)",
             tipo="MRP", p=mrp["meridiano"]["theta_pereira"]["mean"],
             lo=mrp["meridiano"]["theta_pereira"]["ic95"][0],
             hi=mrp["meridiano"]["theta_pereira"]["ic95"][1],
             sd=math.hypot(mrp["meridiano"]["logit_sd"], HOUSE_SD)),
        dict(id="redinf_06", fecha="2026-06-15", casa="Red Informativa (reacciones)",
             tipo="transferida",
             p=expit(logit(239 / 822) + delta_low), sd=TRANSFER_SD),
        dict(id="ag_0806", fecha="2026-08-06", casa="Analytics Group (widget)",
             tipo="MRP", p=p_ago, lo=1 - b["ic95"][1], hi=1 - b["ic95"][0],
             sd=math.hypot(sd_ago, HOUSE_SD)),
        dict(id="agcom_0806", fecha="2026-08-06", casa="AG comentarios (auxiliar)",
             tipo="auxiliar", p=agc["theta_pereira"]["mean"],
             lo=agc["theta_pereira"]["ic95"][0],
             hi=agc["theta_pereira"]["ic95"][1],
             sd=math.hypot(agc["logit_sd"], HOUSE_SD)),
    ]
    for o in obs:
        o["y"] = logit(o["p"])
        if "lo" not in o:
            o["lo"] = expit(o["y"] - 1.96 * o["sd"])
            o["hi"] = expit(o["y"] + 1.96 * o["sd"])
    return obs, delta_low


def kalman(obs, hoy="2026-08-08"):
    # solo obs primarias (la auxiliar comparte post/fecha con el widget)
    prim = [o for o in obs if o["tipo"] != "auxiliar"]
    d0 = date.fromisoformat(prim[0]["fecha"])
    ts = [(date.fromisoformat(o["fecha"]) - d0).days / 30.0 for o in prim]
    t_hoy = (date.fromisoformat(hoy) - d0).days / 30.0
    ys = [o["y"] for o in prim]
    rs = [o["sd"] ** 2 for o in prim]
    # filtro
    m, v = ys[0], rs[0]
    ms, vs, preds = [m], [v], []
    for i in range(1, len(ys)):
        dt = ts[i] - ts[i - 1]
        v_pred = v + Q_MONTH ** 2 * dt
        preds.append((m, v_pred))
        k = v_pred / (v_pred + rs[i])
        m = m + k * (ys[i] - m)
        v = (1 - k) * v_pred
        ms.append(m)
        vs.append(v)
    # RTS smoother
    sm, sv = [None] * len(ys), [None] * len(ys)
    sm[-1], sv[-1] = ms[-1], vs[-1]
    for i in range(len(ys) - 2, -1, -1):
        dt = ts[i + 1] - ts[i]
        v_pred = vs[i] + Q_MONTH ** 2 * dt
        c = vs[i] / v_pred
        sm[i] = ms[i] + c * (sm[i + 1] - (ms[i]))
        sv[i] = vs[i] + c ** 2 * (sv[i + 1] - v_pred)
    # nivel HOY: predicción desde la última obs
    dt = t_hoy - ts[-1]
    m_hoy, v_hoy = ms[-1], vs[-1] + Q_MONTH ** 2 * dt
    return {"ts": ts, "smooth": [(expit(a), a, b) for a, b in zip(sm, sv)],
            "hoy": {"p": expit(m_hoy), "sd": math.sqrt(v_hoy),
                    "ic95": [expit(m_hoy - 1.96 * math.sqrt(v_hoy)),
                             expit(m_hoy + 1.96 * math.sqrt(v_hoy))]}}


def render(obs, kal, delta_low, out_html):
    W, H, PL, PR, PT, PB = 760, 380, 56, 24, 20, 46
    d0 = date.fromisoformat("2025-11-01")
    d1 = date.fromisoformat("2026-08-31")

    def X(fecha):
        d = date.fromisoformat(fecha)
        return PL + (d - d0).days / (d1 - d0).days * (W - PL - PR)

    y_lo, y_hi = 0.35, 0.70  # eje en share CHEBA

    def Y(p_cheba):
        return PT + (y_hi - p_cheba) / (y_hi - y_lo) * (H - PT - PB)

    s = [f'<svg viewBox="0 0 {W} {H}" role="img" style="width:100%;height:auto" '
         f'aria-label="Serie calibrada">']
    for t in np.arange(0.35, 0.701, 0.05):
        s.append(f'<line x1="{PL}" y1="{Y(t):.1f}" x2="{W-PR}" y2="{Y(t):.1f}" '
                 f'stroke="var(--grid)"/>'
                 f'<text x="{PL-8}" y="{Y(t)+4:.1f}" text-anchor="end" '
                 f'fill="var(--muted)" font-size="11">{100*t:.0f}%</text>')
    s.append(f'<line x1="{PL}" y1="{Y(0.5):.1f}" x2="{W-PR}" y2="{Y(0.5):.1f}" '
             f'stroke="var(--baseline)" stroke-width="1.5" stroke-dasharray="4 3"/>')
    months = [("2025-12-01", "dic"), ("2026-02-01", "feb"), ("2026-04-01", "abr"),
              ("2026-06-01", "jun"), ("2026-08-01", "ago")]
    for f, lab in months:
        s.append(f'<text x="{X(f):.1f}" y="{H-16}" text-anchor="middle" '
                 f'fill="var(--muted)" font-size="11">{lab}</text>')
    # banda y línea suavizada (share Cheba = 1 - p)
    prim = [o for o in obs if o["tipo"] != "auxiliar"]
    pts_u, pts_l, pts_m = [], [], []
    for o, (p_sm, mlog, vlog) in zip(prim, kal["smooth"]):
        x = X(o["fecha"])
        sd = math.sqrt(max(vlog, 1e-9))
        pts_m.append((x, Y(1 - p_sm)))
        pts_u.append((x, Y(1 - expit(mlog - 1.96 * sd))))
        pts_l.append((x, Y(1 - expit(mlog + 1.96 * sd))))
    band = ("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts_u)
            + " L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in reversed(pts_l)) + " Z")
    s.append(f'<path d="{band}" fill="var(--s1)" opacity="0.12"/>')
    line = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts_m)
    s.append(f'<path d="{line}" fill="none" stroke="var(--s1)" stroke-width="2" '
             f'opacity="0.7"/>')
    # observaciones
    for o in obs:
        x, pc = X(o["fecha"]), 1 - o["p"]
        y = Y(pc)
        ylo, yhi = Y(1 - o["lo"]), Y(1 - o["hi"])
        aux = o["tipo"] == "auxiliar"
        op = "0.55" if aux else "1"
        s.append(f'<line x1="{x:.1f}" y1="{ylo:.1f}" x2="{x:.1f}" y2="{yhi:.1f}" '
                 f'stroke="var(--s1)" stroke-width="2" opacity="{op}"/>')
        if o["tipo"] == "transferida":
            s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="var(--surface)" '
                     f'stroke="var(--s1)" stroke-width="2"/>')
        else:
            s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="var(--s1)" '
                     f'opacity="{op}"/>')
        s.append(f'<text x="{x:.1f}" y="{min(ylo, yhi)-8:.1f}" text-anchor="middle" '
                 f'fill="var(--ink2)" font-size="11" opacity="{op}">{100*pc:.0f}%</text>')
    # HOY
    hoy = kal["hoy"]
    xh, yh = X("2026-08-08") + 6, Y(1 - hoy["p"])
    s.append(f'<path d="M{xh:.1f},{yh-7:.1f} l7,7 l-7,7 l-7,-7 Z" fill="var(--s1)"/>'
             f'<text x="{xh:.1f}" y="{yh-14:.1f}" text-anchor="middle" font-size="12" '
             f'font-weight="650" fill="var(--ink)">{100*(1-hoy["p"]):.1f}%</text>')
    s.append('</svg>')
    svg = "".join(s)

    rows = "".join(
        f"<tr><td>{o['fecha']}</td><td>{html.escape(o['casa'])}</td>"
        f"<td>{o['tipo']}</td>"
        f"<td>{100*(1-o['p']):.1f}%</td><td>{100*(1-o['hi']):.1f} – {100*(1-o['lo']):.1f}</td>"
        f"<td>{100*o['p']:.1f}%</td></tr>"
        for o in obs)
    doc = f"""<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Serie calibrada — electorado de Encarnación</title>
<style>
:root {{ color-scheme: light dark; }}
.viz-root {{ --surface:#fcfcfb; --page:#f9f9f7; --ink:#0b0b0b; --ink2:#52514e;
  --muted:#898781; --grid:#e1e0d9; --baseline:#c3c2b7; --s1:#2a78d6; --s2:#eb6834;
  --border:rgba(11,11,11,0.10);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  background: var(--page); color: var(--ink); max-width: 860px; margin: 0 auto;
  padding: 24px 16px 64px; line-height: 1.55; }}
@media (prefers-color-scheme: dark) {{ :root:where(:not([data-theme="light"])) .viz-root {{
  --surface:#1a1a19; --page:#0d0d0d; --ink:#fff; --ink2:#c3c2b7; --grid:#2c2c2a;
  --baseline:#383835; --s1:#3987e5; --s2:#d95926; --border:rgba(255,255,255,0.10); }} }}
:root[data-theme="dark"] .viz-root {{ --surface:#1a1a19; --page:#0d0d0d; --ink:#fff;
  --ink2:#c3c2b7; --grid:#2c2c2a; --baseline:#383835; --s1:#3987e5; --s2:#d95926;
  --border:rgba(255,255,255,0.10); }}
.card {{ background:var(--surface); border:1px solid var(--border); border-radius:10px;
  padding:16px; margin:12px 0; }}
h1 {{ font-size:1.4rem; margin:0 0 4px; }} h2 {{ font-size:1.05rem; margin:24px 0 8px; }}
.sub {{ color:var(--ink2); margin-bottom:16px; }}
table {{ border-collapse:collapse; width:100%; font-size:0.88rem; }}
th,td {{ text-align:left; padding:6px 10px; border-bottom:1px solid var(--grid); }}
th {{ color:var(--ink2); }} td:nth-child(n+4) {{ font-variant-numeric: tabular-nums; }}
.tblwrap {{ overflow-x:auto; }} .note {{ font-size:0.88rem; color:var(--ink2); }}
.hero-num {{ font-size:2rem; font-weight:650; }}
</style>
<div class="viz-root">
<h1>Serie calibrada — intendencia de Encarnación 2026</h1>
<div class="sub">Un solo estimando en toda la serie: share h2h Cheba/Pereira en el
<b>electorado de Encarnación</b> (padrón TSJE, votante probable con curvas de urna).
Nada de crudos. Generado 2026-08-08.</div>
<div class="card">
<div class="hero-num">Cheba {100*(1-hoy['p']):.1f}% — Pereira {100*hoy['p']:.1f}%</div>
<div class="note">Nivel a hoy (2026-08-08), filtro de nivel sobre la serie calibrada ·
IC 95% Cheba: {100*(1-hoy['ic95'][1]):.1f} – {100*(1-hoy['ic95'][0]):.1f}</div>
</div>
<h2>La serie (eje: share de Cheba en el electorado)</h2>
<div class="card">{svg}
<p class="note">Puntos llenos = MRP completo sobre microdatos nominales (enlace al
padrón + imputación múltiple + post-estratificación). Puntos vacíos = observaciones
sin nombres, calibradas por transferencia (Δ canal bajo-esfuerzo = {delta_low:+.3f}
logit, estimado del par crudo→MRP de AG-comentarios ago) — banda ancha. Punto
atenuado = canal auxiliar (mismo post que el widget). Línea y banda: nivel suavizado
(RW logit, q=0.06/mes). Rombo = hoy.</p></div>
<h2>Tabla</h2>
<div class="card tblwrap"><table>
<thead><tr><th>Fecha</th><th>Fuente</th><th>Tratamiento</th><th>Cheba</th>
<th>IC 95% Cheba</th><th>Pereira</th></tr></thead><tbody>{rows}</tbody></table>
<p class="note">Cada IC incluye muestreo + enlace (MI) + residuo de casa (±0.10
logit; ±0.25 para transferidas). Paraná era a 3 candidatos: h2h excluye los votos
a Florentín (43). Límite honesto: el ajuste corrige marco y composición observable;
la selección no observable dentro de celda queda cubierta solo por el término de
casa del filtro.</p></div>
</div>"""
    open(out_html, "w", encoding="utf-8").write(doc)


if __name__ == "__main__":
    ag, mrp = load()
    obs, delta_low = build_obs(ag, mrp)
    kal = kalman(obs)
    json.dump({"obs": [{k: v for k, v in o.items()} for o in obs],
               "delta_canal_bajo_esfuerzo": delta_low, "hoy": kal["hoy"],
               "supuestos": {"house_sd": HOUSE_SD, "transfer_sd": TRANSFER_SD,
                             "q_mes": Q_MONTH}},
              open("data/output/serie_calibrada.json", "w"), indent=1)
    render(obs, kal, delta_low, "docs/serie_calibrada_20260808.html")
    print("HOY: Pereira", round(100 * kal["hoy"]["p"], 1),
          "Cheba", round(100 * (1 - kal["hoy"]["p"]), 1),
          "IC", [round(100 * x, 1) for x in kal["hoy"]["ic95"]])
