#!/usr/bin/env bash
# Entwurfs-Betrachter steuern:  ./start-mockups.sh [start|stop|restart|status] [port]
#
# Startet einen statischen Server auf der Projektwurzel im Hintergrund. Es läuft
# höchstens EINE Instanz; PID und Port stehen unter .run/. Die Entwürfe laden
# Schriften und Symbole aus frontend/node_modules, deshalb wird die Wurzel
# ausgeliefert. Vorgabe-Port 8535.
set -uo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN="$HIER/.run"; mkdir -p "$RUN"
PIDF="$RUN/mockups.pid"
PORTF="$RUN/mockups.port"
LOG="$RUN/mockups.log"

lebt() { [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF" 2>/dev/null)" 2>/dev/null; }

stop() {
  if [ -f "$PIDF" ]; then kill "$(cat "$PIDF" 2>/dev/null)" 2>/dev/null; fi
  rm -f "$PIDF" "$PORTF"
}

start() {
  stop
  nohup python3 -m http.server "$PORT" --directory "$HIER" > "$LOG" 2>&1 &
  echo "$!" > "$PIDF"; echo "$PORT" > "$PORTF"
  sleep 0.3
  if lebt; then
    echo "Entwurfs-Betrachter läuft auf Port $PORT (PID $(cat "$PIDF"))"
    echo "  Galerie: http://localhost:$PORT/mockups/index.html"
  else
    echo "Start fehlgeschlagen - Log: $LOG"; tail -n 3 "$LOG" 2>/dev/null; exit 1
  fi
}

BEFEHL="${1:-start}"
case "$BEFEHL" in
  [0-9]*) PORT="$BEFEHL"; BEFEHL=start ;;
  *) PORT="${2:-$(cat "$PORTF" 2>/dev/null || echo 8535)}" ;;
esac

case "$BEFEHL" in
  start|restart) start ;;
  stop) stop; echo "gestoppt" ;;
  status) if lebt; then echo "läuft auf Port $(cat "$PORTF") (PID $(cat "$PIDF"))"; else echo "läuft nicht"; fi ;;
  *) echo "Gebrauch: $0 [start|stop|restart|status] [port]"; exit 2 ;;
esac
