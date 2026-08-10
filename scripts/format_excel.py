#!/usr/bin/env python3
"""Rediseño visual sobrio del libro PRELIMINAR, con garantía de cero cambios de contenido.

Un .xlsx es un zip. Este script reescribe SOLO xl/styles.xml y las 10 hojas, y
únicamente en su capa de presentación; el resto del paquete (calcChain,
sharedStrings, gráficos, drawings, tema, tablas nativas, rels, docProps) se
copia byte a byte. Ninguna celda cambia de valor, texto, fórmula ni formato
numérico, y no se mueve ni agrega ninguna celda — la verificación integrada lo
prueba y falla duro ante cualquier desvío.

Identidad "ficha técnica" (referencia del usuario): bandas carbón/pizarra en
lugar del semáforo (título FF1F4E78→FF1F2430, encabezados FF5B9BD5→FF263340,
verde FF70AD47→pizarra, ámbar FFFFC000→ámbar pálido con tipografía oscura),
paneles blancos enmarcados en la portada 00, Carlito→Calibri en todo el libro,
grilla completa + cebra sobria en las tablas de las hojas 01–08, pestañas en
rampa monocroma, paneles congelados en las 10 hojas y cuadrícula oculta.

Los colores del formato condicional (dxfs) se conservan: los swaps de FFE2F0D9,
FFFFF2CC y FF375623 se limitan a los bloques <fills>/<fonts>. Los 157 formatos
de celda originales quedan intactos en su posición; todo lo nuevo se anexa al
final de cada bloque.

Uso: python3 scripts/format_excel.py entrada.xlsx salida.xlsx
"""
import hashlib
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# ---------------- capa 1: styles.xml ----------------

# swaps globales (token exacto, apariciones esperadas verificadas)
SWAPS_GLOBALES = [
    ('val="Carlito"', 'val="Calibri"', 7),
    ('rgb="FFB7C9D6"', 'rgb="FF9AA7B0"', 20),
    ('rgb="FFE6E6E6"', 'rgb="FFD5DBE0"', 24),
    ('rgb="FF5B9BD5"', 'rgb="FF263340"', 1),
    ('rgb="FF1F4E78"', 'rgb="FF1F2430"', 2),   # banda de título + fuente 26pt
    ('rgb="FFD9EAF7"', 'rgb="FFF4F6F8"', 1),
    ('rgb="FF70AD47"', 'rgb="FF263340"', 1),
    ('rgb="FFFFC000"', 'rgb="FFFCF3DC"', 1),
    ('rgb="FFEDF5FB"', 'rgb="FFFFFFFF"', 1),
    ('rgb="FFF2F2F2"', 'rgb="FFFFFFFF"', 1),
]
# swaps limitados a un bloque (los dxfs del formato condicional no se tocan)
SWAPS_FILLS = [('rgb="FFE2F0D9"', 'rgb="FFF3F7F0"', 1), ('rgb="FFFFF2CC"', 'rgb="FFFBF6EC"', 1)]
SWAPS_FONTS = [('rgb="FF375623"', 'rgb="FF3D4852"', 1)]

ZEBRA = "FFF2F4F6"        # banda alterna de filas de datos
GRID = "FFBFC9D0"         # grilla de las tablas
HDR_SEP = "FF1A2530"      # separador entre celdas de encabezado
FIX_AMBAR = "FF6B5518"    # texto del encabezado "Qué falta completar" (antes blanco)

N_XFS = 157
XF_HDR = {1, 2, 3}        # encabezados de tabla (blanco negrita sobre pizarra)
XF_PENDIENTE = 112        # blanco sobre ámbar: quedaría 1.1:1 al aclarar el ámbar

# ---------------- capa 2: vistas ----------------

TABS = {1: "FF1F2430", 2: "FF263340", 3: "FF5A6B78", 4: "FF5A6B78", 5: "FF5A6B78",
        6: "FF5A6B78", 7: "FF5A6B78", 8: "FF5A6B78", 9: "FF8A959E", 10: "FFA6ADB4"}


def pane(ysplit, topleft):
    return (f'<pane ySplit="{ysplit}" topLeftCell="{topleft}" activePane="bottomLeft" state="frozen"/>'
            f'<selection pane="bottomLeft" activeCell="{topleft}" sqref="{topleft}"/>')


