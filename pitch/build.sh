#!/usr/bin/env bash
# Genera el PDF del deck de capacidades a partir de deck.html.
# Requiere un binario de Chromium/Chrome (headless). Uso: ./build.sh [ruta-chrome]
set -euo pipefail
cd "$(dirname "$0")"
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
  --print-to-pdf="$OUT" "deck.html" 2>/dev/null
echo "PDF generado: $OUT"
