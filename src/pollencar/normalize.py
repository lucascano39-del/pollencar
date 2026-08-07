"""Canonicalización de nombres: FB display names y padrón a un mismo espacio.

La `ñ` se preserva como letra distinta (guaraní/castellano paraguayo); todo
otro diacrítico o letra "leet" ("Käřïňä") colapsa a su base ASCII vía NFKD y,
si sobrevive algo no-ASCII, vía el nombre Unicode del carácter.
"""

import re
import unicodedata

_NH = ""  # centinela para ñ

_HONORIFICS = {
    "DR", "DRA", "ING", "LIC", "ABG", "ABOG", "PROF", "MG", "MSC", "ESC",
    "OBSTETRA", "PASTOR", "PASTORA", "PADRE", "HERMANA", "DON", "DOÑA",
    "SR", "SRA", "SRTA", "MTRO", "MTRA",
}

# partículas que no son ni nombre ni apellido "fuerte" pero forman apellidos
PARTICLES = {"DE", "DEL", "LA", "LAS", "LOS", "DA", "DO", "DOS", "DI", "VDA", "Y", "SAN", "SANTA"}


def _fold_char(ch: str) -> str:
    """Colapsa un carácter no-ASCII a su letra base usando el nombre Unicode."""
    name = unicodedata.name(ch, "")
    m = re.match(r"LATIN (?:SMALL|CAPITAL) LETTER ([A-Z])\b", name)
    if m:
        return m.group(1)
    return " "


def canon(s: str) -> str:
    """'Käřïňä Äřïyü' -> 'KARINA ARIYU'; preserva Ñ; mayúsculas; sin puntuación."""
    if not s:
        return ""
    s = s.replace("ñ", _NH).replace("Ñ", _NH)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper()
    out = []
    for ch in s:
        if ch == _NH:
            out.append("Ñ")
        elif "A" <= ch <= "Z" or ch == " ":
            out.append(ch)
        elif ch in "'’´`-.,":
            out.append(" ")
        elif ord(ch) > 127:
            out.append(_fold_char(ch))
        else:
            out.append(" ")
    return re.sub(r"\s+", " ", "".join(out)).strip()


def tokens(s: str, drop_honorifics: bool = True) -> list:
    """Tokeniza un nombre canónico; opcionalmente saca honoríficos al inicio."""
    toks = canon(s).split()
    if drop_honorifics:
        while toks and toks[0] in _HONORIFICS:
            toks = toks[1:]
        toks = [t for t in toks if t not in _HONORIFICS]
    return toks


def strong_tokens(toks: list) -> list:
    """Tokens sin partículas (DE, DEL, VDA...) — los que portan información."""
    return [t for t in toks if t not in PARTICLES and len(t) >= 2]


def split_padron_name(apellido_nombre: str):
    """'ACEVEDO ALTAMIRANO, FRANCO' -> (['ACEVEDO','ALTAMIRANO'], ['FRANCO'])."""
    if "," in apellido_nombre:
        sur, giv = apellido_nombre.split(",", 1)
    else:
        sur, giv = apellido_nombre, ""
    return strong_tokens(tokens(sur, drop_honorifics=False)), strong_tokens(
        tokens(giv, drop_honorifics=False)
    )