SV_1 = '<sheetView showGridLines="0" tabSelected="1" workbookViewId="0"><selection sqref="A1:J1"/></sheetView>'
# orden CT_SheetView: pane primero, después las selection (la original se conserva)
SV_1_NUEVO = ('<sheetView showGridLines="0" tabSelected="1" workbookViewId="0">'
              '<pane ySplit="3" topLeftCell="A4" activePane="bottomLeft" state="frozen"/>'
              '<selection sqref="A1:J1"/>'
              '<selection pane="bottomLeft" activeCell="A4" sqref="A4"/>'
              '</sheetView>')
SV_29 = '<sheetView showGridLines="0" workbookViewId="0"/>'
SV_10 = '<sheetView workbookViewId="0"/>'

SHEET_VIEWS = {1: (SV_1, SV_1_NUEVO)}
for _n in range(2, 10):
    SHEET_VIEWS[_n] = (SV_29, '<sheetView showGridLines="0" workbookViewId="0">' + pane(2, "A3") + '</sheetView>')
SHEET_VIEWS[10] = (SV_10, '<sheetView showGridLines="0" workbookViewId="0">' + pane(1, "A2") + '</sheetView>')

# ---------------- capa 4: regiones de tabla (hojas 2-9) ----------------
# Rectángulos "col1 fila1 col2 fila2" fijados a partir del volcado del libro.
# Dentro: encabezados (xfs 1/2/3) con separador oscuro; el resto grilla + cebra.
# Quedan fuera: cajas de nota/prosa (xfs 122-156), chips de sección (85) y el
# ListObject tblTrazaEntradas (hoja 9, A33:D42), que ya banda solo.

REGIONES = {
    2: ["A5:H9", "J4:L6", "A24:H29"],
    3: ["A5:F13"],
    4: ["A5:M9", "A13:D17"],
    5: ["A5:J9", "A13:D19", "A23:C27"],
    6: ["A5:D13", "A17:D20", "A24:E28", "A31:D34"],
    7: ["A5:G9", "A13:F21", "A25:F35", "A39:E46"],
    8: ["A5:F12", "A17:F24", "A28:D31", "A35:D38"],
    9: ["A5:J11", "A23:D29", "A60:C67"],
}

CELL_RE = re.compile(r"<c\b[^>]*/>|<c\b[^>]*>.*?</c>")
ROW_OPEN_RE = re.compile(r"<row\b[^>]*>")


def fallo(msg):
    raise SystemExit(f"ERROR: {msg}")


def reemplazo_exacto(texto, viejo, nuevo, esperado, parte):
    n = texto.count(viejo)
    if n != esperado:
        fallo(f"{parte}: {viejo!r} aparece {n} veces, se esperaban {esperado}")
    return texto.replace(viejo, nuevo)


def col_a_num(letras):
    n = 0
    for ch in letras:
        n = n * 26 + ord(ch) - 64
    return n


def parse_rect(rect):
    (c1, f1), (c2, f2) = (re.match(r"([A-Z]+)(\d+)", p).groups() for p in rect.split(":"))
    return col_a_num(c1), int(f1), col_a_num(c2), int(f2)


def bloque(texto, etiqueta):
    m = re.search(f"<{etiqueta}[ >].*?</{etiqueta}>", texto)
    return m.group(0) if m else None


def sub_chunks(bloque_xml, tag):
    return re.findall(f"<{tag}\\b[^>]*/>|<{tag}\\b[^>]*>.*?</{tag}>", bloque_xml)


def patch_count(texto, etiqueta, nuevo_n):
    return re.sub(f'(<{etiqueta} count=")\\d+(")', f"\\g<1>{nuevo_n}\\g<2>", texto, count=1)


def swap_en_bloque(texto, etiqueta, swaps):
    blk = bloque(texto, etiqueta)
    nuevo = blk
    for viejo, nvo, esperado in swaps:
        nuevo = reemplazo_exacto(nuevo, viejo, nvo, esperado, f"styles.xml/<{etiqueta}>")
    return texto.replace(blk, nuevo, 1)


def set_attr(tag_xf, attr, val):
    if re.search(f'{attr}="[^"]*"', tag_xf):
        return re.sub(f'{attr}="[^"]*"', f'{attr}="{val}"', tag_xf, count=1)
    return re.sub("( ?/?>)$", f' {attr}="{val}"\\1', tag_xf, count=1)


