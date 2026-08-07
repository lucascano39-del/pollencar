"""Orquestador: python -m pollencar.cli run --poll ... --padron ... --out ...

Corre las cinco capas de punta a punta y deja CSVs + informe HTML en --out.
Re-corrida con ola nueva: mismo comando con la captura nueva (y waves.json
actualizado para el linaje de olas).
"""

import argparse
import csv
import json
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

from . import diagnostics, mi, model, poststrat, rubin
from .io_padron import frequency_tables, load_padron, validate_padron
from .io_poll import flag_non_persons, parse_capture, prepare_respondents
from .linkage import Linker
from .sampler_numpy import run_chains
from .sexo import _load as load_sex_lexicon, infer_sex


def log(msg):
    print(f"[pollencar {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def infer_sex_fb(toks, given_vocab):
    """Sexo del display name FB: léxico primero en orden de tokens; morfología
    solo sobre tokens que existen como nombre de pila en el padrón."""
    lex = load_sex_lexicon()
    for t in toks:
        s = lex.get(t)
        if s in ("M", "F"):
            return s
    for t in toks:
        if t in given_vocab:
            s = infer_sex([t])
            if s != "U":
                return s
    return "U"


def load_or_build_padron(path, cfg, interim, rebuild=False):
    cache = os.path.join(interim, "padron.pkl")
    key = (os.path.getsize(path), int(os.path.getmtime(path)))
    if not rebuild and os.path.exists(cache):
        with open(cache, "rb") as f:
            k, df = pickle.load(f)
        if k == key:
            log("padrón: cache hit")
            return df
    log("padrón: parseando xlsx (esto tarda un poco)...")
    df = load_padron(path, cfg)
    with open(cache, "wb") as f:
        pickle.dump((key, df), f)
    return df


def wave_of_respondents(resp_df, waves_path):
    """wave_first_seen por (nombre normalizado, candidato) desde el registro de olas."""
    if not waves_path or not os.path.exists(waves_path):
        return pd.Series(1, index=resp_df.index), 1
    waves = json.load(open(waves_path, encoding="utf-8"))
    waves = sorted(waves, key=lambda w: w["wave"])
    seen = {}
    for w in waves:
        if not os.path.exists(w["file"]):
            continue
        try:
            _, older = parse_capture(w["file"])
        except (ValueError, OSError):
            continue
        older = prepare_respondents(older)
        for r in older.itertuples():
            seen.setdefault((r.norm_name, r.candidate), w["wave"])
    cur = max((w["wave"] for w in waves), default=1)
    out = resp_df.apply(
        lambda r: seen.get((r["norm_name"], r["candidate"]), cur), axis=1)
    return out, cur


def crude_share(vals):
    return float(np.mean(vals)) if len(vals) else float("nan")


def fit_imputation(linked_df, cfg, seed, n_locals, local_covar=None, chains=None):
    cells = model.respondents_to_cells(linked_df, cfg, n_locals)
    data = model.ModelData(cells, n_locals, local_covar=local_covar)
    draws_by_chain, infos = run_chains(data, cfg["model"], seed, n_chains=chains)
    return cells, data, draws_by_chain, infos


def theta_from_draws(draws_by_chain, ps_cells, lay_slices, cfg, local_covar=None):
    flat = [d for ch in draws_by_chain for d in ch]
    out = {}
    out["A"] = poststrat.mrp_theta_draws(ps_cells, flat, lay_slices, "A", local_covar)
    out["B"] = poststrat.mrp_theta_draws(ps_cells, flat, lay_slices, "B", local_covar, cfg=cfg)
    out["B_flat"] = poststrat.mrp_theta_draws(
        ps_cells, flat, lay_slices, "B", local_covar,
        age_curve_override=cfg["turnout"]["age_curve_flat"], cfg=cfg)
    out["B_steep"] = poststrat.mrp_theta_draws(
        ps_cells, flat, lay_slices, "B", local_covar,
        age_curve_override=cfg["turnout"]["age_curve_steep"], cfg=cfg)
    return out


def linked_frame(assign, resp_df, padron, cand0):
    vote_of = dict(zip(resp_df["resp_id"], (resp_df["candidate"] == cand0).astype(int)))
    rows = []
    for rid, j in assign.items():
        if j is None or rid not in vote_of:
            continue
        rows.append((padron["party_group"].iat[j], padron["sexo"].iat[j],
                     padron["age_band"].iat[j], int(padron["mesa"].iat[j]),
                     vote_of[rid], rid))
    return pd.DataFrame(rows, columns=["party_group", "sexo", "age_band",
                                       "local", "vote", "resp_id"])


def negative_control(linker, resp_df, given_vocab, cfg, rng):
    """Permuta apellidos entre respondentes y reclasifica con el mismo scorer."""
    from .linkage import RespFeatures

    toks_list = [list(t) for t in resp_df["toks"]]
    tails = [t[1:] for t in toks_list if len(t) > 1]
    rng.shuffle(tails)
    it = iter(tails)
    perm = []
    for t in toks_list:
        perm.append(t if len(t) <= 1 else [t[0]] + next(it))
    feats = {i: RespFeatures(perm[i], linker.nicknames,
                             infer_sex_fb(perm[i], given_vocab))
             for i in range(len(perm))}
    compared, _ = linker.compare_all(feats)
    res = linker.classify(feats, compared)
    zones = pd.Series([r["zone"] for r in res.values()]).value_counts()
    return {z: int(zones.get(z, 0)) for z in ("auto", "ambiguous", "nonlink")}


def run(args):
    cfg = json.load(open(args.config, encoding="utf-8"))
    rng = np.random.default_rng(cfg["seed"])
    os.makedirs(args.out, exist_ok=True)
    interim = os.path.join(os.path.dirname(args.out.rstrip("/")), "interim")
    os.makedirs(interim, exist_ok=True)
    results = {"config": cfg, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")}

    # ---------------- capa 1: insumos ----------------
    model.make_levels(cfg)
    padron = load_or_build_padron(args.padron, cfg, interim, rebuild=args.rebuild)
    results["padron_checks"] = validate_padron(padron)
    log(f"padrón ok: {results['padron_checks']}")
    freqs = frequency_tables(padron)
    n_locals = int(padron["mesa"].max())

    cands, poll_raw = parse_capture(args.poll)
    results["candidates"] = cands
    cand0 = cands[0]["candidate"]
    log(f"captura ok: {[(c['candidate'], c['votes_declared']) for c in cands]}")

    lex_dir = os.path.join(os.path.dirname(os.path.abspath(args.config)), "..", "lexicons")
    given_vocab = set(load_sex_lexicon()) | set(padron["giv1"]) | set(padron["giv2"])
    given_vocab.discard("")
    flagged = flag_non_persons(poll_raw, os.path.join(lex_dir, "non_person_pages.csv"),
                               given_vocab)
    excl = flagged[~flagged["is_person"]]
    excl.to_csv(os.path.join(args.out, "excluidos_no_persona.csv"), index=False)
    results["exclusiones"] = (
        excl.assign(tipo=excl["non_person_reason"].str.replace("regex:", "", regex=False))
        .groupby(["candidate", "tipo"]).size().reset_index(name="n")
        .to_dict("records"))
    resp = prepare_respondents(flagged[flagged["is_person"]])
    resp = resp[resp["n_toks"] > 0].reset_index(drop=True)
    resp["sexo_fb"] = resp["toks"].map(lambda t: infer_sex_fb(t, given_vocab))
    resp["wave"], cur_wave = wave_of_respondents(resp, args.waves)
    results["funnel"] = {
        "votos_declarados": int(sum(c["votes_declared"] for c in cands)),
        "nombres_visibles": int(len(poll_raw)),
        "no_persona": int(len(excl)),
        "personas": int(len(resp)),
    }
    results["raw_shares"] = {
        c["candidate"]: c["votes_declared"] / sum(x["votes_declared"] for x in cands)
        for c in cands}
    results["person_share_cand0"] = crude_share((resp["candidate"] == cand0).to_numpy())

    # ---------------- capa 2: enlace ----------------
    log("enlace: bloqueo + comparación...")
    linker = Linker(padron, freqs, cfg)
    feats = linker.features(resp)
    compared, pattern_counts = linker.compare_all(feats)
    n_pairs = sum(len(v) for v in compared.values())
    log(f"enlace: {n_pairs} pares bloqueados, clasificando...")
    try:  # EM de patrones: solo diagnóstico (ver linkage.fit_em)
        m_probs, u_probs, p_pair = linker.fit_em(pattern_counts)
        em_diag = {"prevalencia": float(p_pair),
                   "m": [list(map(float, x)) for x in m_probs],
                   "u": [list(map(float, x)) for x in u_probs]}
    except Exception as e:  # noqa: BLE001 - el EM nunca debe frenar el pipeline
        em_diag = {"error": str(e)}
    link_res = linker.classify(feats, compared)
    zones = pd.Series([r["zone"] for r in link_res.values()]).value_counts()
    results["linkage"] = {
        "pares": int(n_pairs), "lambda_en_marco": float(linker.lam),
        "zonas": {z: int(zones.get(z, 0)) for z in ("auto", "ambiguous", "nonlink")},
        "cell_links": int(sum(1 for r in link_res.values() if r.get("cell_link"))),
        "em_diagnostico": em_diag,
    }
    # tasas de enlace por candidato (diagnóstico de enlace diferencial)
    zc = resp.copy()
    zc["zone"] = zc["resp_id"].map(lambda r: link_res[int(r)]["zone"])
    results["linkage"]["por_candidato"] = (
        zc.groupby(["candidate", "zone"]).size().unstack(fill_value=0)
        .to_dict("index"))
    log(f"enlace: zonas {results['linkage']['zonas']} lambda={linker.lam:.3f}")

    # auditoría manual
    audit_rows = []
    rng_a = np.random.default_rng(cfg["seed"] + 1)
    for zone, k in (("auto", 100), ("ambiguous", 50), ("nonlink", 50)):
        rids = [rid for rid, r in link_res.items() if r["zone"] == zone]
        for rid in rng_a.choice(rids, size=min(k, len(rids)), replace=False):
            r = link_res[int(rid)]
            top = r["cands"][0] if r["cands"] else (None, 0.0)
            pad_name = padron["apellido_nombre"].iat[top[0]] if top[0] is not None else ""
            audit_rows.append({
                "zone": zone, "resp_id": int(rid),
                "fb": resp.loc[resp["resp_id"] == int(rid), "display_name_raw"].iat[0],
                "padron": pad_name, "q_top": round(float(top[1]), 4),
                "q0": round(float(r["q0"]), 4), "n_cands": len(r["cands"]),
            })
    pd.DataFrame(audit_rows).to_csv(os.path.join(args.out, "audit_sample.csv"),
                                    index=False)

    if not args.skip_negctrl:
        log("control negativo (apellidos permutados)...")
        results["control_negativo"] = negative_control(
            linker, resp, given_vocab, cfg, np.random.default_rng(cfg["seed"] + 2))
        log(f"control negativo: {results['control_negativo']}")

    # ---------------- capa 2b: imputación múltiple ----------------
    M = cfg["imputation"]["M"] if not args.fast else 4
    imps = mi.build_imputations(link_res, M, cfg["seed"] + 100)

    # ancla 2023 opcional
    local_covar = None
    anchor_path = cfg["anchors"]["resultados_2023_mesa"]
    if os.path.exists(anchor_path):
        a = pd.read_csv(anchor_path)
        lc = np.zeros(n_locals)
        for r in a.itertuples():
            sh = min(max(float(r.share_cheba_equiv), 0.02), 0.98)
            lc[int(r.local) - 1] = np.log(sh / (1 - sh))
        local_covar = lc
        results["anchor_2023"] = "activa"
    else:
        results["anchor_2023"] = "no disponible (slot documentado, inactivo)"

    # ---------------- capa 3+4: modelo + post-estratificación ----------------
    ps_cells = poststrat.padron_cells(padron, cfg)
    log(f"modelo: M={M} imputaciones x {cfg['model']['chains']} cadenas...")
    theta = {k: [] for k in ("A", "B", "B_flat", "B_steep")}
    theta_A_by_imp = []
    linked_crude = []
    diag_by_imp = []  # diagnósticos POR imputación (posteriors distintos entre sí)
    lay_slices = None
    sample_cells_pooled = []
    t0 = time.time()
    for mth, assign in enumerate(imps):
        ldf = linked_frame(assign, resp, padron, cand0)
        linked_crude.append(crude_share(ldf["vote"].to_numpy()))
        cells, data, draws_by_chain, _ = fit_imputation(
            ldf, cfg, cfg["seed"] + 1000 * mth, n_locals, local_covar)
        sample_cells_pooled.append(cells)
        if lay_slices is None:
            from .model import ParamLayout
            lay_slices = ParamLayout(data).slices
        th = theta_from_draws(draws_by_chain, ps_cells, lay_slices, cfg, local_covar)
        for k in theta:
            theta[k].append(th[k])
        theta_A_by_imp.append(th["A"])
        imp_chains = {"theta_A": [], "beta0": [], "s2_party": [], "s2_age": [],
                      "s2_local": []}
        for ch in draws_by_chain:
            imp_chains["theta_A"].append(poststrat.mrp_theta_draws(
                ps_cells, ch, lay_slices, "A", local_covar))
            imp_chains["beta0"].append(np.array([x[lay_slices["beta0"]][0] for x, _ in ch]))
            imp_chains["s2_party"].append(np.array([s2["u_party"] for _, s2 in ch]))
            imp_chains["s2_age"].append(np.array([s2["u_age"] for _, s2 in ch]))
            imp_chains["s2_local"].append(np.array([s2["u_local"] for _, s2 in ch]))
        diag_by_imp.append(diagnostics.summarize(
            imp_chains, cfg["model"]["rhat_max"], cfg["model"]["ess_min"]))
        log(f"  imputación {mth + 1}/{M} lista ({time.time() - t0:.0f}s)")

    results["linked_crude_share_cand0"] = float(np.nanmean(linked_crude))
    # peor caso entre imputaciones por parámetro (cada imputación es su propio posterior)
    worst = {}
    for name in diag_by_imp[0]["params"]:
        per = [d["params"][name] for d in diag_by_imp]
        wi = max(range(len(per)), key=lambda i: per[i]["rhat"])
        worst[name] = dict(per[wi])
        worst[name]["ess"] = min(p["ess"] for p in per)
        worst[name]["mean"] = float(np.mean([p["mean"] for p in per]))
    results["mcmc"] = {"params": worst,
                       "ok": all(d["ok"] for d in diag_by_imp)}
    pooled = {k: np.concatenate(v) for k, v in theta.items()}
    results["mrp"] = {
        k: {"mean": float(v.mean()),
            "ic95": [float(np.quantile(v, 0.025)), float(np.quantile(v, 0.975))]}
        for k, v in pooled.items()}
    results["rubin"] = rubin.rubin_table(theta_A_by_imp)

    # n por celda-margen = suma de celdas finas dentro de la imputación,
    # promediada entre imputaciones
    pooled_cells = pd.concat(sample_cells_pooled)
    margin_n = (pooled_cells.groupby(
        ["party_idx", "sex_idx", "age_idx"], as_index=False)["n"].sum())
    margin_n["n"] = margin_n["n"] / len(sample_cells_pooled)
    cov = poststrat.coverage_table(ps_cells, margin_n)
    cov["table"].to_csv(os.path.join(args.out, "celdas.csv"), index=False)
    results["cobertura"] = {k: v for k, v in cov.items() if k != "table"}

    # ---------------- sensibilidades ----------------
    if not args.fast:
        log("sensibilidades S1/S2 (nombres en ambas listas)...")
        both = (resp.groupby("norm_name")["candidate"].nunique() > 1)
        both_names = set(both[both].index)
        cross_ids = set(resp.loc[resp["norm_name"].isin(both_names), "resp_id"])
        M_s = min(6, M)
        for label, drop_fn in (
            ("S1_sin_cruzados", lambda rng_: cross_ids),
            ("S2_uno_al_azar", None),
        ):
            th_list = []
            for mth in range(M_s):
                rng_s = np.random.default_rng(cfg["seed"] + 5000 + mth)
                if drop_fn is not None:
                    drop = drop_fn(rng_s)
                else:
                    drop = set()
                    for nm in both_names:
                        ids = list(resp.loc[resp["norm_name"] == nm, "resp_id"])
                        rng_s.shuffle(ids)
                        drop.update(ids[: len(ids) // 2])
                assign = {rid: j for rid, j in imps[mth].items() if rid not in drop}
                ldf = linked_frame(assign, resp, padron, cand0)
                _, data, dbc, _ = fit_imputation(
                    ldf, cfg, cfg["seed"] + 7000 + 1000 * mth, n_locals,
                    local_covar, chains=2)
                th = theta_from_draws(dbc, ps_cells, lay_slices, cfg, local_covar)
                th_list.append(th["A"])
            v = np.concatenate(th_list)
            results.setdefault("sensibilidad", {})[label] = {
                "mean": float(v.mean()),
                "ic95": [float(np.quantile(v, 0.025)), float(np.quantile(v, 0.975))]}

    # ---------------- salidas ----------------
    est_rows = []
    c0, c1 = cands[0]["candidate"], cands[1]["candidate"]
    for k, v in results["mrp"].items():
        est_rows.append({"estimando": f"MRP_{k}", "candidato": c0,
                         "share": v["mean"], "ic95_lo": v["ic95"][0],
                         "ic95_hi": v["ic95"][1]})
        est_rows.append({"estimando": f"MRP_{k}", "candidato": c1,
                         "share": 1 - v["mean"], "ic95_lo": 1 - v["ic95"][1],
                         "ic95_hi": 1 - v["ic95"][0]})
    est_rows.append({"estimando": "crudo_declarado", "candidato": c0,
                     "share": results["raw_shares"][c0], "ic95_lo": None, "ic95_hi": None})
    est_rows.append({"estimando": "crudo_declarado", "candidato": c1,
                     "share": results["raw_shares"][c1], "ic95_lo": None, "ic95_hi": None})
    est_rows.append({"estimando": "solo_personas", "candidato": c0,
                     "share": results["person_share_cand0"], "ic95_lo": None, "ic95_hi": None})
    est_rows.append({"estimando": "solo_enlazados_crudo", "candidato": c0,
                     "share": results["linked_crude_share_cand0"],
                     "ic95_lo": None, "ic95_hi": None})
    pd.DataFrame(est_rows).to_csv(os.path.join(args.out, "estimaciones.csv"), index=False)

    with open(os.path.join(args.out, "resultados.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1, default=str)

    from .report import render_report
    html_path = os.path.join(args.out, "informe_agosto2026.html")
    render_report(results, html_path)
    log(f"listo: {html_path}")
    if not results["mcmc"]["ok"] and args.strict:
        log("ADVERTENCIA: diagnósticos MCMC fuera de umbral (--strict)")
        sys.exit(2)
    return results


def main():
    ap = argparse.ArgumentParser(prog="pollencar")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--poll", required=True)
    r.add_argument("--padron", required=True)
    r.add_argument("--out", default="data/output")
    r.add_argument("--config", default="config/config.json")
    r.add_argument("--waves", default="data/raw/waves.json")
    r.add_argument("--fast", action="store_true", help="M=4, sin sensibilidades")
    r.add_argument("--skip-negctrl", action="store_true")
    r.add_argument("--rebuild", action="store_true", help="ignora caches")
    r.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
