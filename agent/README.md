# Knoten-Agent

Ein kleiner Dienst je Rechner. Er misst Speicher, Swap und Last und meldet sie der Leitstelle, und er
startet und hält die KI-Dienste des Rechners an, die nicht über einen Modell-Läufer laufen (Sprache, Bild,
Musik und Ähnliches). Er verbindet sich von sich aus mit der Leitstelle; auf dem Rechner öffnet er keinen
Port. Ohne Verbindung arbeitet er weiter: Dienste, die laufen sollen, startet er nach einem Neustart des
Rechners wieder.

## Installieren

In der Leitstelle unter Knoten beim Rechner einen Agent-Schlüssel erzeugen, dann auf dem Rechner:

```bash
sh -c "$(curl -fsSL http://leitstelle:8530/agent/installieren.sh)"
```

Das Skript fragt nach dem Schlüssel, legt den Agentenordner `~/Leitstelle-Agent` an und richtet den Agenten
ein: auf dem Mac als launchd-Dienst (startet mit der Anmeldung), auf Linux als systemd-Dienst im
Benutzerkontext. Derselbe Befehl aktualisiert den Agenten; Dienstdateien, Sollzustand und Schlüssel bleiben.

## Der Agentenordner

| Pfad | Inhalt |
|---|---|
| `agent.toml` | Adresse der Leitstelle und Regeln (siehe unten) |
| `schluessel` | Schlüssel des Agenten, nur für den Benutzer lesbar |
| `dienste/<kennung>.toml` | je Dienst eine Datei; der Dateiname ist die Kennung |
| `protokolle/agent.log` | Ausgabe des Agenten |
| `protokolle/<kennung>.log` | Ausgabe des Dienstes |
| `zustand.json` | Sollzustand je Dienst und gemessene Höchstwerte |

Stand aller Dienste ansehen:

```bash
~/Leitstelle-Agent/.venv/bin/python -m leitstelle_agent ~/Leitstelle-Agent --liste
```

Neue oder geänderte Dienstdateien liest der Agent im nächsten Takt; ein Neustart ist nicht nötig.

## Dienstdatei

Beispiel: [beispiele/bildwerkstatt.toml](beispiele/bildwerkstatt.toml).

| Feld | Vorgabe | Bedeutung |
|---|---|---|
| `name` | Pflicht | Anzeigename |
| `ordner` | Pflicht | Arbeitsordner; `~` und `$VAR` werden aufgelöst |
| `befehl` | Pflicht | Programm und Argumente als Liste; ein relativer Programmpfad gilt ab `ordner` |
| `vorher` | leer | Befehl, der vor jedem Start einmal läuft |
| `port` | keiner | erreichbar heißt: der Port nimmt Verbindungen an (IPv4 oder IPv6) |
| `pruefadresse` | keine | strenger: eine Antwort unter 500 von dieser Adresse |
| `faehigkeiten` | leer | `stimme`, `hoeren`, `bild_erzeugen`, `musik`, ... |
| `speicher_gb` | 1 | Schätzung, bis der Agent den Dienst gemessen hat |
| `startzeit_s` | 120 | so lange darf der Start bis zur Erreichbarkeit dauern |
| `anhaltezeit_s` | 20 | so lange darf das Beenden dauern, danach hart |
| `umgebung` | leer | zusätzliche Umgebungsvariablen |
| `umgebung_datei` | keine | Datei mit Zeilen `NAME=WERT`, zum Beispiel die `.env` eines Projekts |
| `pfad` | übliche Systempfade | Suchpfad für Programme |
| `neustart` | ja | nach einem Absturz neu starten, solange der Dienst laufen soll |

## Abgrenzung je Dienst

Jeder Dienst läuft in eigener Sitzung und Prozessgruppe, im eigenen Arbeitsordner, mit eigener Umgebung (nur
Suchpfad, Heimordner, Sprache und was die Datei nennt) und schreibt in eine eigene Protokolldatei. Anhalten
trifft genau seine Prozessgruppe: erst freundlich, nach `anhaltezeit_s` hart. Dienste, die die Grafik des Mac
nutzen, laufen nativ; Container haben dort keinen Zugriff auf die Grafik.

Läuft ein Dienst schon, ohne vom Agenten gestartet zu sein (sein Port antwortet), übernimmt der Agent ihn:
er misst ihn und kann ihn anhalten (den lauschenden Prozess und dessen Nachfahren), startet ihn aber nicht
doppelt. Der nächste Start geschieht dann durch den Agenten.

## agent.toml

| Feld | Vorgabe | Bedeutung |
|---|---|---|
| `leitstelle` | Pflicht | Basisadresse, zum Beispiel `http://leitstelle:8530` |
| `name` | Rechnername | Anzeigename bei der Anmeldung |
| `takt_s` | 5 | Abstand der Messungen und der Dienstprüfung |
| `neustart_pausen_s` | 5, 30, 120 | Pausen vor dem ersten, zweiten, dritten Neustart nach Absturz |
| `neustart_fenster_s` | 600 | Zeitraum, in dem Abstürze gezählt werden |
| `neustarts_im_fenster` | 3 | mehr Abstürze im Zeitraum: der Dienst bleibt aus, bis ihn jemand startet |
| `wiederverbindung_max_s` | 30 | längste Pause zwischen Verbindungsversuchen |
| `macmon` | ja | auf dem Mac Grafik, Temperatur und Leistung über macmon, wenn installiert |

## Was gemessen wird

Speicher auf dem Mac: belegt = (anonyme Seiten - löschbare + fest verdrahtete + Kompressor) mal Seitengröße;
das entspricht den Systemanzeigen. Auf Linux: Gesamt minus verfügbar. Dazu Swap, freie Platte, Last; auf Linux
Prozessorlast und Temperatur, auf dem Mac mit macmon Prozessor, Grafik, Temperatur und Leistung. Je Dienst
der Speicher seiner Prozesse (Mac: physischer Fußabdruck, Linux: PSS).

Die Leitstelle setzt den gemessenen Speicher an die Stelle der Schätzung: was nicht die bekannten Modelle
belegen, gilt als vom System belegt. Die Dienste des Agenten erscheinen in der Leitstelle als Dienst
"Dienste auf <Rechner>"; Starten heißt dort Laden, Anhalten heißt Entladen. Von sich aus hält die Leitstelle
sie nie an, nur auf Knopfdruck.
