"""Capa 5 — Informe HTML autocontenido (español), sin dependencias de plotting.

Gráfico principal: cadena de shares (crudo → personas → enlazados → MRP) como
dot-plot con intervalos de credibilidad, SVG generado acá mismo. Colores y
tipografía siguen la paleta de referencia (roles CSS, claro/oscuro).
"""

import html


def _fmt_pct(x, nd=1):
    return f"{100 * x:.{nd}f}%" if x is not None and x == x else "—"


def _interval_chart(rows, x_lo, x_hi):
    """rows: (etiqueta, valor, lo, hi, es_primaria). Dot + whisker, eje único."""
    W, H = 720, 40 * len(rows) + 60
    PL, PR, PT = 210, 30, 16
    plot_w = W - PL - PR

    def X(v):
        return PL + (v - x_lo) / (x_hi - x_lo) * plot_w

    parts = [
        f'<svg viewBox="0 0 {W} {H}" role="img" '
        f'style="width:100%;height:auto;max-width:{W}px" '
        f'aria-label="Cadena de estimaciones">'
    ]
    # gridlines + ticks
    import numpy as np

    ticks = [t for t in np.arange(round(x_lo * 20) / 20, x_hi + 1e-9, 0.05)]
    for t in ticks:
        x = X(t)
        parts.append(
            f'<line x1="{x:.1f}" y1="{PT}" x2="{x:.1f}" y2="{H - 34}" '
            f'stroke="var(--grid)" stroke-width="1"/>'
            f'<text x="{x:.1f}" y="{H - 18}" text-anchor="middle" '
            f'fill="var(--muted)" font-size="12">{_fmt_pct(t, 0)}</text>'
        )
    # línea de referencia 50%
    x50 = X(0.5)
    parts.append(
        f'<line x1="{x50:.1f}" y1="{PT}" x2="{x50:.1f}" y2="{H - 34}" '
        f'stroke="var(--baseline)" stroke-width="1.5" stroke-dasharray="4 3"/>'
    )
    for i, (label, v, lo, hi, primary) in enumerate(rows):
        y = PT + 20 + 40 * i
        op = "1" if primary else "0.55"
        parts.append(
            f'<text x="{PL - 12}" y="{y + 4}" text-anchor="end" '
            f'fill="var(--ink)" font-size="13" opacity="{op}">{html.escape(label)}</text>'
        )
        if lo is not None and hi is not None:
            parts.append(
                f'<line x1="{X(lo):.1f}" y1="{y}" x2="{X(hi):.1f}" y2="{y}" '
                f'stroke="var(--s1)" stroke-width="2" opacity="{op}"/>'
                f'<line x1="{X(lo):.1f}" y1="{y - 4}" x2="{X(lo):.1f}" y2="{y + 4}" '
                f'stroke="var(--s1)" stroke-width="2" opacity="{op}"/>'
                f'<line x1="{X(hi):.1f}" y1="{y - 4}" x2="{X(hi):.1f}" y2="{y + 4}" '
                f'stroke="var(--s1)" stroke-width="2" opacity="{op}"/>'
            )
        if v is not None and v == v:
            parts.append(
                f'<circle cx="{X(v):.1f}" cy="{y}" r="5" fill="var(--s1)" '
                f'opacity="{op}"/>'
                f'<text x="{X(v):.1f}" y="{y - 10}" text-anchor="middle" '
                f'fill="var(--ink2)" font-size="11" opacity="{op}">{_fmt_pct(v)}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def _table(headers, rows):
    th = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    trs = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>"
        for r in rows
    )
    return f'<div class="tblwrap"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def render_report(results, out_path):
    cands = results["candidates"]
    c0, c1 = cands[0]["candidate"], cands[1]["candidate"]
    mrp = results.get("mrp", {})
    raw = results["raw_shares"]

    chain = [
        (f"Crudo declarado ({c0})", raw[c0], None, None, False),
        ("Solo personas", results.get("person_share_cand0"), None, None, False),
        ("Solo enlazados (crudo)", results.get("linked_crude_share_cand0"), None, None, False),
    ]
    label_map = [
        ("A", "MRP — todos los inscriptos", True),
        ("B", "MRP — votante probable", True),
        ("B_flat", "MRP — VP curva plana", False),
        ("B_steep", "MRP — VP curva empinada", False),
    ]
    for key, label, primary in label_map:
        if key in mrp:
            chain.append((label, mrp[key]["mean"], mrp[key]["ic95"][0],
                          mrp[key]["ic95"][1], primary))
    for key, sens in results.get("sensibilidad", {}).items():
        chain.append((f"Sens. {key}", sens["mean"], sens["ic95"][0],
                      sens["ic95"][1], False))

    vals = [v for _, v, lo, hi, _ in chain for v in (v, lo, hi) if v is not None and v == v]
    x_lo = min(min(vals) - 0.03, 0.45)
    x_hi = max(max(vals) + 0.03, 0.55)

    headline = mrp.get("B") or mrp.get("A")
    hero = ""
    if headline:
        hero = f"""
  <div class="heroes">
    <div class="hero"><div class="hero-name"><span class="dot" style="background:var(--s1)"></span>{html.escape(c0)}</div>
      <div class="hero-num">{_fmt_pct(headline['mean'])}</div>
      <div class="hero-ci">IC 95%: {_fmt_pct(headline['ic95'][0])} – {_fmt_pct(headline['ic95'][1])}</div></div>
    <div class="hero"><div class="hero-name"><span class="dot" style="background:var(--s2)"></span>{html.escape(c1)}</div>
      <div class="hero-num">{_fmt_pct(1 - headline['mean'])}</div>
      <div class="hero-ci">IC 95%: {_fmt_pct(1 - headline['ic95'][1])} – {_fmt_pct(1 - headline['ic95'][0])}</div></div>
  </div>"""

    fun = results["funnel"]
    lk = results.get("linkage", {})
    zones = lk.get("zonas", {})
    linked_n = zones.get("auto", 0)
    funnel_rows = [
        ("Votos declarados por la UI del poll", fun["votos_declarados"]),
        ("Nombres visibles capturados", fun["nombres_visibles"]),
        ("Excluidos: páginas / no-personas", fun["no_persona"]),
        ("Respondentes persona", fun["personas"]),
        ("Enlace automático (cédula única)", zones.get("auto", 0)),
        ("Enlace dudoso → imputación múltiple", zones.get("ambiguous", 0)),
        ("Sin enlace (probable fuera del distrito)", zones.get("nonlink", 0)),
    ]

    coord_rows = [(e["candidate"], e["tipo"], e["n"])
                  for e in results.get("exclusiones", [])
                  if e["tipo"] == "politica"] or [("—", "—", 0)]

    porcand = lk.get("por_candidato", {})
    porcand_rows = []
    for cand, z in porcand.items():
        tot = sum(z.values()) or 1
        porcand_rows.append((cand, z.get("auto", 0), z.get("ambiguous", 0),
                             z.get("nonlink", 0),
                             _fmt_pct((z.get("auto", 0) + z.get("ambiguous", 0)) / tot)))

    cov = results.get("cobertura", {})
    rub = results.get("rubin", {})
    mcmc = results.get("mcmc", {"params": {}, "ok": None})
    negc = results.get("control_negativo")
    turnout = results["config"]["turnout"]

    mcmc_rows = [(k, f"{v['mean']:.3f}", f"{v['rhat']:.3f}", f"{v['ess']:.0f}")
                 for k, v in mcmc["params"].items()]

    doc = f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Intención de voto — Encarnación 2026 (agosto)</title>
