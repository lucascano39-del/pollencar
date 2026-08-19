#!/usr/bin/env bash
# Ensambla el deck y genera el PDF. Uso: ./build.sh [ruta-chrome]
set -euo pipefail
cd "$(dirname "$0")"
SRC="${SRC:-deck.html}"
[ "$SRC" = "deck.html" ] && ./assemble.sh
CHROME="${1:-${CHROME_BIN:-}}"
if [ -z "$CHROME" ]; then
  for c in /opt/pw-browsers/chromium-*/chrome-linux/chrome \
           /usr/bin/chromium /usr/bin/chromium-browser /usr/bin/google-chrome \
           "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; do
    [ -x "$c" ] && CHROME="$c" && break
  done
fi
[ -n "$CHROME" ] || { echo "No se encontró Chromium/Chrome. Pasalo como argumento."; exit 1; }
OUT="${OUT:-Malaparte_Analytica_Capacidades.pdf}"
"$CHROME" --headless --disable-gpu --no-sandbox --no-pdf-header-footer \
  --print-to-pdf="$OUT" "$SRC" 2>/dev/null
python3 - "$OUT" <<'PY'
import sys
try:
    import pypdfium2 as p
    d = p.PdfDocument(sys.argv[1]); print(f"PDF generado: {sys.argv[1]} · {len(d)} páginas · {d[0].get_size()} pt")
except ImportError:
    print(f"PDF generado: {sys.argv[1]}")
PY
