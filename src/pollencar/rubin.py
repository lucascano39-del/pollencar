"""Reglas de Rubin sobre el logit del share estimado.

La inferencia primaria es la mezcla de draws posteriores entre imputaciones;
esta tabla clásica se reporta para descomponer la incertidumbre: cuánta viene
del muestreo (W) y cuánta del enlace dudoso (B), vía la FMI.
"""

import numpy as np


def rubin_table(theta_draws_by_imp: list) -> dict:
    """theta_draws_by_imp: lista de arrays de draws posteriores de theta (0-1) por imputación."""
    M = len(theta_draws_by_imp)
    logit = [np.log(np.clip(d, 1e-9, 1 - 1e-9) / (1 - np.clip(d, 1e-9, 1 - 1e-9)))
             for d in theta_draws_by_imp]
    est = np.array([float(np.mean(l)) for l in logit])
    var = np.array([float(np.var(l, ddof=1)) for l in logit])
    qbar = float(est.mean())
    W = float(var.mean())
    B = float(est.var(ddof=1)) if M > 1 else 0.0
    T = W + (1 + 1 / M) * B
    # grados de libertad de Barnard-Rubin (com = inf -> forma clásica)
    if B > 0:
        r = (1 + 1 / M) * B / W if W > 0 else np.inf
        df = (M - 1) * (1 + 1 / r) ** 2 if np.isfinite(r) and r > 0 else np.inf
        fmi = ((1 + 1 / M) * B + 2 / (df + 3) * T) / T if np.isfinite(df) else (1 + 1 / M) * B / T
    else:
        df, fmi = np.inf, 0.0
    inv = lambda x: 1 / (1 + np.exp(-x))
    return {
        "M": M,
        "theta_hat": float(inv(qbar)),
        "W_within": W,
        "B_between": B,
        "T_total": T,
        "df": float(df) if np.isfinite(df) else None,
        "fmi": float(fmi),
        "ic95_logit": [qbar - 1.96 * T ** 0.5, qbar + 1.96 * T ** 0.5],
        "ic95": [float(inv(qbar - 1.96 * T ** 0.5)), float(inv(qbar + 1.96 * T ** 0.5))],
    }
