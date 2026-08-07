"""Capa 4 — Post-estratificación sobre el marco completo del padrón.

theta = sum_c N_c * w_turn(c) * p_c / sum_c N_c * w_turn(c), por draw posterior.
Escenario A: todos los inscriptos (w=1). Escenario B: votante probable con
curva etaria prior escalada a la participación municipal objetivo y factor por
tipo de inscripción como proxy de engagement.
"""

import numpy as np

from . import model


def padron_cells(padron_df, cfg):
    """Grilla fina partido x sexo x edad x local con N y w de participación."""
    df = padron_df.copy()
    pidx = {p: i for i, p in enumerate(model.PARTY_LEVELS)}
    sidx = {s: i for i, s in enumerate(model.SEX_LEVELS)}
    aidx = {a: i for i, a in enumerate(model.AGE_LEVELS)}
    df["party_idx"] = df["party_group"].map(pidx)
    df["sex_idx"] = df["sexo"].map(sidx)
    df["age_idx"] = df["age_band"].map(aidx)
    df["local_idx"] = df["mesa"].astype(int) - 1

    curve = cfg["turnout"]["age_curve"]
    insc = cfg["turnout"]["tipo_inscrip_factor"]
    df["w_raw"] = (df["age_band"].map(curve).astype(float)
                   * df["tipo_inscrip"].map(insc).fillna(1.0).astype(float))
    # escala para que la participación media padrón-ponderada dé el target
    scale = cfg["turnout"]["target_municipal"] / max(float(df["w_raw"].mean()), 1e-9)
    df["w_turnout"] = np.clip(df["w_raw"] * scale, 0.02, 0.98)

    g = (df.groupby(["party_idx", "sex_idx", "age_idx", "local_idx"])
           .agg(N=("cedula", "size"), w_turnout=("w_turnout", "mean"))
           .reset_index())
    return g


def cell_eta(cells, x, slices, local_covar=None):
    e = np.full(len(cells), x[slices["beta0"]][0])
    bs = x[slices["beta_sex"]]
    sx = cells["sex_idx"].to_numpy()
    e += np.where(sx == 1, bs[0], 0.0) + np.where(sx == 2, bs[1], 0.0)
    e += (x[slices["u_party"]][cells["party_idx"].to_numpy()]
          + x[slices["u_age"]][cells["age_idx"].to_numpy()]
          + x[slices["u_local"]][cells["local_idx"].to_numpy()])
    if local_covar is not None and "beta23" in slices:
        e += x[slices["beta23"]][0] * local_covar[cells["local_idx"].to_numpy()]
    return e


def mrp_theta_draws(cells, draws, slices, scenario="A", local_covar=None,
                    age_curve_override=None, cfg=None):
    """Array de draws posteriores de theta para un escenario de participación."""
    N = cells["N"].to_numpy(float)
    if scenario == "A":
        w = N
    else:
        wt = cells["w_turnout"].to_numpy(float)
        if age_curve_override is not None:
            # re-mapea la curva etaria alternativa manteniendo el factor inscripción
            base = np.array([cfg["turnout"]["age_curve"][a] for a in model.AGE_LEVELS])
            alt = np.array([age_curve_override[a] for a in model.AGE_LEVELS])
            ratio = alt / base
            wt = wt * ratio[cells["age_idx"].to_numpy()]
        w = N * np.clip(wt, 0.02, 0.98)
    out = np.empty(len(draws))
    for i, (x, _s2) in enumerate(draws):
        p = 1.0 / (1.0 + np.exp(-cell_eta(cells, x, slices, local_covar)))
        out[i] = float((w * p).sum() / w.sum())
    return out


def coverage_table(cells, sample_cells_df):
    """Cobertura muestral sobre el margen partido x sexo x edad (90 celdas)."""
    frame = (cells.groupby(["party_idx", "sex_idx", "age_idx"])["N"].sum()
             .reset_index())
    samp = (sample_cells_df.groupby(["party_idx", "sex_idx", "age_idx"])["n"].sum()
            .reset_index())
    t = frame.merge(samp, on=["party_idx", "sex_idx", "age_idx"], how="left").fillna(0)
    t["party"] = t["party_idx"].map(dict(enumerate(model.PARTY_LEVELS)))
    t["sexo"] = t["sex_idx"].map(dict(enumerate(model.SEX_LEVELS)))
    t["edad"] = t["age_idx"].map(dict(enumerate(model.AGE_LEVELS)))
    total_N = t["N"].sum()
    return {
        "table": t[["party", "sexo", "edad", "N", "n"]],
        "share_padron_en_celdas_n0": float(t.loc[t["n"] == 0, "N"].sum() / total_N),
        "share_padron_en_celdas_n_lt5": float(t.loc[t["n"] < 5, "N"].sum() / total_N),
    }