def xf_derivado(chunk, border_id, fill_id=None, font_id=None):
    """Copia de un xf original con borde/relleno/fuente nuevos y centrado vertical."""
    m = re.match(r"<xf\b[^>]*?(/>|>)", chunk)
    tag, resto = chunk[:m.end()], chunk[m.end():]
    autocerrado = m.group(1) == "/>"
    tag = set_attr(tag, "borderId", str(border_id))
    tag = set_attr(tag, "applyBorder", "1")
    if fill_id is not None:
        tag = set_attr(tag, "fillId", str(fill_id))
        tag = set_attr(tag, "applyFill", "1")
    if font_id is not None:
        tag = set_attr(tag, "fontId", str(font_id))
        tag = set_attr(tag, "applyFont", "1")
    tag = set_attr(tag, "applyAlignment", "1")
    if autocerrado:
        return re.sub(" ?/>$", '><alignment vertical="center"/></xf>', tag)
    if "<alignment" in resto:
        if "vertical=" not in resto:
            resto = resto.replace("<alignment", '<alignment vertical="center"', 1)
        return tag + resto
    return tag + '<alignment vertical="center"/>' + resto


def wraps_de_estilos(estilos_xml):
    out = set()
    for i, xf in enumerate(ET.fromstring(estilos_xml).find(f"{NS}cellXfs")):
        al = xf.find(f"{NS}alignment")
        if al is not None and al.get("wrapText") == "1":
            out.add(i)
    return out


def parchear_estilos(texto):
    """Swaps + anexos. Devuelve (texto, mapa (xf_origen, variante) -> xf_nuevo)."""
    # ningún color/nombre nuevo puede preexistir (FFFFFFFF sí existe: fuentes blancas)
    for token in ("Calibri", "FF9AA7B0", "FFD5DBE0", "FF263340", "FF1F2430", "FFF4F6F8",
                  "FFFCF3DC", "FF3D4852", "FFF3F7F0", "FFFBF6EC", ZEBRA, GRID, HDR_SEP, FIX_AMBAR):
        if token in texto:
            fallo(f"styles.xml: el token nuevo {token!r} ya existía en el original")
    for viejo, nuevo, esperado in SWAPS_GLOBALES:
        texto = reemplazo_exacto(texto, viejo, nuevo, esperado, "styles.xml")
    texto = swap_en_bloque(texto, "fills", SWAPS_FILLS)
    texto = swap_en_bloque(texto, "fonts", SWAPS_FONTS)

    fonts = bloque(texto, "fonts")
    fills = bloque(texto, "fills")
    borders = bloque(texto, "borders")
    cellxfs = bloque(texto, "cellXfs")
    xfs = sub_chunks(cellxfs, "xf")
    if len(xfs) != N_XFS:
        fallo(f"styles.xml: se esperaban {N_XFS} cellXfs, hay {len(xfs)}")

    # fuente nueva: la del encabezado pendiente (negrita 11 blanca -> ámbar oscuro)
    plantilla_font = next(c for c in sub_chunks(fonts, "font") if 'rgb="FFFFFFFF"' in c and '<sz val="11"' in c)
    id_font_ambar = len(sub_chunks(fonts, "font"))
    texto = texto.replace(fonts, patch_count(
        fonts.replace("</fonts>", plantilla_font.replace("FFFFFFFF", FIX_AMBAR) + "</fonts>"),
        "fonts", id_font_ambar + 1), 1)

    # relleno cebra (plantilla: cualquier solid; el generador usa fgColor+bgColor)
    plantilla_fill = next(c for c in sub_chunks(fills, "fill") if 'rgb="FF263340"' in c)
    id_zebra = len(sub_chunks(fills, "fill"))
    texto = texto.replace(fills, patch_count(
        fills.replace("</fills>", plantilla_fill.replace("FF263340", ZEBRA) + "</fills>"),
        "fills", id_zebra + 1), 1)

    # bordes de 4 lados: plantilla del borde 8 (único original con los 4 lados)
    plantilla_borde = sub_chunks(borders, "border")[8]
    if plantilla_borde.count("FFD5DBE0") != 4:
        fallo("styles.xml: el borde plantilla no tiene 4 lados")
    id_grid = len(sub_chunks(borders, "border"))
    id_hdr = id_grid + 1
    texto = texto.replace(borders, patch_count(
        borders.replace("</borders>", plantilla_borde.replace("FFD5DBE0", GRID)
                        + plantilla_borde.replace("FFD5DBE0", HDR_SEP) + "</borders>"),
        "borders", id_hdr + 1), 1)

    # cellXfs derivados, siempre anexados (los 157 originales no se mueven)
    mapa, anexos = {}, []

    def alta(clave, chunk):
        mapa[clave] = N_XFS + len(anexos)
        anexos.append(chunk)

    # _xfs_en_regiones se llena en main() (inventariar_regiones) antes de llamar acá
    for s in sorted(_xfs_en_regiones):
        if s in XF_HDR:
            alta((s, "hdr"), xf_derivado(xfs[s], id_hdr))
        else:
            alta((s, "impar"), xf_derivado(xfs[s], id_grid, fill_id=0))
            alta((s, "par"), xf_derivado(xfs[s], id_grid, fill_id=id_zebra))
    alta((XF_PENDIENTE, "fix"), xf_derivado(xfs[XF_PENDIENTE], 0, font_id=id_font_ambar))

    texto = texto.replace(cellxfs, patch_count(
        cellxfs.replace("</cellXfs>", "".join(anexos) + "</cellXfs>"), "cellXfs", N_XFS + len(anexos)), 1)
    return texto, mapa


