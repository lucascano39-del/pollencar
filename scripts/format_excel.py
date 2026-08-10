#!/usr/bin/env python3
"""Rediseño visual del libro Excel de la encuesta, con garantía de cero cambios de datos.

Un .xlsx es un zip. Este script reescribe SOLO xl/styles.xml y las 10 hojas, y
únicamente en su capa de presentación; las demás partes del paquete (gráficos,
tablas nativas, tema, drawings, rels, sharedStrings) se copian byte a byte.
Ninguna celda cambia de valor, fórmula, valor cacheado, texto ni formato
numérico — la verificación integrada lo prueba celda por celda y falla duro
ante cualquier desvío.

Cambios aplicados:
- Fuente Carlito -> Calibri (métricamente idéntica; se ve bien en Excel real).
- Paleta unificada al tema del libro: encabezados FF5B9BD5 -> FF156082 (mismo
  azul que las tablas nativas), banda de info FFD9EAF7 -> FFDEEAF0, bordes
  FFB7C9D6 -> FF8FB0C6 y FFE6E6E6 -> FFD9D9D9.
- Grilla dibujada: cada celda de las tablas armadas a mano recibe borde
  completo; filas de datos cebradas (blanco / FFE9F1F6) por paridad de fila;
  centrado vertical; filas sin texto envuelto pasan de 15 a 19 pt de alto.
  Las tablas nativas de Excel (ListObjects con TableStyleMedium2) ya traen
  bandas propias y quedan tal cual.
- Color de pestaña por sección y panel congelado en las 10 hojas (título fijo;
  en 09_BASE_AUDITABLE queda fija la fila de encabezados sobre 4000 filas).
- Cuadrícula oculta también en la hoja 10 (consistente con las otras nueve).

Los estilos nuevos se AGREGAN al final de styles.xml: los 191 formatos de celda
originales quedan byte a byte en su lugar, así ninguna celda no tocada puede
cambiar de aspecto. Para cada celda retocada se preserva formato numérico,
fuente y alineación (solo se permite agregar centrado vertical).

Uso: python3 scripts/format_excel.py entrada.xlsx salida.xlsx
"""
import hashlib
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

ROOT_OPEN = '<x:worksheet xmlns:x="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'

# ---------------- capa 1: definiciones de estilo (tokens exactos) ----------------

STYLE_REPLACES = [
    ('<x:name val="Carlito" />', '<x:name val="Calibri" />', 6),
    ('rgb="FFB7C9D6"', 'rgb="FF8FB0C6"', 20),
    ('rgb="FFE6E6E6"', 'rgb="FFD9D9D9"', 24),
    ('rgb="FF5B9BD5"', 'rgb="FF156082"', 1),
    ('rgb="FFD9EAF7"', 'rgb="FFDEEAF0"', 1),
]

ZEBRA = "FFE9F1F6"      # banda alterna de las filas de datos
GRID = "FFC5D3DC"       # borde de la grilla de datos
HDR_SEP = "FF0E4A61"    # separador entre celdas de encabezado (más oscuro que el relleno)

# ---------------- capa 2: vista por hoja ----------------

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

# ---------------- capa 3: grilla + cebrado por familias de estilo ----------------

# familias de los 191 cellXfs originales (inventariadas del propio archivo)
HDR_IDS = set(range(1, 15)) | {62, 63}                    # encabezados sobre azul
FICHA_IDS = {92, 93, 94, 95, 96}                          # bloques etiqueta/valor
DATA_IDS = set(range(15, 54)) | set(range(125, 167))      # datos con borde de pelo
# el resto (título, subtítulo, cajas de nota gris/amarilla/azul) queda intacto

# rangos de ListObjects en hojas de contenido: su TableStyleMedium2 ya banda
SKIP_RECTS = {
    "xl/worksheets/sheet1.xml": [("A", 11, "C", 16)],     # tblGuiaAgosto
    "xl/worksheets/sheet9.xml": [("A", 33, "D", 42)],     # tblTrazaEntradas
}

