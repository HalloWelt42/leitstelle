# Bausteine für die Oberfläche (aus den Entwürfen abgeleitet)

Beim Bau der 20 Entwurfsseiten sind neben den Bausteinen in `stil.css` seitenlokale Formen entstanden,
die mehrfach vorkommen. Sie werden in Staffel 1 Komponenten der Svelte-Oberfläche; bis dahin bleiben sie
in den Seiten, damit die Entwürfe unverändert als Leitfaden taugen. Jede Zeile nennt den Baustein, wo er
heute steht und was die Komponente leisten muss.

## Schon in `stil.css` und `gemeinsam.js` (werden Komponenten 1:1)

Schale (Kopf, Seitenleiste, Fußleiste, Lage-Marke), Seitenkopf mit Kennzahlen, Rollfeld und Spalten,
Knöpfe, Chips, Reiter, Zustands-, Fähigkeits- und Zonen-Marken (`zustand()`, `faehigkeit()`, `zone()`),
Hinweis, Bestätigen-Leiste, Meldung, Balken (lebt, unbestimmt), Speicherbalken mit Legende, Ring,
Verlauf (Sparkline), Prozesskette, Einstellungszeile, Schalter, Stufenknöpfe, Hilfepunkt, Tabelle,
Fenster (Kopf, Inhalt, Fuß, Griff), Schleier und Dialog, Wahlkarten, Protokollzeile, Leerer Zustand,
Netzbild (`netzbild.js`).

## Mehrfach lokal gebaut, werden eigene Komponenten

| Baustein | Vorkommen | Leistung der Komponente |
|---|---|---|
| Auftragszeile `.auftrag` (Symbol in Fähigkeitsfarbe, Titel, Zweitzeile, Balken, Rest, Priorität, Knöpfe) | uebersicht, auftraege, auftrag-stoppen, knoten-detail, anwendung-detail | eine Zeile je Auftrag in jedem Zustand; Knöpfe nach Zustand und `pausierbar`; gewählt-Zustand |
| Angaben-Raster `.angaben` (dt/dd) | auftraege, modelle, sicherheit, uebersicht-leer | Begriff links, Wert rechts, Werte dürfen Marken enthalten |
| Zeitleiste `.zeitleiste` (Zeit, Punkt, Text; Signal-Zeilen hervorgehoben) | auftraege, knoten-detail, anwendung-detail | Ereignisse eines Auftrags, Knotens oder einer Anwendung |
| Detail-Kopf (Zurück, Titel, Marken, Unterzeile, Aktionen) | knoten-detail, anwendung-detail, anwendung-anmelden | Kopf jeder Einzelansicht |
| Priorität als Wort mit Farbe `.prio` | auftraege, anwendungen, anwendung-detail | Wort aus `WORT.prioritaet`, Farbe nach Stufe |
| Signalzeile (Papierflieger oder Eingangspfeil, Art als `code`, Worte, Zeit oder Zähler) | auftraege, anwendung-detail, nachrichten | eine Nachricht in Kurzform; Richtung und Gruppe farbig |
| Umschlag-Anzeige (eingefärbtes JSON, Schlüssel, Zeichenketten, Zahlen) | auftrag-stoppen, nachrichten, anwendung-anmelden | Umschlag lesbar in 16 px, kopierbar, Zeilen umbrechen nur an Leerzeichen |
| Code-Block mit Kopfzeile und Kopieren | uebersicht-leer, anwendung-anmelden, auftrag-stoppen | Befehle und Schnipsel, Zeilenumbruch an Leerzeichen, Farben für Schlüsselwort, Zeichenkette, Kommentar |
| Diagramm (Säulen, Linien, Fläche, Budgetlinie, Jetzt-Marke, Achsen 15 px, Legende mit Wörtern) | knoten-detail, verlauf | gemeinsames `diagramme.js` neben `netzbild.js`; Zeitachsen mit Uhrzeiten |
| Zustandsstreifen (Abschnitte bereit, rechnet, pausiert, nicht erreichbar; Lage über den Tag) | dienste, verlauf | Zeitstreifen mit Legende, Dauer je Abschnitt im title |
| Schrittfolge (Schrittleiste mit Nummernkreisen, Karten erledigt, jetzt, offen) | uebersicht-leer, anwendung-anmelden | Ablauf mit Fortschritt, erledigte Schritte zusammengeklappt mit Zusammenfassung und Ändern |
| Umbau-Stufenanzeige (vier Segmente) | anwendungen, anwendung-detail | Stufe aus `ANWENDUNGEN.stufe`, Wort aus `WORT_STUFE` |
| Schlüsselfeld (verdeckt, Auge deckt auf, Kopieren, Neu erzeugen mit Bestätigung) | anwendung-detail, sicherheit | stabil, Auge deckt auf, Kopieren liefert immer den vollen Wert, Rotation nur bestätigt |
| Budgetmarke auf dem Speicherbalken | modelle, knoten-detail | senkrechte Marke mit Beschriftung |
| Einstellungszeile breit (Wertspalte auto oder volle Breite) und schmal (Seitenspalte) | einstellungen, regeln, knoten-detail, dienste | Varianten der Einstellungszeile ohne Sonderfälle in den Seiten |
| Gruppe mit Kopf (Symbol, Titel, leiser Hinweis rechts), Gefahrenzone | einstellungen, regeln, sicherheit | Rahmen für Einstellungsgruppen |
| Filterzeile (Reiter links, Auswahlfelder und Suche rechts) | auftraege, nachrichten, modelle, dienste | eine Zeile über Listen |
| Kennzahl-Varianten (warnung, extern, pausiert) | modelle, verlauf, dienste | Farbe nach Bedeutung, Zahlen in `small` ohne Versalien |
| Tabellenzeile gewählt, Zweitzeile in Zellen, dichte Tabelle | modelle, anwendungen, sicherheit, hilfe | `tr.gewaehlt`, `.zweit`, `.tabelle.dicht` |

## Festlegungen aus den Entwürfen

- `.wahl`-Karten enthalten Marken als `inline-flex`; nur der Erklärungstext ist ein Block.
- Fensterschrift mindestens `--ls-gr-klein`; Protokollzeilen mit Bereichsspalte 132 px.
- Höchstens drei bewegte Dinge je Bildschirm; Listen mit vielen Sparklines ohne blinkenden Endpunkt.
- Die Schale nimmt je Szenario Zahlen entgegen (Fußleiste, Navi-Zähler, Knotenpunkt); in der App kommen
  sie aus dem Live-Zustand.
- Thema "System" folgt `prefers-color-scheme`; Schriftstufe und Bewegung liegen als `data-*` am `<html>`.
