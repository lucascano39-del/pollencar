"""Sampler MCMC en numpy puro: Metropolis-within-Gibbs adaptativo.

- sigma2 de cada bloque de RE: Gibbs exacto (conjugado InvGamma).
- beta / u escalares: random-walk Metropolis adaptativo (Roberts-Rosenthal,
  aceptación objetivo 0.44, adaptación diminishing congelada tras el burn-in).
- eta (logits por celda) se mantiene cacheado y se actualiza incrementalmente
  con la máscara de celdas de cada parámetro: costo por update ~ celdas tocadas.
"""

import numpy as np

from .model import ModelData, ParamLayout


def _cell_loglik(y, n, eta):
    # binomial log-lik sin constante; estable vía log1p(exp)
    return y * eta - n * np.logaddexp(0.0, eta)


class MwG:
    def __init__(self, data: ModelData, cfg_model, seed):
        self.d = data
        self.lay = ParamLayout(data)
        self.cfg = cfg_model
        self.rng = np.random.default_rng(seed)
        # bloques de RE presentes en el layout; ola/página llevan prior más chico
        self.re_blocks = [n for n, _ in self.lay.blocks if n.startswith("u_")]
        self.s2_prior = {}
        for n in self.re_blocks:
            p = (cfg_model["sigma2_prior_small"]
                 if n in ("u_wave", "u_page") else cfg_model["sigma2_prior"])
            self.s2_prior[n] = (p["a"], p["b"])
        # nombre de bloque por índice escalar (para prior_sd)
        self.block_of = {}
        for n, _k in self.lay.blocks:
            sl = self.lay.slices[n]
            for k in range(sl.start, sl.stop):
                self.block_of[k] = n

    def _prior_sd(self, k, s2):
        name = self.block_of[k]
        if name == "beta0":
            return self.cfg["beta0_sd"]
        if name in ("beta_sex", "beta23"):
            return self.cfg["beta_sd"]
        return np.sqrt(s2[name])

    def run(self, iters, burnin, thin=4):
        d, lay, rng = self.d, self.lay, self.rng
        x = rng.normal(0.0, 0.3, lay.dim)  # arranque sobredisperso por cadena
        s2 = {n: 0.25 for n in self.re_blocks}
        eta = lay.eta(x)
        cll = _cell_loglik(d.y, d.n, eta)
        log_step = np.full(lay.dim, np.log(0.3))
        acc = np.zeros(lay.dim)
        tries = np.zeros(lay.dim)
        draws = []
        target = self.cfg["target_accept"]

        for it in range(iters):
            for k in range(lay.dim):
                mask, mult = lay.eta_delta_for(k)
                step = np.exp(log_step[k])
                prop = rng.normal(0.0, step)
                eta_new = eta[mask] + prop * (mult if np.isscalar(mult) else mult[mask] if not isinstance(mask, slice) else mult)
                cll_new = _cell_loglik(d.y[mask], d.n[mask], eta_new)
                sd = self._prior_sd(k, s2)
                lp_old = -0.5 * (x[k] / sd) ** 2
                lp_new = -0.5 * ((x[k] + prop) / sd) ** 2
                dll = float(cll_new.sum() - cll[mask].sum()) + lp_new - lp_old
                tries[k] += 1
                if np.log(rng.random()) < dll:
                    x[k] += prop
                    eta[mask] = eta_new
                    cll[mask] = cll_new
                    acc[k] += 1
                # adaptación diminishing (solo durante burn-in)
                if it < burnin:
                    rate = acc[k] / tries[k]
                    log_step[k] += (rate - target) / np.sqrt(1 + it)

            # movimiento de traslación: beta0+delta, u_bloque-delta (eta invariante,
            # se acepta solo por priors) — decorrela beta0 de las medias de los RE
            for name in self.re_blocks:
                sl = lay.slices[name]
                u = x[sl]
                delta = rng.normal(0.0, 0.15)
                b0_old, b0_new = x[0], x[0] + delta
                sd_b0 = self.cfg["beta0_sd"]
                sd_u = np.sqrt(s2[name])
                lp = (-0.5 * (b0_new / sd_b0) ** 2 + 0.5 * (b0_old / sd_b0) ** 2
                      - 0.5 * (((u - delta) / sd_u) ** 2).sum()
                      + 0.5 * ((u / sd_u) ** 2).sum())
                if np.log(rng.random()) < lp:
                    x[0] = b0_new
                    x[sl] = u - delta

            # Gibbs exacto para las varianzas
            for name in self.re_blocks:
                u = x[lay.slices[name]]
                a0, b0 = self.s2_prior[name]
                a_post = a0 + len(u) / 2
                b_post = b0 + float((u ** 2).sum()) / 2
                s2[name] = b_post / rng.gamma(a_post, 1.0)

            if it >= burnin and (it - burnin) % thin == 0:
                draws.append((x.copy(), dict(s2)))

        return draws, {"accept_rate": (acc / np.maximum(tries, 1)).tolist()}


def run_chains(data: ModelData, cfg_model, base_seed, n_chains=None):
    n_chains = n_chains or cfg_model["chains"]
    all_draws, infos = [], []
    for ch in range(n_chains):
        s = MwG(data, cfg_model, base_seed + ch)
        draws, info = s.run(cfg_model["iters"], cfg_model["burnin"])
        all_draws.append(draws)
        infos.append(info)
    return all_draws, infos
