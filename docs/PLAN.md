# Plan: Aufbau der Leitstelle in Staffeln

Stand 16.10.2026. Jede Staffel endet mit etwas Benutzbarem, Tests, Sichtprüfung gegen die Entwürfe
und einem Eintrag im Fortschritt. Die Entwürfe unter `mockups/` sind der Leitfaden: Optik ändert sich
zuerst dort, dann im Code.

## Staffel 0: Entwürfe und Verträge (diese Staffel)

- Bestandsaufnahme aller KI-Nutzung im Haus des Autors (privat, nicht im Repository).
- Architektur: [ARCHITEKTUR.md](ARCHITEKTUR.md). Protokoll: [PROTOKOLL.md](PROTOKOLL.md).
  Umbau-Leitfaden: [UMBAU.md](UMBAU.md).
- Gestaltung und 21 Entwurfsseiten unter `mockups/` (Galerie `mockups/index.html`, Server
  `./start-mockups.sh`, Bilder `tools/screenshots.sh`).
- Freigabe der Entwürfe durch den Nutzer; offene Entscheidungen siehe unten. Rückmeldungen vom 16.10.2026
  eingearbeitet: kräftigere Farbwelt (Vorgabe Kräftig), Hauptregler zentral in der Kopfleiste (Normal, Auslaufen,
  Halt), Breitenstufen und eigene Handy-Ansicht, Einstellungen in Untergruppen, Pillen nur für Bedeutsames,
  freigestelltes Kopfsymbol, Blauart wählbar.
- Entscheidungskern vorgezogen (16.10.2026, Wunsch des Nutzers: alle Szenarien und jeden Zweig mit bis zu
  8 Programmen und 5 Anbindungen prüfen, alles gemockt): `backend/leitstelle/kern/` (Zuteiler, Speicherplaner,
  Lage, Messwerk, Umschichter, Bausteine, Auswerter, Vorlagen) und der Schein-Verbund
  `backend/leitstelle/simulation/`; Szenarienkatalog [SZENARIEN.md](SZENARIEN.md) mit allen Tests grün.
- Anbindungsanweisung für KI und Menschen: [ANBINDUNG.md](ANBINDUNG.md). Anwendungen, die nur die gewöhnliche Schnittstelle kennen,
  bleiben dauerhaft über die Fassade verträglich.

## Staffel 1: Kern mit Fassade

Ziel: eine Anwendung ohne Umbau läuft über die Leitstelle gegen den Modell-Läufer auf dem MacBook M4 Max 128 GB.

- Backend `backend/leitstelle/` nach ARCHITEKTUR.md: kern (Modelle, Zustände, Zuteiler, Speicherplaner,
  Lage), fach (Vermittlung, Speicherverwaltung, Signalgeber), ports (Adapter `openai_kompatibel` mit
  nativer Läufer-Schnittstelle für Zustand, Laden und Entladen; Ablage SQLite), vorgaenge (Läufer,
  Aufräumer), api (Fassade `/v1/*`, `/api/*`, `/api/kanal`), protokoll (Umschlag, Schemata).
- Oberfläche Svelte 5 + TypeScript mit den Marken aus `mockups/stil.css`: Übersicht (Netzbild,
  Kennzahlen, Läuft gerade, Speicherlage), Aufträge (Liste, Einzelheiten, Prozesskette, Stoppen mit
  Wahl), Modelle (Tabelle, Speicher freigeben mit Vorschau). Thema hell und dunkel, Schriftstufen.
- Testdaten: Schein-Dienst im OpenAI-Format unter `tests/schein/`.
- Messungen je Auftrag (Ladezeit je Modell und Knoten, Laufzeit, erstes Stück) von Anfang an speichern; die
  Selbststeuerung in Staffel 4 baut darauf.
- Messpunkt: Latenz der Fassade (Zeit bis erstes Stück mit und ohne Leitstelle) und Durchsatz bei 20
  gleichzeitigen Strömen; Ergebnis in `docs/MESSUNGEN.md`. Danach Entscheidung, ob die Durchleitung in
  Python bleibt.
- Erste Anwendung: Codehilfe über die Fassade; zweite: Medienpool (Übersetzung).
- Betrieb auf dem Pi (Entscheidung des Nutzers): Docker-Compose mit Datenordner auf der SSD, Ausrollen per pull
  und compose wie bei TubeVault; Entwicklung lokal auf dem Mac. `version.json`, `tools/version.sh`, Git-Hooks,
  `start.sh`, `docs/SPICKZETTEL.md`.