# hojas que reciben grilla/cebrado (la 10 ya es una tabla nativa gigante)
GRID_SHEETS = [f"xl/worksheets/sheet{n}.xml" for n in range(1, 10)]

ROW_HT = "19"           # alto de las filas de tabla sin texto envuelto (antes 15)

CELL_RE = re.compile(r"<x:c\b[^>]*/>|<x:c\b[^>]*>.*?</x:c>")
ROW_OPEN_RE = re.compile(r'<x:row\b[^>]*>')


def fallo(msg):
    raise SystemExit(f"ERROR: {msg}")


def reemplazo_exacto(texto, viejo, nuevo, esperado, parte):
    n = texto.count(viejo)
    if n != esperado:
        fallo(f"{parte}: {viejo!r} aparece {n} veces, se esperaban {esperado}")
    if texto.count(nuevo):
        fallo(f"{parte}: el token nuevo {nuevo!r} ya existía en la parte")
    return texto.replace(viejo, nuevo)


def col_a_num(letras):
    n = 0
    for ch in letras:
        n = n * 26 + ord(ch) - 64
    return n


def en_rect(rects, col, fila):
    return any(col_a_num(c1) <= col <= col_a_num(c2) and f1 <= fila <= f2
               for c1, f1, c2, f2 in rects)


def bloque(texto, etiqueta):
    m = re.search(f"<x:{etiqueta}[ >].*?</x:{etiqueta}>", texto)
    return m.group(0) if m else None


def sub_chunks(bloque_xml, tag):
    return re.findall(f"<x:{tag}\\b[^>]*/>|<x:{tag}\\b[^>]*>.*?</x:{tag}>", bloque_xml)


def patch_count(texto, etiqueta, nuevo_n):
    return re.sub(f'(<x:{etiqueta} count=")\\d+(")', f"\\g<1>{nuevo_n}\\g<2>", texto, count=1)


def set_attr(tag_xf, attr, val):
    """Fija attr="val" en el tag raíz de un chunk xf, agregándolo si falta."""
    if re.search(f'{attr}="[^"]*"', tag_xf):
        return re.sub(f'{attr}="[^"]*"', f'{attr}="{val}"', tag_xf, count=1)
    return re.sub("( ?/?>)", f' {attr}="{val}"\\1', tag_xf, count=1)


def xf_derivado(chunk, border_id, fill_id=None):
    """Copia de un xf original con borde/relleno nuevos y centrado vertical."""
    m = re.match(r"<x:xf\b[^>]*?(/>|>)", chunk)
    tag, resto = chunk[:m.end()], chunk[m.end():]
    autocerrado = m.group(1) == "/>"
    tag = set_attr(tag, "borderId", str(border_id))
    tag = set_attr(tag, "applyBorder", "1")
    if fill_id is not None:
        tag = set_attr(tag, "fillId", str(fill_id))
        tag = set_attr(tag, "applyFill", "1")
    tag = set_attr(tag, "applyAlignment", "1")
    if autocerrado:
        return tag[:-2].rstrip() + '><x:alignment vertical="center" /></x:xf>'
    if "<x:alignment" in resto:
        if "vertical=" not in resto:
            resto = resto.replace("<x:alignment", '<x:alignment vertical="center"', 1)
        return tag + resto
    return tag + '<x:alignment vertical="center" />' + resto


def wraps_de_estilos(estilos_xml):
    """ids de cellXfs originales cuyo texto se envuelve (wrapText)."""
    root = ET.fromstring(estilos_xml)
    out = set()
    for i, xf in enumerate(root.find(f"{NS}cellXfs")):
        al = xf.find(f"{NS}alignment")
        if al is not None and al.get("wrapText") == "1":
            out.add(i)
    return out


