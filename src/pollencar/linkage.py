"""Capa 2 — Enlace Fellegi-Sunter poll ↔ padrón.

Bloqueo por conjunción (apellido fonético ∧ nombre fonético/apodo) + bloque de
apellidos raros. Vector de comparación discreto, EM para m/u sobre patrones,
pesos por frecuencia de apellido/nombre en el acuerdo exacto, posterior a nivel
respondente con masa explícita de no-match. Tres zonas; los dudosos NUNCA se
fuerzan: quedan como set de candidatos para imputación múltiple.
"""

import csv
import math
import os
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from .phonetics import phonetic_key

N_FIELDS = 5  # gamma = (sur, giv, 2nd, sex, jw)
LEVELS = (3, 4, 3, 3, 4)  # niveles por campo (incluye NA como último nivel donde aplica)
NA_2ND, NA_SEX, NA_JW = 2, 2, 3  # índice del nivel NA de cada campo que lo tiene


def load_nicknames(path=None):
    path = path or os.path.join(os.path.dirname(__file__), "..", "..",
                                "lexicons", "nicknames.csv")
    nick = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cans = [c for c in row["canonicals"].split("|") if c]
            if cans:
                nick[row["nickname"].strip().upper()] = cans
    return nick


def jaro_winkler(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0
    n1, n2 = len(s1), len(s2)
    if not n1 or not n2:
        return 0.0
    window = max(n1, n2) // 2 - 1
    m1, m2 = [False] * n1, [False] * n2
    matches = 0
    for i, c in enumerate(s1):
        lo, hi = max(0, i - window), min(n2, i + window + 1)
        for j in range(lo, hi):
            if not m2[j] and s2[j] == c:
                m1[i] = m2[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    t = 0
    k = 0
    for i in range(n1):
        if m1[i]:
            while not m2[k]:
                k += 1
            if s1[i] != s2[k]:
                t += 1
            k += 1
    t //= 2
    jaro = (matches / n1 + matches / n2 + (matches - t) / matches) / 3
    prefix = 0
    for a, b in zip(s1, s2):
        if a != b or prefix == 4:
            break
        prefix += 1
    return jaro + prefix * 0.1 * (1 - jaro)


class RespFeatures:
    """Estructuras precomputadas por respondente para el loop de comparación."""

    __slots__ = ("toks", "phons", "exp_givens", "exp_phons", "sexo", "full")

    def __init__(self, toks, nicknames, sexo):
        self.toks = toks
        self.phons = [phonetic_key(t) for t in toks]
        exp = set()
        for t in toks:
            for c in nicknames.get(t, []):
                exp.add(c)
        self.exp_givens = exp
        self.exp_phons = {phonetic_key(c) for c in exp}
        self.sexo = sexo
        self.full = " ".join(toks)


def build_blocks(padron: pd.DataFrame, f_sur: dict, rare_thresh_n: int):
    """Índices de bloqueo sobre el padrón."""
    by_phon_sur = defaultdict(list)
    by_phon_giv = defaultdict(list)
    by_rare_sur = defaultdict(list)
    n = len(padron)
    sur1 = padron["sur1"].to_numpy()
    sur2 = padron["sur2"].to_numpy()
    ph_s1 = padron["ph_sur1"].to_numpy()
    ph_s2 = padron["ph_sur2"].to_numpy()
    ph_g1 = padron["ph_giv1"].to_numpy()
    ph_g2 = padron["ph_giv2"].to_numpy()
    for i in range(n):
        if ph_s1[i]:
            by_phon_sur[ph_s1[i]].append(i)
        if ph_s2[i] and ph_s2[i] != ph_s1[i]:
            by_phon_sur[ph_s2[i]].append(i)
        if ph_g1[i]:
            by_phon_giv[ph_g1[i]].append(i)
        if ph_g2[i] and ph_g2[i] != ph_g1[i]:
            by_phon_giv[ph_g2[i]].append(i)
        for s, f in ((sur1[i], f_sur.get(sur1[i], 0)), (sur2[i], f_sur.get(sur2[i], 0))):
            if s and 0 < f * n < rare_thresh_n:
                by_rare_sur[s].append(i)
    return by_phon_sur, by_phon_giv, by_rare_sur


def candidate_pairs(feat: RespFeatures, blocks) -> set:
    """Bloqueo por conjunción: (apellido fonético ∧ nombre fonético) ∪ apellido raro."""
    by_phon_sur, by_phon_giv, by_rare_sur = blocks
    sur_side, giv_side = set(), set()
    for ph in feat.phons:
        sur_side.update(by_phon_sur.get(ph, ()))
        giv_side.update(by_phon_giv.get(ph, ()))
    for ph in feat.exp_phons:
        giv_side.update(by_phon_giv.get(ph, ()))
    cands = sur_side & giv_side
    for t in feat.toks:
        cands.update(by_rare_sur.get(t, ()))
    if len(feat.toks) == 1:
        # un solo token: candidato = cualquiera que lo tenga como nombre o apellido
        cands = sur_side | giv_side
    return cands


class PadronArrays:
    """Vista columnar del padrón para el loop de comparación."""

    def __init__(self, padron: pd.DataFrame):
        self.sur1 = padron["sur1"].to_numpy()
        self.sur2 = padron["sur2"].to_numpy()
        self.giv1 = padron["giv1"].to_numpy()
        self.giv2 = padron["giv2"].to_numpy()
        self.ph_sur1 = padron["ph_sur1"].to_numpy()
        self.ph_sur2 = padron["ph_sur2"].to_numpy()
        self.ph_giv1 = padron["ph_giv1"].to_numpy()
        self.ph_giv2 = padron["ph_giv2"].to_numpy()
        self.sexo = padron["sexo"].to_numpy()
        self.full = (padron["giv1"] + " " + padron["sur1"]).to_numpy()


def compare(feat: RespFeatures, pa: PadronArrays, j: int, jw_bins):
    """Vector gamma del par (respondente, registro j) + valores para pesos por frecuencia."""
    toks, phons = feat.toks, feat.phons
    tokset = set(toks)
    phonset = set(phons)

    # --- apellido ---
    g_sur, sur_val = 0, None
    for s in (pa.sur1[j], pa.sur2[j]):
        if s and s in tokset:
            g_sur, sur_val = 2, s
            break
    if g_sur == 0:
        for ps, s in ((pa.ph_sur1[j], pa.sur1[j]), (pa.ph_sur2[j], pa.sur2[j])):
            if ps and ps in phonset:
                g_sur, sur_val = 1, s
                break

    # --- nombre ---
    g_giv, giv_val = 0, None
    for g in (pa.giv1[j], pa.giv2[j]):
        if g and g in tokset:
            g_giv, giv_val = 3, g
            break
    if g_giv == 0:
        for g in (pa.giv1[j], pa.giv2[j]):
            if g and g in feat.exp_givens:
                g_giv, giv_val = 2, g
                break
    if g_giv == 0:
        for pg, g in ((pa.ph_giv1[j], pa.giv1[j]), (pa.ph_giv2[j], pa.giv2[j])):
            if pg and (pg in phonset or pg in feat.exp_phons):
                g_giv, giv_val = 1, g
                break

    # --- tercer acuerdo (2do apellido / 2do nombre por token distinto) ---
    pad_fields = [f for f in (pa.ph_sur1[j], pa.ph_sur2[j], pa.ph_giv1[j], pa.ph_giv2[j]) if f]
    if len(phons) < 3 or len(pad_fields) < 3:
        g_2nd = NA_2ND
    else:
        matched_fields = set()
        used_toks = set()
        for ph in phons:
            for fi, f in enumerate(pad_fields):
                if fi not in matched_fields and f == ph and ph not in used_toks:
                    matched_fields.add(fi)
                    used_toks.add(ph)
                    break
        g_2nd = 1 if len(matched_fields) >= 3 else 0

    # --- sexo ---
    if feat.sexo == "U" or pa.sexo[j] == "U":
        g_sex = NA_SEX
    else:
        g_sex = 1 if feat.sexo == pa.sexo[j] else 0

    # --- Jaro-Winkler (solo si hay señal mínima; si no, bin bajo) ---
    if g_sur >= 1 and g_giv >= 1:
        jw = jaro_winkler(feat.full, pa.full[j])
        g_jw = 2 if jw >= jw_bins[1] else (1 if jw >= jw_bins[0] else 0)
    else:
        g_jw = NA_JW

    return (g_sur, g_giv, g_2nd, g_sex, g_jw), sur_val, giv_val


def em_mu(pattern_counts: Counter, cfg):
    """EM de mezcla 2 clases (M/U) con independencia condicional entre campos."""
    patterns = np.array(list(pattern_counts.keys()), dtype=int)  # (P, 5)
    counts = np.array(list(pattern_counts.values()), dtype=float)
    P = len(patterns)
    total = counts.sum()

    m = [np.array(v) for v in
         ([0.03, 0.20, 0.77], [0.05, 0.60, 0.15, 0.20], [0.30, 0.40, 0.30],
          [0.04, 0.66, 0.30], [0.05, 0.15, 0.70, 0.10])]
    u = []
    for f in range(N_FIELDS):
        emp = np.bincount(patterns[:, f], weights=counts, minlength=LEVELS[f]) / total
        u.append(np.clip(emp, 1e-4, None) / np.clip(emp, 1e-4, None).sum())
    p = cfg["linkage"]["prevalence_init"]

    ll_old = -np.inf
    for _ in range(cfg["linkage"]["em_max_iter"]):
        log_m = np.zeros(P)
        log_u = np.zeros(P)
        for f in range(N_FIELDS):
            log_m += np.log(np.clip(m[f][patterns[:, f]], 1e-12, None))
            log_u += np.log(np.clip(u[f][patterns[:, f]], 1e-12, None))
        num = np.log(p) + log_m
        den = np.logaddexp(num, np.log1p(-p) + log_u)
        g = np.exp(num - den)  # P(M | patrón)
        ll = float((counts * den).sum())

        wm = counts * g
        wu = counts * (1 - g)
        for f in range(N_FIELDS):
            mm = np.bincount(patterns[:, f], weights=wm, minlength=LEVELS[f])
            uu = np.bincount(patterns[:, f], weights=wu, minlength=LEVELS[f])
            m[f] = np.clip(mm / max(wm.sum(), 1e-12), 1e-6, None)
            m[f] /= m[f].sum()
            u[f] = np.clip(uu / max(wu.sum(), 1e-12), 1e-6, None)
            u[f] /= u[f].sum()
        p = float(np.clip(wm.sum() / total, 1e-7, 0.5))
        if abs(ll - ll_old) < cfg["linkage"]["em_tol"]:
            break
        ll_old = ll
    return m, u, p


class Linker:
    def __init__(self, padron, freqs, cfg, nicknames=None):
        self.padron = padron
        self.freqs = freqs  # dict de frequency_tables(): f_sur, f_giv, f_ph_*, f_sex
        self.cfg = cfg
        self.nicknames = nicknames if nicknames is not None else load_nicknames()
        self.pa = PadronArrays(padron)
        self.blocks = build_blocks(padron, freqs["f_sur"],
                                   cfg["linkage"]["rare_surname_freq"])
        self.N = len(padron)

    def features(self, resp_df):
        return {
            int(r.resp_id): RespFeatures(list(r.toks), self.nicknames, r.sexo_fb)
            for r in resp_df.itertuples()
        }

    def compare_all(self, feats):
        """Pares bloqueados + vectores gamma. Devuelve dict resp -> [(j, gamma, sur_val, giv_val)]."""
        jw_bins = self.cfg["linkage"]["jw_bins"]
        out = {}
        pattern_counts = Counter()
        for rid, feat in feats.items():
            cands = candidate_pairs(feat, self.blocks)
            if len(cands) > 20000:  # nombre hiperfrecuente con 1 token: cap defensivo
                cands = set(list(cands)[:20000])
            rows = []
            for j in cands:
                gamma, sur_val, giv_val = compare(feat, self.pa, j, jw_bins)
                rows.append((j, gamma, sur_val, giv_val))
                pattern_counts[gamma] += 1
            out[rid] = rows
        return out, pattern_counts

    def fit_em(self, pattern_counts):
        """EM de patrones — SOLO diagnóstico. Con bloqueo por conjunción casi
        todos los pares acuerdan en apellido y nombre, el patrón no discrimina
        y el EM degenera hacia clusters espurios; el score usa m fijos + u por
        frecuencia de valor (FS clásico). Se reporta igual para transparencia."""
        self.m, self.u, self.p_pair = em_mu(pattern_counts, self.cfg)
        return self.m, self.u, self.p_pair

    def _pair_llr(self, feat, gamma, sur_val, giv_val):
        """log LR del par: m fijos documentados (config), u por frecuencia.

        u = probabilidad de acuerdo POR COINCIDENCIA con un no-match:
        exacto -> share del valor en el padrón; fonético -> share de la clave
        fonética; apodo -> share de los canónicos expandibles; sexo -> share
        del sexo del respondente en el padrón.
        """
        cfgL = self.cfg["linkage"]
        mp, lrf = cfgL["m_probs"], cfgL["lr_fixed"]
        fN = 1.0 / self.N
        fq = self.freqs
        llr = 0.0

        g = gamma[0]  # apellido: 0 dis / 1 fon / 2 exacto
        m = max(mp["sur"][g], 1e-9)
        if g == 2:
            u = max(fq["f_sur"].get(sur_val, fN), fN)
        elif g == 1:
            ph = phonetic_key(sur_val) if sur_val else ""
            u = max(fq["f_ph_sur"].get(ph, fN) - fq["f_sur"].get(sur_val, 0.0), fN)
        else:
            u = 0.98
        llr += math.log(m) - math.log(u)

        g = gamma[1]  # nombre: 0 dis / 1 fon / 2 apodo / 3 exacto
        m = max(mp["giv"][g], 1e-9)
        if g == 3:
            u = max(fq["f_giv"].get(giv_val, fN), fN)
        elif g == 2:
            u = max(sum(fq["f_giv"].get(c, 0.0) for c in feat.exp_givens), fN)
        elif g == 1:
            ph = phonetic_key(giv_val) if giv_val else ""
            u = max(fq["f_ph_giv"].get(ph, fN), fN)
        else:
            u = 0.95
        llr += math.log(m) - math.log(u)

        g = gamma[2]  # tercer acuerdo
        if g == 1:
            llr += math.log(lrf["2nd_present"])
        elif g == 0:
            llr += math.log(lrf["2nd_absent"])

        g = gamma[3]  # sexo
        if g != NA_SEX:
            m = mp["sex"][g]
            f_same = max(fq["f_sex"].get(feat.sexo, 0.5), 0.05)
            u = f_same if g == 1 else max(1.0 - f_same - fq["f_sex"].get("U", 0.0), 0.05)
            llr += math.log(max(m, 1e-9)) - math.log(u)

        llr += math.log(lrf["jw"][gamma[4]])
        return llr

    def classify(self, feats, compared, lam_init=0.6, keep_top=30):
        """Posterior por respondente con masa de no-match; zonas; sin forzar dudosos."""
        cfg = self.cfg["linkage"]
        mp = cfg["m_probs"]
        # LR piso para los pares NO enumerados (desacuerdan en apellido y nombre
        # fonéticos). Sus u globales son ~1, así que LR ~ m_sur0 * m_giv0.
        lr_floor = min(max(mp["sur"][0], 1e-12) * max(mp["giv"][0], 1e-12), 1.0)

        pair_lrs = {}
        for rid, rows in compared.items():
            feat = feats[rid]
            lrs = [(j, math.exp(min(self._pair_llr(feat, g, sv, gv), 60.0)))
                   for j, g, sv, gv in rows]
            pair_lrs[rid] = lrs

        lo, hi = cfg["lambda_bounds"]
        lam = lam_init
        for _ in range(30):  # punto fijo para lambda (share de respondentes en-marco)
            mass = []
            for rid, lrs in pair_lrs.items():
                s = sum(lr for _, lr in lrs)
                K = len(lrs)
                z = (1 - lam) + (lam / self.N) * (s + (self.N - K) * lr_floor)
                mass.append(1 - (1 - lam) / z)
            new_lam = float(np.clip(np.mean(mass) if mass else lam, lo, hi))
            if abs(new_lam - lam) < 1e-4:
                break
            lam = new_lam
        self.lam = lam

        results = {}
        for rid, lrs in pair_lrs.items():
            s = sum(lr for _, lr in lrs)
            K = len(lrs)
            z = (1 - lam) + (lam / self.N) * (s + (self.N - K) * lr_floor)
            q0 = (1 - lam) / z + (lam / self.N) * (self.N - K) * lr_floor / z
            cand = sorted(((j, (lam / self.N) * lr / z) for j, lr in lrs),
                          key=lambda t: -t[1])[:keep_top]
            match_mass = sum(q for _, q in cand)
            q1 = cand[0][1] if cand else 0.0
            q2 = cand[1][1] if len(cand) > 1 else 0.0
            if q1 >= cfg["auto_link_posterior"] and (q2 == 0 or q1 / max(q2, 1e-12) >= 10):
                zone = "auto"
            elif match_mass < cfg["nonlink_posterior_max"]:
                zone = "nonlink"
            else:
                zone = "ambiguous"
            results[rid] = {"zone": zone, "q0": q0, "cands": cand}

        # conflicto: dos auto-links a la misma cédula -> ambos a ambiguo
        by_top = defaultdict(list)
        for rid, r in results.items():
            if r["zone"] == "auto":
                by_top[r["cands"][0][0]].append(rid)
        for j, rids in by_top.items():
            if len(rids) > 1:
                for rid in rids:
                    results[rid]["zone"] = "ambiguous"

        # enlace "a celda": candidatos todos en la misma celda de post-estratificación
        cell_of = (self.padron["party_group"] + "|" + self.padron["sexo"] + "|"
                   + self.padron["age_band"] + "|" + self.padron["mesa"].astype(str)).to_numpy()
        for rid, r in results.items():
            if r["zone"] == "ambiguous" and r["cands"] and r["q0"] < 0.05:
                cells = {cell_of[j] for j, q in r["cands"] if q > 0.01 * r["cands"][0][1]}
                r["cell_link"] = len(cells) == 1
            else:
                r["cell_link"] = False
        return results
