# Entwurfsregeln der Leitstelle-Mockups

Diese Datei ist der Vertrag für alle Entwurfsseiten unter `mockups/`. Wer eine Seite baut oder ändert,
hält sich daran, damit die Seiten untereinander konsistent bleiben.

## Aufbau einer Seite

- Eine Datei je Zustand, zum Beispiel `knoten.html`, `knoten-detail.html`, `auftrag-stoppen.html`.
- Kopf wie in `uebersicht.html`: `<link>` auf `../frontend/node_modules/@fortawesome/fontawesome-free/css/all.min.css`
  und auf `stil.css`, `<link rel="icon" href="symbol.svg">`, Titel `Leitstelle - Entwurf: <Seite>`.
- Rumpf: `<div class="schale">` mit `[data-block="kopf"]`, `[data-block="seite"]`, `<main class="haupt rahmen" id="haupt">`,
  `[data-block="fuss"]`. Dann `<script type="module">`, das `seite('<navi-schluessel>')` aus `gemeinsam.js` aufruft und
  den Hauptbereich füllt. Navi-Schlüssel: uebersicht, auftraege, knoten, dienste, modelle, anwendungen, regeln,
  nachrichten, verlauf, sicherheit, protokoll, einstellungen, hilfe.
- Fester Kopf, eigenes Rollfeld: `.rahmen-kopf` (Titel, Kennzahlen, Filter) plus `.rollfeld` oder `.spalten` mit zwei
  Rollfeldern. Die Seite selbst rollt nie.
- Seitenspezifisches CSS in `<style>` im Kopf der Seite. `stil.css` und `gemeinsam.js` werden von Seitenautoren NICHT
  geändert; fehlt ein Baustein, wird er lokal gebaut und im Bericht genannt, damit er später in `stil.css` wandert.

## Daten

- Nur die Beispielwelt aus `gemeinsam.js` (KNOTEN, DIENSTE, MODELLE, ANWENDUNGEN, AUFTRAEGE). Keine neuen Rechner,
  Dienste, Modelle oder Anwendungen erfinden. Zahlen im Kopf, in der Fußleiste und auf den Seiten müssen zusammenpassen
  (3 laufen, 2 warten, 1 pausiert, 67 heute fertig, 1 Fehler, 5 von 6 Knoten, Mac Studio 96 Prozent, extern 0,42 Euro).
- Wörter statt Schlüssel: Zustände, Fähigkeiten, Zonen und Prioritäten immer über `WORT` ausgeben oder die Bausteine
  `zustand()`, `faehigkeit()`, `zone()` nutzen. Nie `laeuft` oder `wartet_speicher` drucken.
- Zahlen in der Zahlenschrift (`.zahl`), deutsches Format (1.240, 84,7 GB, 0,42 Euro, 14:56).

## Gestaltung

- Nur Marken `--ls-*`, keine festen Farben oder Größen. Akzent Bernstein nur für die Hauptsache einer Ansicht.
- Jede Farbe steht mit einem Wort oder Symbol, nie allein.
- Keine einseitigen Ränder, keine Leuchtleisten, kein `!important`, keine Browser-Dialoge. Bestätigungen als
  `.bestaetigen`-Leiste auf der Seite oder `.dialog` mit `.schleier`.
- Schrift: nichts unter `--ls-gr-marke`. In SVG-Diagrammen Beschriftungen mindestens 15 px im gezeichneten Maßstab.
- Jeder Knopf, Regler und jedes Feld, dessen Wirkung nicht selbstverständlich ist, bekommt ein `title` mit einem Satz
  (was es tut, welche Folge). Mini-i-Knopf `hilfepunkt('<Thema>')` für Tiefe.
- Hinweistexte in Karten kurz halten (höchstens zwei Zeilen), voller Satz ins `title`.
- Lebendigkeit: laufende Balken `.balken.lebt`, Prozessketten `.kette` mit `.pfeil.laeuft`, Netzbild aus `netzbild.js`,
  Verläufe mit `verlauf()`, Ringe mit `ring()`, pulsierende `.punkt.lebt`. Nicht übertreiben: höchstens drei bewegte
  Dinge je Bildschirm, alles gehorcht `prefers-reduced-motion`.
- Keine Abkürzungen in sichtbaren Texten, echte Umlaute, keine typografischen Anführungszeichen, kein Gedankenstrich.
- Keine fremden Marken in Oberflächentexten. Der lokale Modell-Dienst heißt "Modell-Läufer", externe Anbieter heißen
  neutral ("Externer Anbieter" ist als Dienstname erlaubt, weil es der Name der Anbindung ist).

## Breitenstufen und Handy

- Die Schreibtisch-Ansicht gilt von 1600 px abwärts: ab 1440 px dichter, ab 1240 px einspaltig mit
  Symbol-Seitenleiste, ab 980 px ohne Suche und Nebenknöpfe (Regeln in `stil.css`, Abschnitt Breitenstufen).
  Seitenlokale Raster nie starr (`repeat(3, 1fr)`), immer `repeat(auto-fit, minmax(…, 1fr))`.
