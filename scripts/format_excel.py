#!/usr/bin/env python3
"""Retoque visual del libro Excel de la encuesta, con garantía de cero cambios de datos.

Un .xlsx es un zip. Este script reescribe SOLO xl/styles.xml (definiciones de
fuente/relleno/borde) y atributos de vista de las 10 hojas (color de pestaña,
panel congelado, cuadrícula); las demás partes del paquete (gráficos, tablas,
tema, drawings, rels, sharedStrings) se copian byte a byte. Ninguna celda,
fórmula, valor cacheado, texto ni formato numérico se toca — por eso no hace
falta recalcular nada.

Cambios aplicados:
- Fuente Carlito -> Calibri (métricamente idéntica; se ve bien en Excel real).
- Paleta unificada al tema del libro: encabezados FF5B9BD5 -> FF156082 (mismo
  azul que las tablas; el blanco pasa de contraste 2.96:1 a 6.93:1), banda de
  info FFD9EAF7 -> FFDEEAF0, bordes FFB7C9D6 -> FF8FB0C6 y FFE6E6E6 -> FFD9D9D9.
- Color de pestaña por sección y panel congelado en las 10 hojas (título fijo;
  en 09_BASE_AUDITABLE queda fija la fila de encabezados sobre 4000 filas).
- Cuadrícula oculta también en la hoja 10 (consistente con las otras nueve).

La verificación integrada falla duro si algo más cambió: prueba de parche
inverso byte a byte, diff semántico por hoja (filas/celdas/fórmulas/valores/
merges), numFmts intactos y conteos de estilos sin variación.

Uso: python3 scripts/format_excel.py entrada.xlsx salida.xlsx
"""
import hashlib
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

ROOT_OPEN = '<x:worksheet xmlns:x="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'

# (token exacto original, token nuevo, apariciones esperadas) en xl/styles.xml
STYLE_REPLACES = [
    ('<x:name val="Carlito" />', '<x:name val="Calibri" />', 6),
    ('rgb="FFB7C9D6"', 'rgb="FF8FB0C6"', 20),
    ('rgb="FFE6E6E6"', 'rgb="FFD9D9D9"', 24),
    ('rgb="FF5B9BD5"', 'rgb="FF156082"', 1),
    ('rgb="FFD9EAF7"', 'rgb="FFDEEAF0"', 1),
]

# color de pestaña, sheetView original y sheetView nuevo (panel congelado) por hoja
SV_19 = '<x:sheetView showGridLines="0" workbookViewId="0" />'
SV_10 = '<x:sheetView showGridLines="1" workbookViewId="0" />'


def vista_congelada(ysplit, topleft):
    return (
        '<x:sheetView showGridLines="0" workbookViewId="0">'
        f'<x:pane ySplit="{ysplit}" topLeftCell="{topleft}" activePane="bottomLeft" state="frozen" />'
        f'<x:selection pane="bottomLeft" activeCell="{topleft}" sqref="{topleft}" />'
        '</x:sheetView>'
    )


SHEET_EDITS = {
    # hoja: (tabColor ARGB, sheetView viejo, sheetView nuevo)
    "xl/worksheets/sheet1.xml": ("FF1F4E78", SV_19, vista_congelada(2, "A3")),
    "xl/worksheets/sheet2.xml": ("FF156082", SV_19, vista_congelada(2, "A3")),
    "xl/worksheets/sheet3.xml": ("FF5088A1", SV_19, vista_congelada(2, "A3")),
    "xl/worksheets/sheet4.xml": ("FF5088A1", SV_19, vista_congelada(2, "A3")),
    "xl/worksheets/sheet5.xml": ("FF5088A1", SV_19, vista_congelada(2, "A3")),
    "xl/worksheets/sheet6.xml": ("FF5088A1", SV_19, vista_congelada(2, "A3")),
    "xl/worksheets/sheet7.xml": ("FF5088A1", SV_19, vista_congelada(2, "A3")),
    "xl/worksheets/sheet8.xml": ("FF5088A1", SV_19, vista_congelada(2, "A3")),
    "xl/worksheets/sheet9.xml": ("FF808080", SV_19, vista_congelada(2, "A3")),
    "xl/worksheets/sheet10.xml": ("FFA6A6A6", SV_10, vista_congelada(1, "A2")),
}


def fallo(msg):
    raise SystemExit(f"ERROR: {msg}")


def reemplazo_exacto(texto, viejo, nuevo, esperado, parte):
    n = texto.count(viejo)
    if n != esperado:
        fallo(f"{parte}: {viejo!r} aparece {n} veces, se esperaban {esperado}")
    if texto.count(nuevo):
        fallo(f"{parte}: el token nuevo {nuevo!r} ya existía; el parche no sería reversible")
    return texto.replace(viejo, nuevo)


def parchear_estilos(texto):
    for viejo, nuevo, esperado in STYLE_REPLACES:
        texto = reemplazo_exacto(texto, viejo, nuevo, esperado, "styles.xml")
    return texto


def parchear_hoja(nombre, texto):
    color, sv_viejo, sv_nuevo = SHEET_EDITS[nombre]
    sheet_pr = f'<x:sheetPr><x:tabColor rgb="{color}" /></x:sheetPr>'
    if texto.count(ROOT_OPEN) != 1:
        fallo(f"{nombre}: etiqueta raíz no encontrada una única vez")
    if "<x:sheetPr" in texto or "<x:pane" in texto or "<x:selection" in texto:
        fallo(f"{nombre}: ya tiene sheetPr/pane/selection; anclas no válidas")
    texto = texto.replace(ROOT_OPEN, ROOT_OPEN + sheet_pr)
    texto = reemplazo_exacto(texto, sv_viejo, sv_nuevo, 1, nombre)
    return texto


