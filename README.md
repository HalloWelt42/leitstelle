# Leitstelle

Zentrale Vermittlungsstelle für KI-Dienste im eigenen Netz. Die Leitstelle kennt die Rechner, die
Dienste darauf (Modell-Läufer mit OpenAI-Schnittstelle und Programme wie Sprachsynthese, Spracherkennung,
Bilderzeugung, die der Maschinenraum des Rechners startet und anhält) und externe Anbieter. Anwendungen geben Aufträge ab; die Leitstelle wählt Dienst und Modell,
reiht nach Priorität ein, lädt und entlädt Modelle nach gemessenem Bedarf, schichtet selbst um und zeigt alles
live in einer Oberfläche: wer was rechnet, wer wartet und warum.

Jedes Programm, das die gewöhnliche OpenAI-Schnittstelle spricht, kann sie ohne Umbau nutzen: Adresse auf die
Leitstelle stellen, Schlüssel eintragen, fertig.

## Zusammenspiel mit Maschinenraum und Stellwerk

Leitstelle und [Maschinenraum](https://github.com/HalloWelt42/maschinenraum) gehören zusammen. Der Modell-Läufer
verwaltet die Sprachmodelle eines Rechners, der Maschinenraum die übrigen KI-Dienste (Sprache, Bild, Musik, etwa das
[Klangwerk](https://github.com/HalloWelt42/klangwerk)), jeder mit eigener Oberfläche. Die Leitstelle steht darüber:
Anwendungen sprechen nur noch mit ihr, sie wählt Dienst und Rechner, plant den Speicher und startet oder hält Dienste
über den Maschinenraum des Rechners an. Die eigenen Webapps selbst startet und stoppt das
[Stellwerk](https://github.com/HalloWelt42/stellwerk); sie halten keine Modelle und nutzen KI nur über die Leitstelle.

```
Webapps (Stellwerk)  ->  Leitstelle  ->  Modell-Läufer      (Sprachmodelle)
                                     ->  Maschinenraum      (übrige KI-Dienste, je Rechner)
```

## Was sie kann

- **Fassade im OpenAI-Format** (`/v1/chat/completions` mit und ohne Strom, `/v1/embeddings`, `/v1/models`, dazu
  die Modelllisten des Läufers nachgebildet). Wartet ein Auftrag, kommen Hinweiszeilen statt Zeitüberschreitung;
  ein Abbruch liefert den bisherigen Text.
- **Speicherplanung und Selbststeuerung:** lädt nur, was passt, entlädt nur bei Bedarf und nie, was rechnet;
  leitet um, räumt Leerlauf, weicht in der Kette aus, mit Begründung, Gewinnschwelle und Schutz vor Hin und Her.
  Regeln sind Graphen aus Bausteinen.
- **Hauptregler** für den ganzen Verbund: Normal, Auslaufen, Halt, Hintergrund anhalten.
- **Knoten-Agenten** je Rechner: der [Maschinenraum](https://github.com/HalloWelt42/maschinenraum) (eigenes
  Programm mit Oberfläche) meldet den echten Speicher statt einer Schätzung, und die Leitstelle startet und hält
  über ihn die Dienste an, die nicht über einen Modell-Läufer laufen. Das Protokoll ist offen
  ([docs/PROTOKOLL.md](docs/PROTOKOLL.md) Abschnitt 4.2); andere Agenten sind möglich.
- **Oberfläche** mit lebendigem Netzbild, Aufträgen mit Zeitleiste, Modellen mit Budget, Knoten, Diensten
  (Anschluss per Adresse, alles andere wird erkannt), Anwendungen mit Schlüsseln, Prüfprotokoll; eigene
  Telefonansicht.
- **Geprüft:** Entscheidungskern gegen einen vollständig gemockten Schein-Verbund, Ende zu Ende gegen einen
  Schein-Läufer ([docs/SZENARIEN.md](docs/SZENARIEN.md)); Kosten der Durchleitung gemessen
  ([docs/MESSUNGEN.md](docs/MESSUNGEN.md)).

Was noch kommt (Anmeldung und Signale über den Kanal, Bibliotheken, Regeleditor, Sicherheit, Verlauf): [docs/PLAN.md](docs/PLAN.md).

## Schnellstart

```bash
docker compose up -d --build
```

Dann `http://<rechner>:8530/` öffnen (nur aus privaten Netzen erreichbar), unter Dienste einen Modell-Läufer per
Adresse anschließen, unter Anwendungen eine Anwendung anlegen und deren Schlüssel kopieren. Im Programm die
Basisadresse auf `http://<rechner>:8530/v1` stellen und den Schlüssel als Bearer eintragen. Daten liegen in
`./daten` (oder `LEITSTELLE_DATENORDNER`). Einzelheiten: [docs/SPICKZETTEL.md](docs/SPICKZETTEL.md),
Anbindung eigener Programme: [docs/ANBINDUNG.md](docs/ANBINDUNG.md).

## Ordner

| Ordner | Inhalt |
|---|---|
| `docs/` | [SPICKZETTEL.md](docs/SPICKZETTEL.md), [ANBINDUNG.md](docs/ANBINDUNG.md) Implementierungsanweisung für KI und Menschen, [UMBAU.md](docs/UMBAU.md) Leitfaden der vier Stufen, [PROTOKOLL.md](docs/PROTOKOLL.md), [ARCHITEKTUR.md](docs/ARCHITEKTUR.md), [SZENARIEN.md](docs/SZENARIEN.md) geprüftes Verhalten, [MESSUNGEN.md](docs/MESSUNGEN.md), [PLAN.md](docs/PLAN.md) |
| `backend/` | Python: `leitstelle/kern/` Entscheidungskern, `fach/` Betrieb, Vermittlung, Verzeichnis, Lagebild, `ports/` Ablage (SQLite, Migrationen), Tresor, Dienst-Adapter, Uhr, `api/` Fassade, Verwaltung, Kanal, `protokoll/` Umschlag und Schemata, `simulation/` Schein-Verbund; Tests `tests/` mit Schein-Läufer |
| `frontend/` | Oberfläche in Svelte 5 und TypeScript nach den Entwürfen; Typen aus den Pydantic-Modellen (`npm run typen`) |
| `mockups/` | Entwürfe als Leitfaden der Gestaltung: `index.html` Galerie, `stil.css` Gestaltungsmarken, `ENTWURFSREGELN.md` |
| `tools/` | `ausrollen.sh` auf einen Rechner im Netz, `version.sh`, Git-Hooks, `screenshots.sh`, `seitenstile.py`, `schein_laeufer.py`, `messen_fassade.py` |

Die Beispielwelt in Entwürfen und Tests trägt die Namen der Programme des Autors; sie dient nur als Anschauung.

## Entwürfe ansehen

```bash
cd frontend && npm install && cd ..
./start-mockups.sh start 8535
```

Dann `http://localhost:8535/mockups/index.html` öffnen. Unten in der Mitte lassen sich Thema (dunkel,
hell) und Schriftstufe (normal, groß, sehr groß) umschalten; die Wahl gilt für alle Seiten.
Bilder aller Seiten: `tools/screenshots.sh .run/shots`.

## Kern prüfen

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[test]" && .venv/bin/python -m pytest
```

Alle Tests laufen gegen den Schein-Verbund, nie gegen echte Modelle. Der Katalog der Szenarien mit
Erwartung je Zweig steht in [docs/SZENARIEN.md](docs/SZENARIEN.md).

## Auf einen anderen Rechner ausrollen

```bash
ZIEL=benutzer@rechner tools/ausrollen.sh
```

Lädt den eingecheckten Stand hoch, holt ihn auf dem Zielrechner (Vorgabe `/home/<benutzer>/leitstelle`, mit
`ORDNER=/pfad` und `DATEN=/pfad` einstellbar), baut dort mit Docker und startet. Beim Bauen laufen alle Kern-Tests
und die Typprüfung der Oberfläche; ist etwas rot, bricht der Bau ab und der alte Stand läuft weiter. Ohne `ZIEL`
fragt das Skript das Werkzeug handbuch nach Ziel, Ordner und Datenordner (`handbuch ziel leitstelle`); dort stehen
sie privat, nicht im Repository.

## Gestaltung in Kürze

Bläuliche Flächen, Bernstein (gelb-orange) als einzige Hervorhebung, Zwischenfarben mit je einer
Bedeutung (Himmel: Text, Petrol: Einbettung, Türkis: Übersetzen, Minze: Hören, Flieder: Bild,
Violett: Musik, Rose: Stimme, Koralle: extern, Honig: pausiert, Sand: Werkzeuge und Wartung, Stahl:
Heimnetz). Sanftes Dunkel und mildes Hell mit geprüften Kontrasten. Grundschrift 18 Pixel, nichts
unter 14 Pixel, Zahlen in der Zahlenschrift. Jede Farbe steht mit einem Wort.

## Version

Die Version steht nur in `version.json`; `tools/version.sh patch|minor|major` zählt hoch, der
Pre-Commit-Hook erzwingt es (`git config core.hooksPath tools/git-hooks`).

## Lizenz

**Nicht-kommerzielle Nutzung** - Siehe [LICENSE](LICENSE)

Erlaubt: Private Nutzung, Installation, persönliche Anpassungen, Teilen mit Quellenangabe

Verboten: Kommerzielle Nutzung, Verkauf, Einbindung in kommerzielle Produkte

---

## Unterstützen

Leitstelle ist ein privates Hobby-Projekt. Kein Tracking, keine Werbung, keine Kompromisse.

Wenn dir das Projekt gefällt, kannst du ihm einen Stern geben - oder direkt hier:

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/HalloWelt42)

**Crypto:**

| Coin | Adresse |
|------|---------|
| BTC | `bc1qnd599khdkv3v3npmj9ufxzf6h4fzanny2acwqr` |
| DOGE | `DL7tuiYCqm3xQjMDXChdxeQxqUGMACn1ZV` |
| ETH | `0x8A28fc47bFFFA03C8f685fa0836E2dBe1CA14F27` |

Copyright (c) 2026 HalloWelt42
