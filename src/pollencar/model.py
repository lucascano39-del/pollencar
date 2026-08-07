"""Capa 3 — Modelo multinivel bayesiano (binomial-logit) sobre celdas realizadas.

logit(p_c) = beta0 + beta_sexo[s] + u_partido[g] + u_edad[a] + u_local[l]
             (+ beta23 * x23[l] si hay ancla 2023) (+ u_ola / u_pagina con >=2 niveles)

Los niveles de RE existen TODOS (incluso sin datos muestrales): los locales sin
muestra sortean de su prior N(0, sigma2) — eso es exactamente lo que MRP necesita
para predecir celdas vacías con pooling parcial.
"""

import numpy as np

SEX_LEVELS = ["F", "M", "U"]
AGE_LEVELS = None  # se fija desde config
PARTY_LEVELS = None


def make_levels(cfg):
    global AGE_LEVELS, PARTY_LEVELS
    bands = cfg["poststrat"]["age_bands"]
    AGE_LEVELS = [f"{lo}-{hi}" if hi < 100 else f"{lo}+" for lo, hi in bands]
    PARTY_LEVELS = cfg["poststrat"]["party_groups"]
    return PARTY_LEVELS, SEX_LEVELS, AGE_LEVELS


class ModelData:
    """Celdas realizadas de una imputación + estructura de niveles."""

    def __init__(self, cells_df, n_locals, local_covar=None, extra=None):
        # cells_df: party_idx, sex_idx, age_idx, local_idx, n, y
        self.ip = cells_df["party_idx"].to_numpy(int)
        self.isx = cells_df["sex_idx"].to_numpy(int)
        self.ia = cells_df["age_idx"].to_numpy(int)
        self.il = cells_df["local_idx"].to_numpy(int)
        self.n = cells_df["n"].to_numpy(float)
        self.y = cells_df["y"].to_numpy(float)
        self.C = len(cells_df)
        self.n_party = len(PARTY_LEVELS)
        self.n_age = len(AGE_LEVELS)
        self.n_local = n_locals
        self.local_covar = local_covar  # array (n_locals,) o None
        self.extra = extra or {}


def respondents_to_cells(linked_df, cfg, n_locals):
    """linked_df: party_group, sexo, age_band, local (1..40), vote (0/1)."""
    make_levels(cfg)
    pidx = {p: i for i, p in enumerate(PARTY_LEVELS)}
    sidx = {s: i for i, s in enumerate(SEX_LEVELS)}
    aidx = {a: i for i, a in enumerate(AGE_LEVELS)}
    df = linked_df.copy()
    df["party_idx"] = df["party_group"].map(pidx)
    df["sex_idx"] = df["sexo"].map(sidx)
    df["age_idx"] = df["age_band"].map(aidx)
    df["local_idx"] = df["local"].astype(int) - 1
    g = (df.groupby(["party_idx", "sex_idx", "age_idx", "local_idx"])
           .agg(n=("vote", "size"), y=("vote", "sum")).reset_index())
    return g


class ParamLayout:
    """Vector plano de parámetros con vistas nombradas y máscaras de celdas."""

    def __init__(self, data: ModelData):
        self.blocks = [("beta0", 1), ("beta_sex", 2),  # M, U (F referencia)
                       ("u_party", data.n_party), ("u_age", data.n_age),
                       ("u_local", data.n_local)]
        if data.local_covar is not None:
            self.blocks.append(("beta23", 1))
        self.slices, off = {}, 0
        for name, k in self.blocks:
            self.slices[name] = slice(off, off + k)
            off += k
        self.dim = off
        self.data = data
        # máscara de celdas afectadas por cada parámetro escalar
        self.masks = []
        for name, k in self.blocks:
            for j in range(k):
                if name == "beta0" or name == "beta23":
                    self.masks.append(slice(None))
                elif name == "beta_sex":
                    self.masks.append(np.where(data.isx == j + 1)[0])  # M=1, U=2
                elif name == "u_party":
                    self.masks.append(np.where(data.ip == j)[0])
                elif name == "u_age":
                    self.masks.append(np.where(data.ia == j)[0])
                elif name == "u_local":
                    self.masks.append(np.where(data.il == j)[0])

    def eta(self, x):
        d = self.data
        s = self.slices
        e = np.full(d.C, x[s["beta0"]][0])
        bs = x[s["beta_sex"]]
        e += np.where(d.isx == 1, bs[0], 0.0) + np.where(d.isx == 2, bs[1], 0.0)
        e += x[s["u_party"]][d.ip] + x[s["u_age"]][d.ia] + x[s["u_local"]][d.il]
        if d.local_covar is not None:
            e += x[s["beta23"]][0] * d.local_covar[d.il]
        return e

    def eta_delta_for(self, k):
        """(máscara, multiplicador por celda) del parámetro escalar k."""
        d = self.data
        # beta23 escala por covariable; el resto suma 1
        name = None
        for nm, kk in self.blocks:
            sl = self.slices[nm]
            if sl.start <= k < sl.stop:
                name = nm
                break
        if name == "beta23":
            return slice(None), d.local_covar[d.il]
        return self.masks[k], 1.0
