"""Inferencia de sexo desde el nombre de pila.

Mismo diccionario y misma función para padrón y poll (requisito de simetría:
si el clasificador se equivoca, se equivoca igual en ambos lados y el término
de sexo del modelo sigue bien definido).
"""

import csv
import os

_LEXICON = None


def _load(lexicon_path=None):
    global _LEXICON
    if _LEXICON is not None and lexicon_path is None:
        return _LEXICON
    path = lexicon_path or os.path.join(
        os.path.dirname(__file__), "..", "..", "lexicons", "given_name_sex.csv"
    )
    lex = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lex[row["name"].strip().upper()] = row["sex"].strip().upper()
    _LEXICON = lex
    return lex


def infer_sex(given_tokens, lexicon_path=None) -> str:
    """M/F/U desde el primer token de nombre de pila.

    Regla: primer token manda (JOSE MARIA -> M, MARIA JOSE -> F).
    Fallback morfológico solo para tokens largos ausentes del léxico.
    """
    lex = _load(lexicon_path)
    if not given_tokens:
        return "U"
    t = given_tokens[0].upper()
    if t in lex:
        return lex[t] or "U"
    if len(t) > 3:
        if t.endswith("A"):
            return "F"
        if t.endswith(("O", "OS")):
            return "M"
    return "U"
