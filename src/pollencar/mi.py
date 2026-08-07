"""Capa 2b — Imputación múltiple sobre los enlaces dudosos.

Por imputación m: los auto-links reclaman su cédula; cada dudoso sortea entre
sus candidatos + no-match según sus probabilidades posteriores, SIN reemplazo
de cédulas dentro de la imputación (dos respondentes no pueden ser el mismo
elector). El no-match excluye al respondente del dataset de esa imputación.
"""

import numpy as np


def draw_imputation(results: dict, rng: np.random.Generator) -> dict:
    """dict resp_id -> pad_idx (int) o None (no-match) para una imputación."""
    taken = set()
    assign = {}
    # 1) auto-links primero (deterministas; los conflictos ya fueron degradados)
    for rid, r in results.items():
        if r["zone"] == "auto":
            j = r["cands"][0][0]
            assign[rid] = j
            taken.add(j)
    # 2) dudosos en orden aleatorio
    amb = [rid for rid, r in results.items() if r["zone"] == "ambiguous"]
    rng.shuffle(amb)
    for rid in amb:
        r = results[rid]
        opts = [(j, q) for j, q in r["cands"] if j not in taken]
        w = np.array([q for _, q in opts] + [r["q0"]], dtype=float)
        if w.sum() <= 0:
            assign[rid] = None
            continue
        w = w / w.sum()
        k = int(rng.choice(len(w), p=w))
        if k == len(opts):
            assign[rid] = None
        else:
            j = opts[k][0]
            assign[rid] = j
            taken.add(j)
    # 3) no-links
    for rid, r in results.items():
        if r["zone"] == "nonlink":
            assign[rid] = None
    return assign


def build_imputations(results: dict, M: int, seed: int) -> list:
    return [draw_imputation(results, np.random.default_rng(seed + 7919 * m))
            for m in range(M)]