Stand 16.10.2026 (Fassung 0.4): gebaut, geprüft und auf einem Raspberry Pi in Betrieb.

- Gebaut wie oben, dazu: Verwaltung für Rechner, Dienste (Anschluss hinzufügen mit Erkennung ohne Nebenwirkung),
  Anwendungen (Schlüssel im Tresor, Auge mit Prüfprotokoll, Ketten), Hauptregler mit Grund, Live-Kanal mit
  Lagebild, Zeitleiste je Auftrag, Tageskennzahlen, Speicher freigeben mit Vorschau, Prüfprotokoll; Oberfläche mit
  Übersicht, Aufträgen, Knoten, Diensten, Modellen, Anwendungen, Protokoll und eigenständiger Telefonansicht.
- Der Vorgängerordner `vorgaenge` ist im Betrieb aufgegangen (Takt, Abgleich, Laden); `start.sh` entfällt, gestartet
  wird über Docker Compose auf dem Pi und lokal über die Startkonfigurationen (SPICKZETTEL).
- Messpunkt erledigt: [MESSUNGEN.md](MESSUNGEN.md). Die Durchleitung bleibt in Python.
- Offen und mit dem Nutzer gemeinsam: den echten Modell-Läufer des Mac anschließen und die erste Anwendung
  (Codehilfe, dann Medienpool) auf die Fassade umstellen. Beide Schritte verändern fremde Konfigurationen und
  gehören in die gemeinsame Sitzung "erste Schritte".

## Staffel 2: Knoten-Agent

- Python-Agent (Entscheidung 16.10.2026; seit 16.10.2026 eigenes Programm Maschinenraum, Repo HalloWelt42/maschinenraum): Messwerte (Prozessor, Speicher, Swap, Platte, Netz; auf dem Mac dazu Grafik,
  Leistung, Temperatur, Lüfter nach den Messwegen aus Leitwarte; auf dem Pi Temperatur aus
  `/sys/class/thermal`), Entdeckung bekannter Dienste (Ports 1234, 10031, 8188, 8766, 8765 und
  Prozesse), Befehle (Dienst starten, anhalten, Messtakt), Anmeldung mit eigenem Schlüssel,
  Wiederverbindung, launchd und systemd.
- Installationsbefehl je Plattform, der sich selbst anmeldet (Seite "Erster Start").
- Oberfläche: Knoten (Karten mit Ringen und Verläufen), Knoten-Einzelheiten (Speicher nach Modellen,
  Dienste, Aufträge, Regeln je Knoten), Dienste.
- Speicherplaner wartet auf die echte Freimeldung des Agenten statt auf feste Pausen.

## Staffel 3: Protokoll, Bibliotheken, erster Umbau

- WebSocket-Kanal vollständig (Anmeldung, Herzschlag, Signale, Fragen, Reservierung).
- `leitstelle-client` für Python und TypeScript mit denselben JSON-Schemata; Beispielanwendung.
- Fundus auf Stufe 3 umbauen (Signale drosseln die Masseneinbettung), danach Zusage; Modell-Manager
  in beiden zurückbauen.
- Oberfläche: Anwendungen (Liste, Einzelheiten mit Zugang, Rechten, Ketten, Signalen), Anwendung
  anmelden (Schritte), Nachrichtenverkehr (Strom, Umschlag, Bedeutung).

## Staffel 4: Weitere Dienste und Regeln

- Adapter: txt2voice (stimme, stimme_klonen, hoeren), hoeren_http (Mitschrift, eigene
  Whisper-Dienste), bildwerkbank (Bildschmiede: erzeugen, freistellen), sprecher_klein (Piper auf dem
  Pi), musik (Klangschmiede), extern_openai (Externer Anbieter mit Kosten je Token).
- Regeln vollständig (Prioritäten, Fairness, Speicher je Knoten, Zeitgrenzen, Zeitfenster, Extern)
  mit Wirkungsvorschau.
- Selbststeuerung (ARCHITEKTUR 5.6): der Kern liegt seit Staffel 0 vor und ist gegen den Schein-Verbund
  geprüft; hier kommt die Anbindung an echte Adapter und Agenten (Vollzug), Rückgängig in der Oberfläche
  und der Dauerlauf gegen Schein-Dienste über das Netz.
- Regelwerk als Graph (ARCHITEKTUR 5.7): Bausteine-Registry, Auswerter und Vorlagen liegen vor (Staffel 0);
  hier Trockenlauf über die Schnittstelle, Fassungen in der Ablage, Editor mit Svelte Flow und der
  Techbaum-Anordnung aus Orbit.
