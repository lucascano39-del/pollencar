#!/usr/bin/env bash
# Previsualiza un slide suelto: ./preview_slide.sh slides/03-margen.html  -> /tmp/<nombre>.png
set -euo pipefail
cd "$(dirname "$0")"
SRC="$1"; NAME="$(basename "$SRC" .html)"
OUTDIR="${OUTDIR:-/tmp/slidepreview}"; mkdir -p "$OUTDIR"
CHROME="${CHROME_BIN:-}"
if [ -z "$CHROME" ]; then
  for c in /opt/pw-browsers/chromium-*/chrome-linux/chrome /usr/bin/chromium /usr/bin/google-chrome; do
    [ -x "$c" ] && CHROME="$c" && break
  done
fi
cat slides/_harness_head.html "$SRC" > "slides/.preview_$NAME.html"
printf '</body></html>' >> "slides/.preview_$NAME.html"
"$CHROME" --headless --disable-gpu --no-sandbox --no-pdf-header-footer \
  --print-to-pdf="$OUTDIR/$NAME.pdf" "slides/.preview_$NAME.html" 2>/dev/null
python3 - "$OUTDIR/$NAME.pdf" "$OUTDIR/$NAME" <<'PY'
import sys, pypdfium2 as pdfium
pdf = pdfium.PdfDocument(sys.argv[1])
print("páginas:", len(pdf), "(debe ser 1: si son 2, el contenido se desborda)")
for i in range(len(pdf)):
    pdf[i].render(scale=1.0).to_pil().save(f"{sys.argv[2]}_{i+1}.png")
    print(f"{sys.argv[2]}_{i+1}.png")
PY
rm -f "slides/.preview_$NAME.html"
