#!/usr/bin/env bash
# Ensambla deck.html a partir de slides/NN-*.html en orden y genera el PDF.
set -euo pipefail
cd "$(dirname "$0")"
OUTHTML="${OUTHTML:-deck.html}"
{
  cat <<'HEAD'
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="description" content="Malaparte Analytica · investigación de opinión pública, inteligencia electoral y operación digital para campañas.">
<title>Malaparte Analytica · Capacidades · Opinión pública e inteligencia electoral</title>
<link rel="stylesheet" href="assets/fonts.css">
<link rel="stylesheet" href="assets/deck.css">
</head>
<body>
HEAD
  for f in slides/[0-9][0-9]-*.html; do printf '\n<!-- ===== %s ===== -->\n' "$f"; cat "$f"; done
  printf '\n</body>\n</html>\n'
} > "$OUTHTML"
echo "HTML ensamblado: $OUTHTML ($(grep -c '<section class="slide' "$OUTHTML") slides)"