- TubeVault: Transkripte und Nachvertonung als Hintergrund-Aufträge mit Abschnitten; Nachvertoner
  entfällt. Rufzeichen mit Direktweg.

## Staffel 5: Sicherheit

- Zonen und Herkunftsprüfung, Rate je Anwendung, Passkey-Anmeldung der Oberfläche mit Einmalcode als
  Rückfall, HTTPS mit eigenem Zertifikat und Anleitung, verschlüsselte Geheimnisse mit Auge und
  Prüfprotokoll, Schlüssel externer Anbieter nur noch hier.
- Durchsicht mit mehreren Prüfagenten je Bereich (Zugänge, Aufträge, Knotenbefehle, Fassade), die nur
  berichten.

## Staffel 6: Verlauf, Hilfe, Doku

- Verdichtung der Messwerte, Diagramme (Aufträge je Stunde, Wartezeit, Speicher, Token, Kosten,
  Anwendungen, Modelle, Lage), Aufbewahrung.
- Protokoll als schwebendes Fenster, Hilfe als schwebendes Fenster mit Suche und Tiefenlinks an allen
  erklärungsbedürftigen Stellen, Begriffe-Glossar.
- Einstellungen knapp; Sicherung; Aktualisierungshinweis.
- Doku: README nur Ist-Zustand, SPICKZETTEL, ANLEITUNG zum Nachbau, Bilder je Thema hell und dunkel.

## Staffel 7: Umbau der übrigen Anwendungen und Rückbau

- Nach dem Umbau-Leitfaden: Medienpool, Kiste, Pinnwand, Bildschmiede, Mitschrift, Pappagei, Buchbote,
  BuecherFreunde, Learn-e-Versum, Strukturblick, Federflink, devradar, Erweiterungen, bombel.
- Rückbau der Doppelstrukturen: Modell-Manager, Zeitgrenzen-Regeln, Modell-Autowahl, Ausweichlisten.
- Messung nach einer Woche Betrieb: Wartezeiten, Speicherwechsel, Fehler; Regeln nachziehen.

## Offene Entscheidungen für den Nutzer

1. Name: ENTSCHIEDEN 16.10.2026, Leitstelle.
2. Betriebsort: ENTSCHIEDEN 16.10.2026, der Nutzer will das System allgemein auf dem Pi (Pi Archiv in Docker, Datenordner auf der SSD).
3. Sprache des Knoten-Agenten: ENTSCHIEDEN 16.10.2026, Python (eine Sprache im Projekt).
4. Oberfläche: Passkey-Anmeldung schon in Staffel 1 oder erst in Staffel 5 (bis dahin nur Heimnetz).
5. Externe Anbieter: nur Externer Anbieter zu Beginn, oder von Anfang an ein allgemeiner
   OpenAI-kompatibler Anbieter mit Kostenmodell.

## Entschieden am 16.10.2026

Name Leitstelle, Betriebsort Pi, Agent in Python, Farbwelt Kräftig, Blauart Königsblau. Offen bleiben 4 und 5.

## Fortschritt

| Staffel | Stand |
|---|---|
| 0 | fertig bis auf Freigabe der Entwürfe (16.10.2026): Bestand, Architektur, Protokoll, Umbau, Entwürfe, Entscheidungskern mit Schein-Verbund und Szenarienkatalog, Anbindungsanweisung |
| 1 | gebaut und auf dem Pi in Betrieb (16.10.2026, 0.4): Kern, Fassade, Verwaltung, Oberfläche, Messpunkt; offen: echter Läufer und erste Anwendung gemeinsam mit dem Nutzer |
| 2 | Knoten-Agent gebaut (16.10.2026, 0.6), seit 0.7 als eigenes Programm Maschinenraum mit Oberfläche und Menüleistensymbol: misst Speicher, Swap, Last, Platte, mit macmon Grafik, Temperatur, Leistung; startet und hält Prozessdienste an (eigene Gruppe, Umgebung, Protokoll), Sollzustand übersteht Neustarts, begrenzte Neustarts nach Absturz, Übernahme fremd gestarteter Dienste; Oberfläche Knoten mit Ringen und Feld für den Maschinenraum. Offen: Netz und Lüfter, Verläufe und Knoten-Einzelheiten, Speicherplaner wartet auf die echte Freimeldung, Erster-Start-Seite |
| 3 bis 7 | offen |