- Telefone bekommen eine eigenständige, reduzierte Ansicht (`mobil.html`): nur Lage, Hauptregler, Aufträge
  stoppen, Knoten, Meldungen; Folgenreiches nur mit Drücken und Halten. Nie den Schreibtisch quetschen.
- Prüfung in drei Breiten: `BREITE=1280 tools/screenshots.sh …` und `BREITE=1024 …` neben 1600.

## Hauptregler, Pillen, Untergruppen

- Der Hauptregler (Normal, Auslaufen, Halt, Hintergrund) steht in der Kopfleiste jeder Seite und kommt aus
  `gemeinsam.js` (`seite(..., { modus, leiste })`). Halt und Auslaufen zeigen vor dem Tun eine Leiste mit Folgen.
- Pillen in Seitenleiste und Reitern zeigen nur, wo etwas Bedeutsames passiert (nicht erreichbar, pausiert,
  wartet, Fehler, getrennt), nie Gesamtzahlen; Farbe nach Bedeutung, Erklärung im title.
- Lange Einstellungsseiten teilen sich in Untergruppen (`untergruppen.js`): Reiter im festen Kopf, eine Gruppe
  sichtbar, kein langes Rollen.

## Farbwelten

- `data-palette`: sanft, kraeftig (Vorgabe, Nutzerwahl 16.10.2026), leuchtend; `data-flaechen`: blaugrau,
  tiefblau; `data-blau`: koenig (Vorgabe, Nutzerwahl 16.10.2026), himmel, azur, kornblume. Alle als Marken in `stil.css`, umschaltbar im Entwurf,
  frühere Fassungen bleiben erhalten.

## Prüfung

- `tools/screenshots.sh .run/shots <seite>` fotografiert die Seite dunkel und hell (1600 x 1000). Beide Bilder ansehen:
  Überlappungen, abgeschnittene Texte, zu kleine Schrift, Kontrast.
- Der Entwurfs-Server läuft über `./start-mockups.sh` auf Port 8535 und liefert die Projektwurzel aus.

## Protokoll-Kurzfassung (für Seiten, die Nachrichten zeigen)

Offenes, einfaches, erweiterbares Protokoll "Leitstelle/1". Jede Nachricht ist ein Umschlag in JSON:

```json
{
  "protokoll": "leitstelle/1",
  "art": "auftrag.anlegen",
  "id": "9f1c7e0a3b4d4c6e8e2a1f5b7d9c0e21",
  "zeit": "2026-10-16T14:56:12.431+02:00",
  "von": "anwendung:zusage",
  "an": "leitstelle",
  "bezug": "id eines Auftrags oder einer Nachricht (optional)",
  "nutzlast": { }
}
```

Transport: HTTP `POST /api/nachrichten` für Frage und Antwort, WebSocket `/api/kanal` für beide Richtungen mit
demselben Umschlag, dazu die OpenAI-Fassade `/v1/*` für Anwendungen ohne Umbau. Unbekannte Arten und Felder werden
ignoriert, Erweiterungen tragen die Vorsilbe `x-`. Rollen: `anwendung`, `dienst`, `knoten`, `leitstelle`.

Nachrichtenarten der ersten Fassung:

| Gruppe | Arten | Richtung |
|---|---|---|
| Anmeldung | `anwendung.anmelden`, `anwendung.angemeldet`, `anwendung.abmelden`, `herzschlag` | beide |
| Knoten | `knoten.messwerte`, `knoten.dienste`, `knoten.befehl`, `knoten.befehl_ergebnis` | Agent meldet, Leitstelle befiehlt |
| Dienst | `dienst.anmelden`, `dienst.zustand`, `dienst.modell` (geladen, entladen, lädt) | Dienst an Leitstelle |
| Auftrag | `auftrag.anlegen`, `auftrag.angenommen`, `auftrag.abgelehnt`, `auftrag.laeuft`, `auftrag.fortschritt`, `auftrag.stueck`, `auftrag.ergebnis`, `auftrag.fehler`, `auftrag.abgebrochen` | Anwendung legt an, Leitstelle meldet |
| Steuerung | `auftrag.anhalten`, `auftrag.fortsetzen`, `auftrag.stoppen` (Modus auslaufen oder sofort), `auftrag.prioritaet` | Anwendung oder Oberfläche an Leitstelle |
| Signale | `signal.speicher` (frei, knapp, voll; frei_gb, knoten), `signal.gesperrt`, `signal.freigegeben`, `signal.pausiert`, `signal.fortgesetzt`, `signal.modell` (bereit, wird_geladen, entladen), `signal.lage` (ruhig, angespannt, engpass), `signal.kosten`, `signal.zone` | Leitstelle an Anwendung oder Dienst |
| Fragen | `frage.kapazitaet` (kann ich jetzt?), `frage.modelle`, `frage.auftrag` mit `antwort.*` | Anwendung fragt, Leitstelle antwortet |
| Reservierung | `reservierung.anfragen`, `reservierung.bestaetigt`, `reservierung.abgelehnt`, `reservierung.freigeben` | beide |
