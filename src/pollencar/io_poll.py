"""Capa 1a — Parser de la captura del poll de Facebook + filtro no-persona.

Formato esperado (export de la UI de FB):
    <nombre candidato>
    NN% · N.NNN votos
    <un display name por línea>
    ...
    <nombre candidato 2>
    ...
"""

import csv
import re

import pandas as pd

from .normalize import canon, strong_tokens, tokens

_VOTES_RX = re.compile(r"^\s*(\d{1,3})\s*%\s*·\s*([\d.,]+)\s*votos?\s*$", re.I)


def parse_capture(path) -> tuple:
    """Devuelve (candidatos, respondents_df). Falla ruidosamente si el formato drifteó."""
    lines = [l.rstrip("\n") for l in open(path, encoding="utf-8")]
    headers = []  # (línea, candidato, pct, votos_declarados)
    for i, l in enumerate(lines):
        m = _VOTES_RX.match(l)
        if m and i > 0 and lines[i - 1].strip():
            votes = int(re.sub(r"[.,]", "", m.group(2)))
            headers.append((i, lines[i - 1].strip(), int(m.group(1)), votes))
    if len(headers) < 2:
        raise ValueError(
            f"Parser: esperaba >=2 bloques candidato, encontré {len(headers)}. "
            "¿Cambió el formato de la captura?"
        )
    rows = []
    for k, (i, cand, pct, votes) in enumerate(headers):
        end = headers[k + 1][0] - 1 if k + 1 < len(headers) else len(lines)
        names = [l.strip() for l in lines[i + 1 : end] if l.strip()]
        if not (0.85 * votes <= len(names) <= 1.02 * votes + 5):
            raise ValueError(
                f"Parser: candidato '{cand}' declara {votes} votos pero hay "
                f"{len(names)} nombres visibles — fuera de tolerancia."
            )
        for j, nm in enumerate(names):
            rows.append({"candidate": cand, "display_name_raw": nm,
                         "line_no": i + 1 + j + 1})
    df = pd.DataFrame(rows)
    df.insert(0, "resp_id", range(len(df)))
    cands = [{"candidate": c, "pct_declared": p, "votes_declared": v}
             for _, c, p, v in headers]
    return cands, df


def load_page_lexicon(path):
    exact, regexes = {}, []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["type"] == "exact":
                exact[canon(row["pattern"])] = row["reason"]
            else:
                regexes.append((re.compile(row["pattern"], re.I), row["reason"]))
    return exact, regexes


def flag_non_persons(df, lexicon_path, plausible_givens) -> pd.DataFrame:
    """Marca páginas/comercios/cuentas político-institucionales.

    plausible_givens: vocabulario de nombres de pila (léxico de sexo ∪ apodos
    ∪ padrón) para la heurística "ningún token parece nombre de persona".
    Los regexes corren sobre el nombre CRUDO además del canónico: canon()
    elimina dígitos y puntuación, que es justo lo que patrones como el de
    años de campaña ("Fulano 2026") o "S.R.L" necesitan ver.
    """
    exact, regexes = load_page_lexicon(lexicon_path)
    reasons = []
    for nm in df["display_name_raw"]:
        cn = canon(nm)
        toks = strong_tokens(tokens(nm))
        reason = ""
        if cn in exact:
            reason = f"lexicon:{exact[cn]}"
        else:
            for rx, why in regexes:
                if rx.search(cn) or rx.search(nm):
                    reason = f"regex:{why}"
                    break
        if not reason and toks:
            if len(toks) > 5:
                reason = "heuristica:demasiados_tokens"
            elif not any(t in plausible_givens for t in toks):
                reason = "heuristica:sin_nombre_pila"
        if not reason and not toks:
            reason = "heuristica:vacio"
        reasons.append(reason)
    out = df.copy()
    out["non_person_reason"] = reasons
    out["is_person"] = out["non_person_reason"] == ""
    return out


def prepare_respondents(df) -> pd.DataFrame:
    """Tokeniza y agrega columnas de trabajo a los respondentes persona."""
    out = df.copy()
    out["toks"] = out["display_name_raw"].map(lambda s: strong_tokens(tokens(s)))
    out["n_toks"] = out["toks"].map(len)
    out["norm_name"] = out["toks"].map(" ".join)
    return out