def despatchear(nombre, texto_nuevo):
    """Parche inverso: de los bytes nuevos debe salir el original exacto."""
    if nombre == "xl/styles.xml":
        for viejo, nuevo, _ in STYLE_REPLACES:
            texto_nuevo = texto_nuevo.replace(nuevo, viejo)
        return texto_nuevo
    color, sv_viejo, sv_nuevo = SHEET_EDITS[nombre]
    sheet_pr = f'<x:sheetPr><x:tabColor rgb="{color}" /></x:sheetPr>'
    texto_nuevo = texto_nuevo.replace(sheet_pr, "")
    return texto_nuevo.replace(sv_nuevo, sv_viejo)


def arbol_sin_vista(data):
    """Árbol de la hoja sin sheetPr/sheetViews: todo lo demás debe ser idéntico."""
    root = ET.fromstring(data)
    for tag in (f"{NS}sheetPr", f"{NS}sheetViews"):
        for el in root.findall(tag):
            root.remove(el)
    return ET.tostring(root)


def celdas(data):
    """Tuplas (ref, tipo, estilo, fórmula, valor) de cada celda, en orden."""
    root = ET.fromstring(data)
    out = []
    for c in root.iter(f"{NS}c"):
        f = c.find(f"{NS}f")
        v = c.find(f"{NS}v")
        out.append((c.get("r"), c.get("t"), c.get("s"),
                    None if f is None else f.text, None if v is None else v.text))
    return out


def bloque(texto, etiqueta):
    m = re.search(f"<x:{etiqueta}[ >].*?</x:{etiqueta}>", texto)
    return m.group(0) if m else None


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main(entrada, salida):
    zin = zipfile.ZipFile(entrada)
    tocadas = {"xl/styles.xml"} | set(SHEET_EDITS)
    originales = {i.filename: zin.read(i.filename) for i in zin.infolist()}
    if set(tocadas) - set(originales):
        fallo("faltan partes esperadas en el paquete")

    nuevas = {}
    for nombre in tocadas:
        texto = originales[nombre].decode("utf-8")
        texto = parchear_estilos(texto) if nombre == "xl/styles.xml" else parchear_hoja(nombre, texto)
        nuevas[nombre] = texto.encode("utf-8")

    with zipfile.ZipFile(salida, "w") as zout:
        for info in zin.infolist():
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zi.create_system = info.create_system
            zout.writestr(zi, nuevas.get(info.filename, originales[info.filename]))

    # ---- verificación ----
    zver = zipfile.ZipFile(salida)
    if zver.testzip() is not None:
        fallo("zip corrupto")
    if [i.filename for i in zver.infolist()] != [i.filename for i in zin.infolist()]:
        fallo("cambió el conjunto u orden de partes del paquete")

    intactas = celdas_comparadas = formulas = 0
    for nombre in (i.filename for i in zver.infolist()):
        data = zver.read(nombre)
        if nombre not in tocadas:
            if data != originales[nombre]:
                fallo(f"{nombre}: cambió sin estar en la lista de partes a tocar")
            intactas += 1
            continue
        ET.fromstring(data)  # bien formado
        if despatchear(nombre, data.decode("utf-8")).encode("utf-8") != originales[nombre]:
            fallo(f"{nombre}: el parche inverso no reproduce el original byte a byte")
        if nombre != "xl/styles.xml":
            if arbol_sin_vista(data) != arbol_sin_vista(originales[nombre]):
                fallo(f"{nombre}: difiere fuera de sheetPr/sheetViews")
            antes, despues = celdas(originales[nombre]), celdas(data)
            if antes != despues:
                fallo(f"{nombre}: alguna celda cambió")
            celdas_comparadas += len(despues)
            formulas += sum(1 for c in despues if c[3] is not None)

    est_orig = originales["xl/styles.xml"].decode("utf-8")
    est_nuevo = zver.read("xl/styles.xml").decode("utf-8")
    if bloque(est_orig, "numFmts") != bloque(est_nuevo, "numFmts"):
        fallo("styles.xml: cambió algún formato numérico")
    for etiqueta in ("fonts", "fills", "borders", "cellStyleXfs", "cellXfs", "cellStyles", "dxfs"):
        a, b = ET.fromstring(est_orig).find(f"{NS}{etiqueta}"), ET.fromstring(est_nuevo).find(f"{NS}{etiqueta}")
        if len(list(a)) != len(list(b)):
            fallo(f"styles.xml: cambió la cantidad de {etiqueta}")
    xfs = lambda t: [(x.attrib, [dict(h.attrib) for h in x]) for x in ET.fromstring(t).find(f"{NS}cellXfs")]
    if [x[0] for x in xfs(est_orig)] != [x[0] for x in xfs(est_nuevo)] or \
       [x[1] for x in xfs(est_orig)] != [x[1] for x in xfs(est_nuevo)]:
        fallo("styles.xml: cambió algún cellXf (formato/alineación de celda)")

    print("VERIFICACIÓN OK — cero cambios de datos")
    print(f"  partes copiadas byte a byte : {intactas}")
    print(f"  partes reescritas (estilo)  : {len(tocadas)} (styles.xml + 10 hojas)")
    print(f"  celdas comparadas idénticas : {celdas_comparadas} ({formulas} con fórmula, valores cacheados intactos)")
    print(f"  sha256 entrada : {sha256(open(entrada, 'rb').read())}")
    print(f"  sha256 salida  : {sha256(open(salida, 'rb').read())}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__.strip().splitlines()[-1])
    main(sys.argv[1], sys.argv[2])
