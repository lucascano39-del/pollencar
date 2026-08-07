"""Diagnósticos MCMC: split-R-hat y ESS bulk (numpy puro)."""

import numpy as np


def split_rhat(chains) -> float:
    """chains: lista de arrays 1D (draws por cadena, misma longitud)."""
    halves = []
    for c in chains:
        c = np.asarray(c, float)
        h = len(c) // 2
        if h < 2:
            return float("nan")
        halves += [c[:h], c[h : 2 * h]]
    m = len(halves)
    n = len(halves[0])
    means = np.array([h.mean() for h in halves])
    vars_ = np.array([h.var(ddof=1) for h in halves])
    W = vars_.mean()
    B = n * means.var(ddof=1)
    var_plus = (n - 1) / n * W + B / n
    return float(np.sqrt(var_plus / W)) if W > 0 else float("nan")


def ess_bulk(chains) -> float:
    """ESS con estimador de secuencia inicial monótona sobre cadenas combinadas."""
    chains = [np.asarray(c, float) for c in chains]
    m = len(chains)
    n = min(len(c) for c in chains)
    chains = [c[:n] for c in chains]
    mean_all = np.mean([c.mean() for c in chains])
    var_all = np.mean([c.var(ddof=0) for c in chains]) + np.var(
        [c.mean() for c in chains], ddof=0
    )
    if var_all == 0:
        return float(m * n)
    max_lag = min(n - 1, 500)
    rho = np.zeros(max_lag)
    for t in range(1, max_lag + 1):
        acov = np.mean([
            np.mean((c[:-t] - mean_all) * (c[t:] - mean_all)) for c in chains
        ])
        rho[t - 1] = acov / var_all
    # sumas por pares, cortando en el primer par negativo (Geyer)
    s = 0.0
    for t in range(0, max_lag - 1, 2):
        pair = rho[t] + rho[t + 1]
        if pair < 0:
            break
        s += pair
    tau = 1 + 2 * s
    return float(m * n / max(tau, 1e-9))


def summarize(chains_by_param: dict, rhat_max, ess_min) -> dict:
    out, ok = {}, True
    for name, chains in chains_by_param.items():
        r = split_rhat(chains)
        e = ess_bulk(chains)
        flat = np.concatenate(chains)
        out[name] = {
            "mean": float(flat.mean()), "sd": float(flat.std(ddof=1)),
            "q025": float(np.quantile(flat, 0.025)),
            "q975": float(np.quantile(flat, 0.975)),
            "rhat": r, "ess": e,
        }
        if not (np.isnan(r) or r < rhat_max) or e < ess_min:
            ok = False
    return {"params": out, "ok": ok}
