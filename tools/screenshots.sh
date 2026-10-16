#!/usr/bin/env bash
# Bildschirmfotos aller Entwurfsseiten, je Thema eines, kopflos mit Chrome.
# Gebrauch: tools/screenshots.sh [zielordner] [seite ...]
# Ohne Seiten werden alle mockups/*.html außer index fotografiert.
# Der Entwurfs-Server muss laufen (./start-mockups.sh), Vorgabe Port 8535.
# Farbwelt wählbar über Umgebung: PALETTE=sanft|kraeftig|leuchtend FLAECHEN=blaugrau|tiefblau
# Fensterbreite über BREITE (Vorgabe 1600), Höhe über HOEHE (Vorgabe 1000)
set -uo pipefail
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZIEL="${1:-$HIER/.run/shots}"; shift || true
PORT="$(cat "$HIER/.run/mockups.port" 2>/dev/null || echo 8535)"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
mkdir -p "$ZIEL"
if [ "$#" -gt 0 ]; then SEITEN=("$@"); else
  SEITEN=(); for f in "$HIER"/mockups/*.html; do n="$(basename "$f" .html)"; SEITEN+=("$n"); done
fi
EXTRA=""
[ -n "${PALETTE:-}" ] && EXTRA="$EXTRA&palette=$PALETTE"
[ -n "${FLAECHEN:-}" ] && EXTRA="$EXTRA&flaechen=$FLAECHEN"
[ -n "${BLAU:-}" ] && EXTRA="$EXTRA&blau=$BLAU"
for s in "${SEITEN[@]}"; do
  for thema in dunkel hell; do
    "$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=${BREITE:-1600},${HOEHE:-1000} --virtual-time-budget=4000 --timeout=20000 \
      --screenshot="$ZIEL/$s-$thema.png" "http://localhost:$PORT/mockups/$s.html?theme=$thema&ohne-schalter$EXTRA" >/dev/null 2>&1
    echo "$s ($thema)"
  done
done
echo "Bilder unter $ZIEL"