_xfs_en_regiones = set()


def inventariar_regiones(originales):
    """Releva qué xfs de origen aparecen dentro de las regiones (incluye el 0)."""
    for n, rects in REGIONES.items():
        data = originales[f"xl/worksheets/sheet{n}.xml"].decode("utf-8")
        rr = [parse_rect(r) for r in rects]
        for m in CELL_RE.finditer(data):
            cell = m.group(0)
            mr = re.search(r'r="([A-Z]+)(\d+)"', cell)
            col, fila = col_a_num(mr.group(1)), int(mr.group(2))
            if any(c1 <= col <= c2 and f1 <= fila <= f2 for c1, f1, c2, f2 in rr):
                ms = re.search(r' s="(\d+)"', cell)
                _xfs_en_regiones.add(int(ms.group(1)) if ms else 0)


def parchear_hoja(n, texto, mapa, wraps):
    nombre = f"sheet{n}.xml"
    # pestaña y panel congelado
    if "<sheetPr" in texto:
        fallo(f"{nombre}: ya tiene sheetPr")
    if texto.count("<dimension ") != 1:
        fallo(f"{nombre}: dimension no es única")
    texto = texto.replace("<dimension ", f'<sheetPr><tabColor rgb="{TABS[n]}"/></sheetPr><dimension ', 1)
    sv_viejo, sv_nuevo = SHEET_VIEWS[n]
    texto = reemplazo_exacto(texto, sv_viejo, sv_nuevo, 1, nombre)
    if n not in REGIONES and n != 1:
        return texto, 0, 0

    rects = [parse_rect(r) for r in REGIONES.get(n, [])]
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
        if n == 1:
            if s != XF_PENDIENTE:
                return cell
            variante = "fix"
        else:
            if not any(c1 <= col <= c2 and f1 <= fila <= f2 for c1, f1, c2, f2 in rects):
                return cell
            variante = "hdr" if s in XF_HDR else ("par" if fila % 2 == 0 else "impar")
            filas_tratadas.add(fila)
        nuevo_s = mapa[(s, variante)]
        head_nuevo = (head.replace(ms.group(0), f' s="{nuevo_s}"', 1) if ms
                      else head.replace(mr.group(0), mr.group(0) + f' s="{nuevo_s}"', 1))
        tocadas += 1
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
            return tag[:-1] + ' ht="19" customHeight="1">'
        return tag

    texto = ROW_OPEN_RE.sub(fila_alta, texto)
    return texto, tocadas, elevadas


# ---------------- verificación ----------------

def celdas(data):
    root = ET.fromstring(data)
    out = []
    for c in root.iter(f"{NS}c"):
        f = c.find(f"{NS}f")
        v = c.find(f"{NS}v")
        out.append((c.get("r"), c.get("t"),
                    None if f is None else f.text, None if v is None else v.text))
    return out


