#!/usr/bin/env python3
"""MRP completo para una fuente nominal arbitraria (name,vote en {pereira,cheba}).

Mismo estimando que el pipeline principal: share h2h en el electorado de
Encarnación, escenario votante-probable con curvas de urna. Uso:
    PYTHONPATH=src python3 scripts/mrp_source.py <in.csv> <label> [M]
Escribe data/interim/mrp_<label>.json con cuantiles y draws resumidos de theta_B.
"""
import json
import sys

import numpy as np
import pandas as pd

CFG = json.load(open("config/config.json"))
import pollencar.model as model  # noqa: E402

model.make_levels(CFG)
from pollencar import mi, poststrat  # noqa: E402
from pollencar.cli import (fit_imputation, infer_sex_fb, linked_frame,  # noqa: E402
                           load_or_build_padron, theta_from_draws)
from pollencar.io_padron import frequency_tables  # noqa: E402
from pollencar.linkage import Linker, load_nicknames  # noqa: E402
from pollencar.model import ParamLayout  # noqa: E402
from pollencar.normalize import strong_tokens, tokens  # noqa: E402
from pollencar.sexo import _load as load_sex_lexicon  # noqa: E402


def run(csv_path, label, M=10):
    padron = load_or_build_padron("data/raw/padron_encarnacion_2026.xlsx", CFG,
                                  "data/interim")
    freqs = frequency_tables(padron)
    gv = (set(load_sex_lexicon()) | set(load_nicknames())
          | set(padron["giv1"]) | set(padron["giv2"]))
    gv.discard("")
    n_locals = int(padron["mesa"].max())

    df = pd.read_csv(csv_path)
    df = df[df["vote"].isin(["pereira", "cheba"])].reset_index(drop=True)
    df["resp_id"] = range(len(df))
    df["candidate"] = df["vote"]
    df["toks"] = df["name"].map(lambda s: strong_tokens(tokens(s)))
    df = df[df["toks"].map(len) > 0].reset_index(drop=True)
    df["sexo_fb"] = df["toks"].map(lambda t: infer_sex_fb(t, gv))

    linker = Linker(padron, freqs, CFG)
    feats = {int(r.resp_id): None for r in df.itertuples()}
    feats = linker.features(df)
    compared, _ = linker.compare_all(feats)
    res = linker.classify(feats, compared)
    zones = pd.Series([r["zone"] for r in res.values()]).value_counts()
    print(f"[{label}] n={len(df)} zonas={dict(zones)} lambda={linker.lam:.3f}",
          flush=True)

    imps = mi.build_imputations(res, M, CFG["seed"] + 31)
    ps_cells = poststrat.padron_cells(padron, CFG)
    theta_draws, lay_slices = [], None
    cfg_m = dict(CFG["model"], iters=6000, burnin=2000)
    cfg_run = dict(CFG)
    cfg_run["model"] = cfg_m
    for m, assign in enumerate(imps):
        ldf = linked_frame(assign, df, padron, "pereira")  # theta = share PEREIRA
        _, data, dbc, _ = fit_imputation(ldf, cfg_run, CFG["seed"] + 300 * m,
                                         n_locals)
        if lay_slices is None:
            lay_slices = ParamLayout(data).slices
        th = theta_from_draws(dbc, ps_cells, lay_slices, CFG)
        theta_draws.append(th["B"])
        print(f"[{label}] imp {m + 1}/{M}", flush=True)
    pooled = np.concatenate(theta_draws)
    lo, med, hi = np.quantile(pooled, [0.025, 0.5, 0.975])
    logit = np.log(pooled / (1 - pooled))
    out = {"label": label, "n_h2h": int(len(df)),
           "linked_mean": float(np.mean([r["zone"] != "nonlink"
                                         for r in res.values()])),
           "theta_pereira": {"mean": float(pooled.mean()),
                             "ic95": [float(lo), float(hi)],
                             "median": float(med)},
           "logit_mean": float(logit.mean()), "logit_sd": float(logit.std()),
           "zonas": {k: int(v) for k, v in zones.items()}}
    path = f"data/interim/mrp_{label}.json"
    json.dump(out, open(path, "w"), indent=1)
    print(f"[{label}] Pereira {100 * pooled.mean():.1f}% "
          f"[{100 * lo:.1f}, {100 * hi:.1f}] -> {path}", flush=True)


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 10)
