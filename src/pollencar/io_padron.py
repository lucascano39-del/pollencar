"""Capa 1b — Padrón definitivo TSJE (xlsx) → DataFrame tipado + tablas de frecuencia.

Lector primario: openpyxl read-only. Fallback: stdlib (zipfile + ElementTree),
por si openpyxl no está disponible en el entorno de re-corrida.
"""

import re
import zipfile
from xml.etree import ElementTree as ET

import pandas as pd

from .normalize import split_padron_name
from .phonetics import phonetic_key
from .sexo import infer_sex

_EXPECTED_COLS = ["mesa", "orden", "cedula", "apellido_nombre", "fec_nac",
                  "partido", "edad", "tipo_voto", "tipo_inscrip"]


def _rows_stdlib(path):
    z = zipfile.ZipFile(path)
    strings = []
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    for si in ET.fromstring(z.read("xl/sharedStrings.xml")):
        strings.append("".join(t.text or "" for t in si.iter(ns + "t")))
    with z.open("xl/worksheets/sheet1.xml") as f:
        for _, el in ET.iterparse(f):
            if el.tag == ns + "row":
                d = {}
                for c in el.findall(ns + "c"):
                    v = c.find(ns + "v")
                    col = re.match(r"[A-Z]+", c.get("r", "?")).group(0)
                    val = v.text if v is not None else ""
                    if c.get("t") == "s" and val != "":
                        val = strings[int(val)]
                    d[col] = val
                yield [d.get(chr(ord("A") + i), "") for i in range(9)]
                el.clear()


def _rows_openpyxl(path):
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    for row in ws.iter_rows(values_only=True):
        yield [("" if v is None else str(v)) for v in (list(row) + [""] * 9)[:9]]


def load_padron(path, cfg, engine="openpyxl") -> pd.DataFrame:
    reader = _rows_openpyxl if engine == "openpyxl" else _rows_stdlib
    recs = []
    for vals in reader(path):
        if not str(vals[0]).isdigit():
            continue  # encabezados / títulos
        recs.append(vals)
    df = pd.DataFrame(recs, columns=_EXPECTED_COLS)
    df["mesa"] = df["mesa"].astype(int)
    df["edad"] = pd.to_numeric(df["edad"], errors="coerce").fillna(0).astype(int)
    df["cedula"] = df["cedula"].astype(str)

    parsed = df["apellido_nombre"].map(split_padron_name)
    df["surnames"] = parsed.map(lambda p: p[0])
    df["givens"] = parsed.map(lambda p: p[1])
    df["sur1"] = df["surnames"].map(lambda t: t[0] if t else "")
    df["sur2"] = df["surnames"].map(lambda t: t[1] if len(t) > 1 else "")
    df["giv1"] = df["givens"].map(lambda t: t[0] if t else "")
    df["giv2"] = df["givens"].map(lambda t: t[1] if len(t) > 1 else "")
    for c in ["sur1", "sur2", "giv1", "giv2"]:
        df["ph_" + c] = df[c].map(phonetic_key)

    df["sexo"] = df["givens"].map(infer_sex)
    df["party_group"] = df["partido"].map(party_group)
    df["age_band"] = df["edad"].map(lambda a: age_band(a, cfg))
    return df


def party_group(partido: str) -> str:
    """Colapsa la afiliación cruda a 5 grupos analíticos."""
    if not partido or not str(partido).strip():
        return "SIN_AFILIACION"
    parts = set(str(partido).split("-"))
    anr, plra = "ANR" in parts, "PLRA" in parts
    if anr and plra:
        return "ANR-PLRA"
    if anr:
        return "ANR"
    if plra:
        return "PLRA"
    return "OTRO"


def age_band(edad: int, cfg) -> str:
    for lo, hi in cfg["poststrat"]["age_bands"]:
        if lo <= edad <= hi:
            return f"{lo}-{hi}" if hi < 100 else f"{lo}+"
    return "18-29"  # menores de 18 en padrón (cumplen 18 al comicio): banda joven


def frequency_tables(df: pd.DataFrame):
    """Frecuencias relativas (exactas y fonéticas) para los pesos FS por valor.

    f_*[valor] ~ P(una persona del padrón al azar porte ese valor) — el u de
    "acuerdo por coincidencia" del Fellegi-Sunter clásico.
    """
    n = len(df)
    out = {}
    for kind, cols in (("sur", ["sur1", "sur2"]), ("giv", ["giv1", "giv2"])):
        vals = pd.concat([df[c] for c in cols])
        vals = vals[vals != ""]
        out["f_" + kind] = (vals.value_counts() / n).to_dict()
        ph = pd.concat([df["ph_" + c] for c in cols])
        ph = ph[ph != ""]
        out["f_ph_" + kind] = (ph.value_counts() / n).to_dict()
    out["f_sex"] = df["sexo"].value_counts(normalize=True).to_dict()
    return out


def validate_padron(df: pd.DataFrame):
    """Asserts de sanidad contra los marginales conocidos del archivo real."""
    checks = []
    checks.append(("filas", len(df)))
    pg = df["party_group"].value_counts(normalize=True)
    checks.append(("ANR_share", round(float(pg.get("ANR", 0)), 4)))
    checks.append(("SIN_AFILIACION_share", round(float(pg.get("SIN_AFILIACION", 0)), 4)))
    checks.append(("sexo_no_U", round(float((df["sexo"] != "U").mean()), 4)))
    checks.append(("locales", int(df["mesa"].nunique())))
    return dict(checks)