<style>
:root {{ color-scheme: light dark; }}
.viz-root {{
  --surface:#fcfcfb; --page:#f9f9f7; --ink:#0b0b0b; --ink2:#52514e;
  --muted:#898781; --grid:#e1e0d9; --baseline:#c3c2b7;
  --s1:#2a78d6; --s2:#eb6834; --warn:#fab219;
  --border:rgba(11,11,11,0.10);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  background: var(--page); color: var(--ink);
  max-width: 860px; margin: 0 auto; padding: 24px 16px 64px;
  line-height: 1.55;
}}
@media (prefers-color-scheme: dark) {{
  :root:where(:not([data-theme="light"])) .viz-root {{
    --surface:#1a1a19; --page:#0d0d0d; --ink:#ffffff; --ink2:#c3c2b7;
    --grid:#2c2c2a; --baseline:#383835; --s1:#3987e5; --s2:#d95926;
    --border:rgba(255,255,255,0.10);
  }}
}}
:root[data-theme="dark"] .viz-root {{
  --surface:#1a1a19; --page:#0d0d0d; --ink:#ffffff; --ink2:#c3c2b7;
  --grid:#2c2c2a; --baseline:#383835; --s1:#3987e5; --s2:#d95926;
  --border:rgba(255,255,255,0.10);
}}
.viz-root h1 {{ font-size: 1.5rem; margin: 0 0 4px; }}
.viz-root h2 {{ font-size: 1.1rem; margin: 32px 0 8px; }}
.viz-root .sub {{ color: var(--ink2); margin-bottom: 20px; }}
.card {{ background: var(--surface); border: 1px solid var(--border);
        border-radius: 10px; padding: 16px; margin: 12px 0; }}
