#!/usr/bin/env bash
# Leitstelle auf einen Rechner im Netz ausrollen: hochladen, dort holen, bauen, starten.
# Nutzung: ZIEL=benutzer@rechner tools/ausrollen.sh   (oder Werte in privat/ausrollen.env)
#          ORDNER=/pfad DATEN=/pfad zusätzlich möglich
# Ausgerollt wird nur, was im Repository liegt. Der Bau scheitert, wenn ein Test rot ist;
# dann läuft der alte Stand weiter. Gebaut wird, während der alte Stand weiterläuft; neu gestartet erst, wenn
# kein Auftrag mehr über die Leitstelle läuft (Lagebild: laeuft oder zugeteilt), damit keine Anfrage einer App
# mitten im Rechnen abreißt. SOFORT=1 tools/ausrollen.sh startet ohne zu warten.
set -euo pipefail
HIER="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
if [ -f "$HIER/privat/ausrollen.env" ]; then
  # shellcheck disable=SC1091
  . "$HIER/privat/ausrollen.env"
fi
ZIEL="${ZIEL:?Ziel fehlt: ZIEL=benutzer@rechner tools/ausrollen.sh}"
ORDNER="${ORDNER:-/home/${ZIEL%@*}/leitstelle}"
QUELLE="$(git -C "$HIER" remote get-url origin)"

if [ -n "$(git -C "$HIER" status --porcelain)" ]; then
  echo "Abbruch: es gibt nicht eingecheckte Änderungen; erst committen." >&2
  exit 1
fi
git -C "$HIER" push --quiet origin HEAD

echo "Rolle aus: $(git -C "$HIER" log -1 --format='%h %s' | cut -c1-80)"
DATEN="${DATEN:-$ORDNER/daten}"
ssh "$ZIEL" "set -e
  mkdir -p '$DATEN'
  if [ ! -d '$ORDNER/.git' ]; then rm -rf '$ORDNER' && git clone --quiet '$QUELLE' '$ORDNER'; fi
  cd '$ORDNER' && git fetch --quiet origin && git reset --quiet --hard origin/main
  LEITSTELLE_DATENORDNER='$DATEN' docker compose build"

PI_HOST="${ZIEL#*@}"
laufend() {
  curl -fsS -m 10 "http://$PI_HOST:8530/api/lage" 2>/dev/null | python3 -c 'import sys, json
try:
    print(sum(1 for a in json.load(sys.stdin).get("auftraege", []) if a.get("zustand") in ("laeuft", "zugeteilt")))
except ValueError:
    print(0)' || echo 0
}
if [ "${SOFORT:-}" != 1 ]; then
  if [ "$(laufend)" != 0 ]; then echo "Wartet auf einen Moment ohne laufenden Auftrag ..."; fi
  while [ "$(laufend)" != 0 ]; do sleep 1; done
fi
ssh "$ZIEL" "set -e; cd '$ORDNER' && LEITSTELLE_DATENORDNER='$DATEN' docker compose up -d && docker compose ps"

for _ in $(seq 1 60); do
  if curl -fsS "http://$PI_HOST:8530/gesundheit" >/dev/null 2>&1 && curl -fsS "http://$PI_HOST:8535/gesundheit" >/dev/null 2>&1; then
    echo "Läuft: Leitstelle http://$PI_HOST:8530/  Entwürfe http://$PI_HOST:8535/  (Version $(curl -fsS "http://$PI_HOST:8530/gesundheit" | python3 -c 'import sys,json; print(json.load(sys.stdin)["version"])'))"
    exit 0
  fi
  sleep 1
done
echo "Abbruch: Gesundheit auf $PI_HOST:8530 oder :8535 antwortet nicht" >&2
exit 1
