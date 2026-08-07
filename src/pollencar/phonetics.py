"""Clave fonética para castellano paraguayo.

Colapsa las confusiones ortográficas reales del español rioplatense/guaraní:
h muda, b=v, ll=y=i, c/qu/k, c(e,i)=z=s, g(e,i)=j=x, w=u, letras dobladas.
La ñ se mantiene distinta (Ñandutí ≠ Nanduti en guaraní).

Opera sobre tokens ya canonizados por normalize.canon (A-Z + Ñ).
"""

import re

_RULES = [
    (re.compile(r"H"), ""),          # h muda (HECTOR=ECTOR)
    (re.compile(r"V"), "B"),         # b=v
    (re.compile(r"LL"), "Y"),        # ll -> y ...
    (re.compile(r"Y"), "I"),         # ... y -> i  (VILLALBA ~ VIYALVA ~ VIIALBA)
    (re.compile(r"QU(?=[EI])"), "K"),
    (re.compile(r"C(?=[AOU])"), "K"),
    (re.compile(r"CK"), "K"),
    (re.compile(r"K"), "K"),
    (re.compile(r"C(?=[EI])"), "S"),
    (re.compile(r"Z"), "S"),
    (re.compile(r"C$"), "K"),        # C final (ISAAC)
    (re.compile(r"C"), "K"),         # C residual (CT, CR...)
    (re.compile(r"G(?=[EI])"), "J"),
    (re.compile(r"X"), "J"),
    (re.compile(r"GU(?=[EI])"), "G"),
    (re.compile(r"W"), "U"),
    (re.compile(r"PH"), "F"),
    (re.compile(r"TH"), "T"),
    (re.compile(r"(.)\1+"), r"\1"),  # dobles colapsadas
]


def phonetic_key(token: str) -> str:
    """Clave fonética paraguaya de un token canónico. '' si queda vacío."""
    t = token
    for rx, rep in _RULES:
        t = rx.sub(rep, t)
    return t