.heroes {{ display:flex; gap:12px; flex-wrap:wrap; }}
.hero {{ flex:1 1 200px; background:var(--surface); border:1px solid var(--border);
        border-radius:10px; padding:14px 16px; }}
.hero-name {{ color:var(--ink2); font-size:0.95rem; display:flex; align-items:center; gap:8px; }}
.hero-num {{ font-size:2.1rem; font-weight:650; margin:2px 0; }}
.hero-ci {{ color:var(--muted); font-size:0.85rem; }}
.dot {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
.tblwrap {{ overflow-x:auto; }}
table {{ border-collapse: collapse; width:100%; font-size:0.9rem; }}
th, td {{ text-align:left; padding:6px 10px; border-bottom:1px solid var(--grid); }}
th {{ color:var(--ink2); font-weight:600; }}
td:nth-child(n+2), th:nth-child(n+2) {{ font-variant-numeric: tabular-nums; }}
.note {{ font-size:0.88rem; color:var(--ink2); }}
.badge {{ display:inline-block; padding:2px 8px; border-radius:999px;
         font-size:0.8rem; border:1px solid var(--border); }}
</style>
<div class="viz-root">
<h1>Intención de voto — Intendencia de Encarnación 2026</h1>
<div class="sub">Estimación modelada de agosto 2026 · straw poll de Facebook enlazada al
padrón definitivo TSJE y ajustada por MRP · generado {html.escape(results['generated_at'])}</div>

{hero}
<p class="note">Titular = escenario «votante probable». La estimación ajusta la
muestra autoseleccionada por afiliación partidaria individual, sexo, edad y local
de votación contra las {results['padron_checks']['filas']:,} personas del padrón;
el intervalo incluye la incertidumbre del enlace (imputación múltiple).</p>

<h2>Cadena de estimaciones — share de {html.escape(c0)}</h2>
<div class="card">{_interval_chart(chain, x_lo, x_hi)}
<p class="note">La línea punteada marca 50%. Filas atenuadas = referencias y
sensibilidades; las dos filas MRP son las estimaciones defendibles.</p></div>

<h2>Embudo de datos y enlace</h2>
<div class="card">{_table(["Etapa", "n"], funnel_rows)}
<p class="note">λ (share de respondentes estimados dentro del marco electoral de
Encarnación): {_fmt_pct(lk.get('lambda_en_marco'))}. Los «sin enlace» son en su
mayoría votantes de otras ciudades de Itapúa que ven la página pero no eligen
intendente acá — excluirlos es correcto, no una pérdida.</p></div>

<h2>Enlace por candidato (diagnóstico de enlace diferencial)</h2>
<div class="card">{_table(["Candidato", "Auto", "Dudoso", "Sin enlace", "% en marco"], porcand_rows)}
<p class="note">Si un candidato enlaza sistemáticamente menos, su electorado del
poll vive más fuera del distrito (o usa más seudónimos): el ajuste MRP corrige la
composición de los enlazados, no puede recuperar a los no enlazados.</p></div>

<h2>Señal de coordinación (páginas no-persona que votaron)</h2>
<div class="card">{_table(["Candidato", "Tipo", "n"], coord_rows)}
<p class="note">Páginas políticas, comercios y medios votando en el poll. Se
excluyen del análisis; el desbalance entre candidatos es en sí un indicador de
movilización organizada de la audiencia.</p></div>

<h2>Incertidumbre por enlace dudoso (Rubin)</h2>
<div class="card">{_table(["M", "θ̂", "W (muestreo)", "B (enlace)", "FMI"],
    [(rub.get('M', '—'), _fmt_pct(rub.get('theta_hat')),
      f"{rub.get('W_within', 0):.5f}", f"{rub.get('B_between', 0):.5f}",
      f"{rub.get('fmi', 0):.3f}")])}
<p class="note">FMI = fracción de la incertidumbre total atribuible a la
ambigüedad del enlace. Los IC del titular ya la incluyen.</p></div>

<h2>Cobertura de celdas</h2>
<div class="card">
<p>Share del padrón en celdas (partido × sexo × edad) sin muestra:
<b>{_fmt_pct(cov.get('share_padron_en_celdas_n0'))}</b> · con n&lt;5:
<b>{_fmt_pct(cov.get('share_padron_en_celdas_n_lt5'))}</b></p>
<p class="note">Las celdas sin muestra se predicen por pooling parcial (ese es el
mecanismo de MRP); si estos shares son altos, el peso de los priors crece y el IC
lo refleja. Detalle en <code>celdas.csv</code>.</p></div>

<h2>Diagnósticos MCMC {'<span class="badge">OK</span>' if mcmc.get('ok') else '<span class="badge" style="border-color:var(--warn)">revisar</span>'}</h2>
<div class="card">{_table(["Parámetro", "Media", "R̂", "ESS"], mcmc_rows)}
{f'<p class="note">Control negativo (apellidos permutados): auto-links {negc.get("auto", "—")} de {sum(negc.values()) if negc else "—"} — el clasificador colapsa con datos falsos, como debe.</p>' if negc else ''}
</div>

<h2>Supuestos del votante probable</h2>
<div class="card">{_table(["Banda", "P(vota)"], list(turnout['age_curve'].items()))}
<p class="note">Curva prior escalada a participación municipal objetivo
{_fmt_pct(turnout['target_municipal'], 0)} × factor por tipo de inscripción
(tradicional {turnout['tipo_inscrip_factor']['TRADICIONAL']}, automática
{turnout['tipo_inscrip_factor']['AUTOMATICA']}). Sensibilidad con curvas plana y
empinada en el gráfico principal. Ancla 2023: {html.escape(str(results.get('anchor_2023')))}.</p></div>

<h2>Límites de lectura</h2>
<div class="card note">
Una muestra autoseleccionada de Facebook se puede ajustar por lo <b>observable</b>
(afiliación, sexo, edad, local); ningún modelo corrige la autoselección por lo
inobservable (motivación, clima de opinión de la página). Hay una sola página y
una sola ola: el efecto de casa no es separable todavía (el término existe y se
activa con la segunda fuente). Sin ancla probabilística, esto es una
<b>estimación modelada de intención de voto</b>, no una encuesta probabilística —
útil para tendencia y magnitud, con los IC como piso (no techo) del error real.
</div>
</div>"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return out_path