def normalizar(data):
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
    if bloque(est_orig, "numFmts") != bloque(est_nuevo, "numFmts"):
        fallo("styles.xml: cambió algún formato numérico")
    if bloque(est_orig, "dxfs") != bloque(est_nuevo, "dxfs"):
        fallo("styles.xml: cambió el formato condicional (dxfs)")
    xfs_orig, xfs_nuevo = indice_xfs(est_orig), indice_xfs(est_nuevo)
    if xfs_nuevo[:N_XFS] != xfs_orig:
        fallo("styles.xml: algún cellXf original cambió (debían quedar intactos)")

    numfmt = lambda xfs, i: xfs[i][0].get("numFmtId", "0")
    fuente = lambda xfs, i: xfs[i][0].get("fontId", "0")
    aprobados_fuente = {(XF_PENDIENTE, mapa[(XF_PENDIENTE, "fix")])}

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
            fallo(f"{nombre}: alguna celda cambió de valor/texto/fórmula")
        celdas_cmp += len(despues)
        formulas += sum(1 for c in despues if c[2] is not None)

        viejos = {c.get("r"): int(c.get("s", "0")) for c in ET.fromstring(originales[nombre]).iter(f"{NS}c")}
        ids_mapa = set(mapa.values())
        for c in ET.fromstring(data).iter(f"{NS}c"):
            s_v, s_n = viejos[c.get("r")], int(c.get("s", "0"))
            if s_v == s_n:
                continue
            if s_n < N_XFS or s_n not in ids_mapa:
                fallo(f"{nombre}!{c.get('r')}: estilo nuevo fuera del mapa aprobado")
            if numfmt(xfs_nuevo, s_n) != numfmt(xfs_orig, s_v):
                fallo(f"{nombre}!{c.get('r')}: cambió el formato numérico")
            if fuente(xfs_nuevo, s_n) != fuente(xfs_orig, s_v) and (s_v, s_n) not in aprobados_fuente:
                fallo(f"{nombre}!{c.get('r')}: cambió la fuente fuera del mapa aprobado")
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
    tocadas = {"xl/styles.xml"} | {f"xl/worksheets/sheet{n}.xml" for n in range(1, 11)}
    originales = {i.filename: zin.read(i.filename) for i in zin.infolist()}
    if set(tocadas) - set(originales):
        fallo("faltan partes esperadas en el paquete")

    inventariar_regiones(originales)
    est_nuevo, mapa = parchear_estilos(originales["xl/styles.xml"].decode("utf-8"))
    wraps = wraps_de_estilos(originales["xl/styles.xml"].decode("utf-8"))
    nuevas = {"xl/styles.xml": est_nuevo.encode("utf-8")}
    stats = {}
    for n in range(1, 11):
        nombre = f"xl/worksheets/sheet{n}.xml"
        texto, tocadas_n, elevadas = parchear_hoja(n, originales[nombre].decode("utf-8"), mapa, wraps)
        nuevas[nombre] = texto.encode("utf-8")
        stats[n] = (tocadas_n, elevadas)

    with zipfile.ZipFile(salida, "w") as zout:
        for info in zin.infolist():
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zi.create_system = info.create_system
            zout.writestr(zi, nuevas.get(info.filename, originales[info.filename]))

    zver = zipfile.ZipFile(salida)
    intactas, celdas_cmp, formulas, restyled = verificar(zin, zver, originales, tocadas, mapa)

    print("VERIFICACIÓN OK — cero cambios de contenido")
    print(f"  partes copiadas byte a byte : {intactas} (calcChain, sharedStrings, gráficos, tablas, tema)")
    print(f"  partes reescritas (estilo)  : {len(tocadas)}")
    print(f"  celdas comparadas idénticas : {celdas_cmp} ({formulas} con fórmula, valores cacheados intactos)")
    print(f"  celdas re-estiladas         : {restyled}")
    for n in range(1, 11):
        t, e = stats[n]
        if t or e:
            print(f"    hoja {n:>2}: celdas={t:<4} filas elevadas={e}")
    print(f"  sha256 entrada : {sha256(entrada)}")
    print(f"  sha256 salida  : {sha256(salida)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__.strip().splitlines()[-1])
    main(sys.argv[1], sys.argv[2])
