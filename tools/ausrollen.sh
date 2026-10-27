#!/usr/bin/env bash
# Leitstelle auf einen Rechner im Netz ausrollen: hochladen, dort holen, bauen, starten.
# Nutzung: tools/ausrollen.sh                        Ziel, Ordner und Datenordner des Hauses aus der privaten Wahrheit
#                                                     (handbuch ziel leitstelle)
#          ZIEL=benutzer@rechner tools/ausrollen.sh   ein anderer Rechner; ORDNER=/pfad DATEN=/pfad zusätzlich möglich
# Ausgerollt wird nur, was im Repository liegt. Der Bau scheitert, wenn ein Test rot ist;
# dann läuft der alte Stand weiter. Gebaut wird, während der alte Stand weiterläuft; neu gestartet erst, wenn
# kein Auftrag mehr über die Leitstelle läuft (Lagebild: laeuft oder zugeteilt), damit keine Anfrage einer App
# mitten im Rechnen abreißt, höchstens WARTEN_S Sekunden (Vorgabe 600). SOFORT=1 tools/ausrollen.sh startet ohne zu warten.
# Nach einem gelungenen Ausrollen (neuer Stand läuft, Version antwortet) räumt es auf dem Zielrechner Docker auf:
# verwaiste Abbilder ohne Namen und den Baucache bis auf BAUCACHE_GB (Vorgabe 20 GB). Bei einem Fehlschlag bleibt alles
# stehen. Grund: Docker auf dem Pi lief mit 239 GB Baucache voll, weil kein Ausrollen je aufräumte (27.10.2026).
set -euo pipefail
BAUCACHE_GB="${BAUCACHE_GB:-20}"          # so viel Baucache darf nach dem Aufräumen bleiben, in GB
case "$BAUCACHE_GB" in
  ''|*[!0-9]*) echo "Abbruch: BAUCACHE_GB ist eine ganze Zahl in GB, nicht '$BAUCACHE_GB'" >&2; exit 1 ;;
esac
# >>> handbuch: vorher Seite, Einrichtungsskript, Probelauf und Bau des Handbuchs (eingesetzt von "handbuch einbinden")
handbuch_befehl="$(command -v handbuch || true)"
[ -n "$handbuch_befehl" ] || handbuch_befehl="$HOME/.local/bin/handbuch"
if [ ! -x "$handbuch_befehl" ]; then
  echo "Abbruch: das Werkzeug handbuch fehlt (Handbuch, Grundlage Mac)" >&2
  exit 1
fi
"$handbuch_befehl" freigabe "$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)" || {
  echo "Abbruch: das Handbuch ist nicht in Ordnung, nichts ausgerollt" >&2
  exit 1
}
# <<< handbuch
HIER="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
ziel_wert() {
  "$handbuch_befehl" ziel leitstelle "$1" || { echo "Abbruch: $1 fehlt im Ziel (handbuch ziel leitstelle)" >&2; exit 1; }
}
if [ -z "${ZIEL:-}" ]; then
  ZIEL="$(ziel_wert rechner)"
  ORDNER="${ORDNER:-$(ziel_wert wurzel)}"
  DATEN="${DATEN:-$(ziel_wert LEITSTELLE_DATENORDNER)}"
fi
ORDNER="${ORDNER:-/home/${ZIEL%@*}/leitstelle}"
DATEN="${DATEN:-$ORDNER/daten}"
QUELLE="$(git -C "$HIER" remote get-url origin)"

if [ -n "$(git -C "$HIER" status --porcelain)" ]; then
  echo "Abbruch: es gibt nicht eingecheckte Änderungen; erst committen." >&2
  exit 1
fi
git -C "$HIER" push --quiet origin HEAD

echo "Rolle aus: $(git -C "$HIER" log -1 --format='%h %s' | cut -c1-80)"
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
  # höchstens WARTEN_S (Vorgabe 600 s): Apps mit stetigem Strom lassen sonst nie einen ruhigen Moment; danach wird
  # ausgerollt, die Apps warten über den Appkern und versuchen erneut
  if [ "$(laufend)" != 0 ]; then echo "Wartet auf einen Moment ohne laufenden Auftrag (höchstens ${WARTEN_S:-600} s) ..."; fi
  BIS=$(( $(date +%s) + ${WARTEN_S:-600} ))
  while [ "$(laufend)" != 0 ] && [ "$(date +%s)" -lt "$BIS" ]; do sleep 1; done
fi
ssh "$ZIEL" "set -e; cd '$ORDNER' && LEITSTELLE_DATENORDNER='$DATEN' docker compose up -d && docker compose ps"

# Aufräumen auf dem Zielrechner, nur nach gelungenem Ausrollen: verwaiste Abbilder ohne Namen (docker image prune) und
# der Baucache bis auf die Grenze; benannte Abbilder und laufende Container bleiben. Gibt den freigegebenen Platz aus.
# Scheitert das Aufräumen, ist das Ausrollen trotzdem gelungen.
aufraeumen() {
  echo "Räumt Docker auf $PI_HOST auf: verwaiste Abbilder, Baucache bis $BAUCACHE_GB GB ..."
  ssh "$ZIEL" "set -eo pipefail
    abbilder=\$(docker image prune -f | sed -n 's/^Total reclaimed space: //p')
    baucache=\$(docker builder prune -f --max-used-space '${BAUCACHE_GB}GB' | sed -n 's/^Total:[[:space:]]*//p')
    echo \"Aufgeräumt: verwaiste Abbilder \${abbilder:-0B}, Baucache \${baucache:-0B} freigegeben (Grenze ${BAUCACHE_GB} GB)\"" \
    || echo "Aufräumen auf $PI_HOST gescheitert; das Ausrollen selbst ist gelungen" >&2
}

for _ in $(seq 1 60); do
  if curl -fsS "http://$PI_HOST:8530/gesundheit" >/dev/null 2>&1 && curl -fsS "http://$PI_HOST:8535/gesundheit" >/dev/null 2>&1; then
    echo "Läuft: Leitstelle http://$PI_HOST:8530/  Entwürfe http://$PI_HOST:8535/  (Version $(curl -fsS "http://$PI_HOST:8530/gesundheit" | python3 -c 'import sys,json; print(json.load(sys.stdin)["version"])'))"
    aufraeumen
    exit 0
  fi
  sleep 1
done
echo "Abbruch: Gesundheit auf $PI_HOST:8530 oder :8535 antwortet nicht" >&2
exit 1
