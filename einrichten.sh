#!/usr/bin/env bash
# Einrichten der Leitstelle. Schritte und Proben der Neueinrichtung stehen in docs/handbuch.md.
#
#   ./einrichten.sh                                       im Klon auf dem Zielrechner: Datenordner anlegen
#                                                         (LEITSTELLE_DATENORDNER, Vorgabe ./daten), bauen (dabei laufen
#                                                         alle Kern-Tests und die Typprüfung der Oberfläche), starten und
#                                                         warten, bis Kern, HTTPS davor und Entwürfe gesund sind. Das
#                                                         Zertifikat der Hausstelle muss in zertifikate/ liegen. Vom Mac
#                                                         aus macht tools/ausrollen.sh dasselbe samt Zertifikat.
#   ./einrichten.sh --probe --ziel DIR --port-versatz N   Probelauf des Handbuchs: dasselbe in DIR mit leerem Datenordner,
#                                                         Wegwerfzertifikat einer Wegwerf-Hausstelle, eigenen Namen und
#                                                         Ports um N verschoben, nur an 127.0.0.1
#                                                         (deploy/probelauf.compose.yml)
#   ./einrichten.sh --probe --ziel DIR --abbauen          entfernt Container, Netz und die gebauten Abbilder
set -euo pipefail
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WARTEN_S=180
PROBE_COMPOSE=(-f docker-compose.yml -f deploy/probelauf.compose.yml)

# gesund KERN_PORT VORNE_PORT ENTWUERFE_PORT CA: Kern direkt, Kern über HTTPS (geprüft gegen die Hausstelle CA) und
# Entwürfe antworten
gesund() {
  curl -sf "http://127.0.0.1:$1/gesundheit" >/dev/null \
    && curl -sf --cacert "$4" --resolve "leitstelle.local:$2:127.0.0.1" "https://leitstelle.local:$2/gesundheit" >/dev/null \
    && curl -sf "http://127.0.0.1:$3/gesundheit" >/dev/null
}

warten() {
  local ende=$(( $(date +%s) + WARTEN_S ))
  while [ "$(date +%s)" -lt "$ende" ]; do
    if gesund "$@"; then return 0; fi
    sleep 2
  done
  echo "Kern, HTTPS davor oder Entwürfe nach $WARTEN_S s nicht gesund" >&2
  return 1
}

# veröffentlichter Port eines Dienstes laut docker-compose.yml (die Ports stehen nur dort)
grundport() {
  docker compose -f docker-compose.yml config --format json | python3 -c '
import json, sys
dienst, innen = sys.argv[1], int(sys.argv[2])
ports = json.load(sys.stdin)["services"][dienst].get("ports", [])
print(next(p["published"] for p in ports if int(p["target"]) == innen))' "$1" "$2"
}

# Port am Rechner eines laufenden Dienstes
port_von() {
  docker compose port "$1" "$2" | head -1 | sed 's/.*://'
}

einrichten() {
  cd "$HIER"
  export LEITSTELLE_DATENORDNER="${LEITSTELLE_DATENORDNER:-./daten}"
  local zertifikate="${LEITSTELLE_ZERTIFIKATE:-./zertifikate}"
  for datei in leitstelle.pem leitstelle-schluessel.pem rootCA.pem; do
    if [ ! -f "$zertifikate/$datei" ]; then
      echo "Abbruch: $zertifikate/$datei fehlt (Zertifikat der Hausstelle; tools/ausrollen.sh am Mac stellt es aus)" >&2
      exit 1
    fi
  done
  mkdir -p "$LEITSTELLE_DATENORDNER"
  docker compose build
  docker compose up -d
  warten "$(port_von leitstelle 8530)" "$(port_von vorne 8531)" "$(port_von entwuerfe 80)" "$zertifikate/rootCA.pem"
  echo "Leitstelle eingerichtet: HTTPS Port $(port_von vorne 8531) (Kern direkt $(port_von leitstelle 8530)), Entwürfe Port $(port_von entwuerfe 80)"
}

probe_aufbauen() {
  local ziel="$1" versatz="$2" kern vorne entwuerfe
  cd "$ziel"
  kern=$(( $(grundport leitstelle 8530) + versatz ))
  vorne=$(( $(grundport vorne 8531) + versatz ))
  entwuerfe=$(( $(grundport entwuerfe 80) + versatz ))
  mkdir -p daten zertifikate
  # Wegwerf-Hausstelle in DIR, nie die echte: das Blattzertifikat gilt nur für diese Probe
  CAROOT="$ziel/hausstelle" mkcert -cert-file zertifikate/leitstelle.pem -key-file zertifikate/leitstelle-schluessel.pem \
    leitstelle.local 127.0.0.1 >/dev/null 2>&1
  cp hausstelle/rootCA.pem zertifikate/rootCA.pem
  {
    echo "LEITSTELLE_DATENORDNER=$ziel/daten"
    echo "LEITSTELLE_ZERTIFIKATE=$ziel/zertifikate"
    echo "PROBE_PORT_LEITSTELLE=$kern"
    echo "PROBE_PORT_VORNE=$vorne"
    echo "PROBE_PORT_ENTWUERFE=$entwuerfe"
  } > .env
  docker compose "${PROBE_COMPOSE[@]}" build
  docker compose "${PROBE_COMPOSE[@]}" up -d
  if warten "$kern" "$vorne" "$entwuerfe" zertifikate/rootCA.pem; then
    echo "ANTWORTET https://127.0.0.1:$vorne/gesundheit"
    return 0
  fi
  docker compose "${PROBE_COMPOSE[@]}" logs --tail 40 >&2 || true
  return 1
}

probe_abbauen() {
  cd "$1"
  [ -f .env ] || return 0
  docker compose "${PROBE_COMPOSE[@]}" down --volumes --remove-orphans --rmi all
}

probe=0; abbauen=0; ziel=""; versatz=""
while [ $# -gt 0 ]; do
  case "$1" in
    --probe) probe=1 ;;
    --abbauen) abbauen=1 ;;
    --ziel) ziel="${2:?--ziel braucht einen Ordner}"; shift ;;
    --port-versatz) versatz="${2:?--port-versatz braucht eine Zahl}"; shift ;;
    *) echo "unbekannte Angabe: $1" >&2; exit 2 ;;
  esac
  shift
done

if [ "$probe" = 0 ]; then
  einrichten
elif [ -z "$ziel" ] || [ ! -d "$ziel" ]; then
  echo "--probe braucht --ziel mit einem vorhandenen Ordner" >&2; exit 2
elif [ "$abbauen" = 1 ]; then
  probe_abbauen "$(cd "$ziel" && pwd)"
else
  probe_aufbauen "$(cd "$ziel" && pwd)" "${versatz:?--port-versatz fehlt}"
fi