def parchear_estilos(texto):
    """Capa 1 (recolor de definiciones) + estilos nuevos anexados al final.

    Devuelve (texto nuevo, mapa (s_original, variante) -> s_nuevo).
    """
    for viejo, nuevo, esperado in STYLE_REPLACES:
        texto = reemplazo_exacto(texto, viejo, nuevo, esperado, "styles.xml")

    fills = bloque(texto, "fills")
    borders = bloque(texto, "borders")
    cellxfs = bloque(texto, "cellXfs")
    xfs = sub_chunks(cellxfs, "xf")
    if len(xfs) != 191:
        fallo(f"styles.xml: se esperaban 191 cellXfs, hay {len(xfs)}")

    # relleno cebra: plantilla del gris F2F2F2 (mismo formato del generador)
    plantilla_fill = next(c for c in sub_chunks(fills, "fill") if "FFF2F2F2" in c)
    fill_zebra = plantilla_fill.replace("FFF2F2F2", ZEBRA)
    id_zebra = len(sub_chunks(fills, "fill"))
    texto = texto.replace(fills, patch_count(fills.replace("</x:fills>", fill_zebra + "</x:fills>"), "fills", id_zebra + 1), 1)

    # bordes de 4 lados: plantilla del borde 8 (único original con los 4 lados)
    plantilla_borde = sub_chunks(borders, "border")[8]
    if plantilla_borde.count("FFD9D9D9") != 4:
        fallo("styles.xml: el borde plantilla no tiene 4 lados")
    id_grid = len(sub_chunks(borders, "border"))
    id_hdr = id_grid + 1
    nuevos_bordes = plantilla_borde.replace("FFD9D9D9", GRID) + plantilla_borde.replace("FFD9D9D9", HDR_SEP)
    texto = texto.replace(borders, patch_count(borders.replace("</x:borders>", nuevos_bordes + "</x:borders>"), "borders", id_hdr + 1), 1)

    # cellXfs derivados: encabezado (borde oscuro) y datos (grilla, par/impar)
    mapa, anexos = {}, []
    def alta(s, variante, chunk):
        mapa[(s, variante)] = 191 + len(anexos)
        anexos.append(chunk)
    for s in sorted(HDR_IDS):
        alta(s, "hdr", xf_derivado(xfs[s], id_hdr))
    for s in sorted(DATA_IDS | FICHA_IDS | {0}):
        alta(s, "impar", xf_derivado(xfs[s], id_grid, fill_id=0))
        alta(s, "par", xf_derivado(xfs[s], id_grid, fill_id=id_zebra))
    cellxfs_nuevo = patch_count(cellxfs.replace("</x:cellXfs>", "".join(anexos) + "</x:cellXfs>"), "cellXfs", 191 + len(anexos))
    texto = texto.replace(cellxfs, cellxfs_nuevo, 1)
    return texto, mapa


def parchear_hoja(nombre, texto, mapa, wraps):
    """Vista (pestaña+panel) y, en hojas 1-9, grilla/cebrado/altos de fila."""
    color, sv_viejo, sv_nuevo = SHEET_EDITS[nombre]
    if texto.count(ROOT_OPEN) != 1:
        fallo(f"{nombre}: etiqueta raíz no encontrada una única vez")
    if "<x:sheetPr" in texto or "<x:pane" in texto or "<x:selection" in texto:
        fallo(f"{nombre}: ya tiene sheetPr/pane/selection; anclas no válidas")
    texto = texto.replace(ROOT_OPEN, ROOT_OPEN + f'<x:sheetPr><x:tabColor rgb="{color}" /></x:sheetPr>')
    texto = reemplazo_exacto(texto, sv_viejo, sv_nuevo, 1, nombre)
    if nombre not in GRID_SHEETS:
        return texto, 0, 0

    rects = SKIP_RECTS.get(nombre, [])
    filas_tratadas, filas_con_wrap = set(), set()
    tocadas = 0

    def celda(m):
        nonlocal tocadas
        cell = m.group(0)
        head = cell[:cell.index(">") + 1]
        mr = re.search(r'r="([A-Z]+)(\d+)"', head)
        col, fila = col_a_num(mr.group(1)), int(mr.group(2))
        ms = re.search(r' s="(\d+)"', head)
        s = int(ms.group(1)) if ms else 0
        if s in wraps:
            filas_con_wrap.add(fila)
        if en_rect(rects, col, fila):
            return cell
        if s in HDR_IDS:
            variante = "hdr"
        elif s in DATA_IDS or s in FICHA_IDS or (s == 0 and "<x:v>" in cell):
            variante = "par" if fila % 2 == 0 else "impar"
        else:
            return cell
        nuevo_s = mapa[(s, variante)]
        head_nuevo = (head.replace(ms.group(0), f' s="{nuevo_s}"', 1) if ms
                      else head.replace(mr.group(0), mr.group(0) + f' s="{nuevo_s}"', 1))
        tocadas += 1
        filas_tratadas.add(fila)
        return head_nuevo + cell[len(head):]

    texto = CELL_RE.sub(celda, texto)

    objetivo = filas_tratadas - filas_con_wrap
    elevadas = 0

    def fila_alta(m):
        nonlocal elevadas
        tag = m.group(0)
        mr = re.search(r'r="(\d+)"', tag)
        if mr and int(mr.group(1)) in objetivo and " ht=" not in tag:
            elevadas += 1
            return tag.replace(mr.group(0), mr.group(0) + f' ht="{ROW_HT}" customHeight="1"', 1)
        return tag

    texto = ROW_OPEN_RE.sub(fila_alta, texto)
    return texto, tocadas, elevadas


