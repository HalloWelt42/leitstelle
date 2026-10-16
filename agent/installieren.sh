#!/bin/sh
# Knoten-Agent der Leitstelle installieren oder aktualisieren, für den angemeldeten Benutzer.
#
#   sh -c "$(curl -fsSL __LEITSTELLE_ADRESSE__/agent/installieren.sh)"
#
# Fragt beim ersten Mal nach dem Schlüssel (Leitstelle, Seite Knoten, Agent-Schlüssel) oder nimmt ihn aus
# LEITSTELLE_SCHLUESSEL. Legt den Agentenordner an (Vorgabe ~/Leitstelle-Agent), installiert den Agenten
# in ein eigenes venv und richtet ihn als Dienst ein, der Neustarts übersteht: macOS launchd (startet mit
# der Anmeldung des Benutzers), Linux systemd im Benutzerkontext. Vorhandene Dienstdateien, Sollzustand
# und Schlüssel bleiben bei einer Aktualisierung erhalten.
set -eu

LEITSTELLE="${LEITSTELLE:-__LEITSTELLE_ADRESSE__}"
ORDNER="${LEITSTELLE_AGENT_ORDNER:-$HOME/Leitstelle-Agent}"
PYTHON="${PYTHON:-python3}"
KENNUNG="leitstelle.agent"

meldung() { printf '%s\n' "$*"; }
abbruch() { printf 'Abbruch: %s\n' "$*" >&2; exit 1; }

command -v curl >/dev/null || abbruch "curl fehlt"
command -v "$PYTHON" >/dev/null || abbruch "$PYTHON fehlt (Python 3.11 oder neuer)"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || abbruch "Python 3.11 oder neuer nötig ($PYTHON)"

mkdir -p "$ORDNER/dienste" "$ORDNER/protokolle"
chmod 700 "$ORDNER"

# ── Schlüssel ────────────────────────────────────────────────────────────
if [ -n "${LEITSTELLE_SCHLUESSEL:-}" ]; then
  SCHLUESSEL="$LEITSTELLE_SCHLUESSEL"
elif [ -s "$ORDNER/schluessel" ]; then
  SCHLUESSEL=""
else
  [ -r /dev/tty ] || abbruch "kein Schlüssel: LEITSTELLE_SCHLUESSEL setzen"
  printf 'Agent-Schlüssel aus der Leitstelle (Seite Knoten): ' > /dev/tty
  stty -echo < /dev/tty; read -r SCHLUESSEL < /dev/tty; stty echo < /dev/tty; printf '\n' > /dev/tty
  [ -n "$SCHLUESSEL" ] || abbruch "kein Schlüssel eingegeben"
fi
if [ -n "$SCHLUESSEL" ]; then
  ( umask 077; printf '%s' "$SCHLUESSEL" > "$ORDNER/schluessel" )
fi

# ── Einstellungen ────────────────────────────────────────────────────────
if [ ! -f "$ORDNER/agent.toml" ]; then
  cat > "$ORDNER/agent.toml" <<EOF
# Knoten-Agent: Adresse der Leitstelle und Takt. Alle weiteren Einstellungen mit Vorgaben stehen in der
# Anleitung des Agenten (README im Ordner agent/ des Projekts).
leitstelle = "$LEITSTELLE"
takt_s = 5
EOF
fi

# ── Agent holen und installieren ─────────────────────────────────────────
QUELLE="$ORDNER/.quelle"
rm -rf "$QUELLE" && mkdir -p "$QUELLE"
curl -fsSL "$LEITSTELLE/agent/paket.tar.gz" | tar -xz -C "$QUELLE"
[ -d "$ORDNER/.venv" ] || "$PYTHON" -m venv "$ORDNER/.venv"
"$ORDNER/.venv/bin/pip" install --quiet --upgrade pip
"$ORDNER/.venv/bin/pip" install --quiet --upgrade "$QUELLE/leitstelle-agent"
AGENT_PY="$ORDNER/.venv/bin/python"

# ── Als Dienst einrichten ────────────────────────────────────────────────
case "$(uname -s)" in
  Darwin)
    PLIST="$HOME/Library/LaunchAgents/$KENNUNG.plist"
    mkdir -p "$HOME/Library/LaunchAgents"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$KENNUNG</string>
  <key>ProgramArguments</key>
  <array><string>$AGENT_PY</string><string>-m</string><string>leitstelle_agent</string><string>$ORDNER</string></array>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string><key>LANG</key><string>de_DE.UTF-8</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>ProcessType</key><string>Interactive</string>
  <key>StandardOutPath</key><string>$ORDNER/protokolle/agent.log</string>
  <key>StandardErrorPath</key><string>$ORDNER/protokolle/agent.log</string>
</dict>
</plist>
EOF
    launchctl bootout "gui/$(id -u)/$KENNUNG" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    meldung "Agent läuft als launchd-Dienst $KENNUNG (startet mit der Anmeldung)."
    ;;
  Linux)
    UNIT="$HOME/.config/systemd/user/leitstelle-agent.service"
    mkdir -p "$(dirname "$UNIT")"
    cat > "$UNIT" <<EOF
[Unit]
Description=Knoten-Agent der Leitstelle
After=network-online.target

[Service]
ExecStart=$AGENT_PY -m leitstelle_agent $ORDNER
Restart=always
RestartSec=10
KillMode=process
StandardOutput=append:$ORDNER/protokolle/agent.log
StandardError=append:$ORDNER/protokolle/agent.log

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now leitstelle-agent.service
    systemctl --user restart leitstelle-agent.service
    meldung "Agent läuft als systemd-Dienst im Benutzerkontext."
    if [ "$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null || echo no)" != "yes" ]; then
      meldung "Damit er ohne Anmeldung startet, einmal mit Verwalterrechten ausführen: sudo loginctl enable-linger $(id -un)"
    fi
    ;;
  *) abbruch "unbekanntes Betriebssystem $(uname -s)" ;;
esac

meldung "Agentenordner: $ORDNER (Dienste unter dienste/, Ausgaben unter protokolle/)"
meldung "Stand der Dienste: $AGENT_PY -m leitstelle_agent $ORDNER --liste"