# ---------------- verificación ----------------

def celdas(data):
    """Tuplas (ref, tipo, fórmula, valor) — la sustancia que no puede cambiar."""
    root = ET.fromstring(data)
    out = []
    for c in root.iter(f"{NS}c"):
        f = c.find(f"{NS}f")
        v = c.find(f"{NS}v")
        out.append((c.get("r"), c.get("t"),
                    None if f is None else f.text, None if v is None else v.text))
    return out


def normalizar(data):
    """Árbol sin capa de presentación: debe ser idéntico antes y después."""
    root = ET.fromstring(data)
    for tag in (f"{NS}sheetPr", f"{NS}sheetViews"):
        for el in root.findall(tag):
            root.remove(el)
    for row in root.iter(f"{NS}row"):
        row.attrib.pop("ht", None)
        row.attrib.pop("customHeight", None)
    for c in root.iter(f"{NS}c"):
        c.attrib.pop("s", None)
    return ET.tostring(root)


def indice_xfs(estilos_xml):
    out = []
    for xf in ET.fromstring(estilos_xml).find(f"{NS}cellXfs"):
        al = xf.find(f"{NS}alignment")
        out.append((dict(xf.attrib), None if al is None else dict(al.attrib)))
    return out


def verificar(zin, zver, originales, tocadas, mapa):
    if zver.testzip() is not None:
        fallo("zip corrupto")
    if [i.filename for i in zver.infolist()] != [i.filename for i in zin.infolist()]:
        fallo("cambió el conjunto u orden de partes del paquete")

    est_orig = originales["xl/styles.xml"].decode("utf-8")
    est_nuevo = zver.read("xl/styles.xml").decode("utf-8")
    xfs_orig, xfs_nuevo = indice_xfs(est_orig), indice_xfs(est_nuevo)
    if xfs_nuevo[:191] != xfs_orig:
        fallo("styles.xml: algún cellXf original cambió (debían quedar intactos)")
    if bloque(est_orig, "numFmts") != bloque(est_nuevo, "numFmts"):
        fallo("styles.xml: cambió algún formato numérico")
    if len(sub_chunks(bloque(est_nuevo, "fonts"), "font")) != 6:
        fallo("styles.xml: cambió la cantidad de fuentes")

    numfmt = lambda xfs, i: xfs[i][0].get("numFmtId", "0")
    fuente = lambda xfs, i: xfs[i][0].get("fontId", "0")

    intactas = celdas_cmp = formulas = restyled = 0
    for nombre in (i.filename for i in zver.infolist()):
        data = zver.read(nombre)
        if nombre not in tocadas:
            if data != originales[nombre]:
                fallo(f"{nombre}: cambió sin estar en la lista de partes a tocar")
            intactas += 1
            continue
        ET.fromstring(data)
        if nombre == "xl/styles.xml":
            continue
        if normalizar(data) != normalizar(originales[nombre]):
            fallo(f"{nombre}: difiere fuera de la capa de presentación")
        antes, despues = celdas(originales[nombre]), celdas(data)
        if antes != despues:
            fallo(f"{nombre}: alguna celda cambió de valor/tipo/fórmula")
        celdas_cmp += len(despues)
        formulas += sum(1 for c in despues if c[2] is not None)

        # cada celda re-estilada preserva formato numérico, fuente y alineación
        viejos = {c.get("r"): int(c.get("s", "0")) for c in ET.fromstring(originales[nombre]).iter(f"{NS}c")}
        for c in ET.fromstring(data).iter(f"{NS}c"):
            s_v, s_n = viejos[c.get("r")], int(c.get("s", "0"))
            if s_v == s_n:
                continue
            if s_n < 191 or s_n not in dict.fromkeys(mapa.values()):
                fallo(f"{nombre}!{c.get('r')}: estilo nuevo fuera del mapa aprobado")
            if numfmt(xfs_nuevo, s_n) != numfmt(xfs_orig, s_v):
                fallo(f"{nombre}!{c.get('r')}: cambió el formato numérico")
            if fuente(xfs_nuevo, s_n) != fuente(xfs_orig, s_v):
                fallo(f"{nombre}!{c.get('r')}: cambió la fuente")
            al_v, al_n = xfs_orig[s_v][1] or {}, xfs_nuevo[s_n][1] or {}
            if {k: v for k, v in al_n.items() if k != "vertical"} != {k: v for k, v in al_v.items() if k != "vertical"}:
                fallo(f"{nombre}!{c.get('r')}: cambió la alineación (más que el centrado vertical)")
            restyled += 1

    return intactas, celdas_cmp, formulas, restyled


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main(entrada, salida):
    zin = zipfile.ZipFile(entrada)
    tocadas = {"xl/styles.xml"} | set(SHEET_EDITS)
    originales = {i.filename: zin.read(i.filename) for i in zin.infolist()}
    if set(tocadas) - set(originales):
        fallo("faltan partes esperadas en el paquete")

    est_nuevo, mapa = parchear_estilos(originales["xl/styles.xml"].decode("utf-8"))
    wraps = wraps_de_estilos(originales["xl/styles.xml"].decode("utf-8"))
    nuevas = {"xl/styles.xml": est_nuevo.encode("utf-8")}
    stats = {}
    for nombre in SHEET_EDITS:
        texto, tocadas_n, elevadas = parchear_hoja(nombre, originales[nombre].decode("utf-8"), mapa, wraps)
        nuevas[nombre] = texto.encode("utf-8")
        stats[nombre] = (tocadas_n, elevadas)

    with zipfile.ZipFile(salida, "w") as zout:
        for info in zin.infolist():
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zi.create_system = info.create_system
            zout.writestr(zi, nuevas.get(info.filename, originales[info.filename]))

    zver = zipfile.ZipFile(salida)
    intactas, celdas_cmp, formulas, restyled = verificar(zin, zver, originales, tocadas, mapa)

    print("VERIFICACIÓN OK — cero cambios de datos")
    print(f"  partes copiadas byte a byte : {intactas}")
    print(f"  partes reescritas (estilo)  : {len(tocadas)} (styles.xml + 10 hojas)")
    print(f"  celdas comparadas idénticas : {celdas_cmp} ({formulas} con fórmula, valores cacheados intactos)")
    print(f"  celdas con grilla/cebrado   : {restyled}")
    for nombre in GRID_SHEETS:
        t, e = stats[nombre]
        print(f"    {nombre.split('/')[-1]:<12} celdas={t:<4} filas elevadas={e}")
    print(f"  sha256 entrada : {sha256(entrada)}")
    print(f"  sha256 salida  : {sha256(salida)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__.strip().splitlines()[-1])
    main(sys.argv[1], sys.argv[2])
