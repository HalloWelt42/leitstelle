# Leitstellen-Protokoll, Fassung 1 (`leitstelle/1`)

Offen, einfach, erweiterbar. Ein Umschlag für alles: Aufträge, Signale, Messwerte, Befehle, Fragen.
Dieselbe Form läuft innerhalb der Leitstelle als Ereignis, über den Kanal zu den Anwendungen, von den
Knoten-Agenten herein und in die Oberfläche "Nachrichtenverkehr". Was man dort sieht, ist genau das,
was gesprochen wird.

## 1. Grundsätze

1. **Ein Umschlag.** Jede Nachricht hat dieselben Kopffelder; der Inhalt steht in `nutzlast`.
2. **JSON, UTF-8, Zeit mit Zeitzone.** Keine Binärdaten im Umschlag; Dateien gehen über
   Verweise (`datei_url`) oder die Fassade (multipart).
3. **Beide Richtungen, gleichberechtigt.** Anwendungen schicken Aufträge und Fragen; die Leitstelle
   schickt Zustände, Fortschritt, Ergebnis und Signale. Dienste und Knoten melden sich genauso an.
4. **Unbekanntes wird ignoriert.** Unbekannte Arten und Felder sind kein Fehler. Erweiterungen tragen
   die Vorsilbe `x-` (zum Beispiel `x-tubevault-video_id`). Eine neue Fassung bekommt eine neue
   `protokoll`-Kennung; die Leitstelle spricht alle, die sie kennt.
5. **Wörter statt Codes.** Zustände und Gründe sind Werte aus Listen mit festen Wörtern; die
   Oberfläche übersetzt sie, Anwendungen können sie ebenfalls anzeigen.
6. **Jede Nachricht ist eigenständig.** Sie enthält, was zum Verstehen nötig ist (Auftrags-Kennung,
   Knoten, Zahlen), nicht nur einen Verweis.
7. **Idempotent, wo es zählt.** `auftrag.anlegen` trägt eine von der Anwendung erzeugte `id`; ein
   zweites Anlegen mit derselben `id` legt keinen zweiten Auftrag an.

## 2. Umschlag

```json
{
  "protokoll": "leitstelle/1",
  "art": "auftrag.anlegen",
  "id": "9f1c7e0a3b4d4c6e8e2a1f5b7d9c0e21",
  "zeit": "2026-10-16T14:56:12.431+02:00",
  "von": "anwendung:zusage",
  "an": "leitstelle",
  "bezug": "a7d3c9e1f0b24d6a8c5e2f1b9d0a7c33",
  "nutzlast": { }
}
```

| Feld | Pflicht | Bedeutung |
|---|---|---|
| protokoll | ja | Fassungskennung, hier `leitstelle/1` |
| art | ja | Nachrichtenart `gruppe.verb`, Kleinbuchstaben |
| id | ja | 32 Hex-Zeichen (UUID ohne Striche), vom Absender erzeugt |
| zeit | ja | ISO 8601 mit Zeitzone und Millisekunden |
| von | ja | `rolle:kennung`; Rollen `anwendung`, `dienst`, `knoten`, `leitstelle`, `oberflaeche` |
| an | ja | Empfänger in derselben Form; `leitstelle` für den Kern |
| bezug | nein | Kennung des Auftrags oder der Nachricht, auf die sich diese bezieht |
| nutzlast | ja | Inhalt je Art, siehe unten; darf leer sein |

## 3. Transport

| Weg | Wofür | Form |
|---|---|---|
| WebSocket `/api/kanal` | Dauerverbindung für beide Richtungen: Signale, Fortschritt, Stücke, Herzschlag | Textrahmen, je Rahmen ein Umschlag; Anmeldung als erste Nachricht; Schlüssel im Kopf `Authorization: Bearer` oder in `anwendung.anmelden` |
| HTTP `POST /api/nachrichten` | Frage und Antwort ohne Dauerverbindung (Auftrag anlegen, Kapazität fragen, Steuerung) | Anfrage ist ein Umschlag, Antwort ist ein Umschlag; Streams als SSE mit einem Umschlag je Ereignis |
| HTTP `/v1/*` (Fassade) | Anwendungen ohne Umbau | OpenAI-Format; die Leitstelle wandelt intern in Umschläge |
| HTTP `GET /api/nachrichten?...` | Oberfläche und Werkzeuge lesen den Verkehr seitenweise | Liste von Umschlägen mit Filtern (ab, anzahl, art, teilnehmer, richtung) |

Transportsicherheit: Knoten-Agenten und Dienste außerhalb des Heimnetzes sprechen die Leitstelle nur über TLS
(`wss://`, `https://`) an; der Agent prüft das beim Installieren hinterlegte Zertifikat der Leitstelle. Im Heimnetz
ist Klartext für Anwendungen erlaubt, TLS wird angeboten und bevorzugt.

Verbindungen gehen immer von außen zur Leitstelle: Anwendungen, Dienste und Knoten-Agenten
verbinden sich; die Leitstelle öffnet keine Ports auf fremden Rechnern. Bricht die Verbindung ab,
verbindet sich die Gegenseite neu und bekommt mit `anwendung.angemeldet` den aktuellen Stand ihrer
Aufträge zurück. Verpasste Signale werden nicht nachgeliefert; der Stand ersetzt sie.

Herzschlag: alle 10 Sekunden (einstellbar) von jeder Dauerverbindung; Herzschläge und periodische Messwerte werden gespeichert, aber im Nachrichtenverkehr der Oberfläche standardmäßig ausgeblendet. Ohne Herzschlag gilt eine
Anwendung nach der eingestellten Frist (Vorgabe 60 s) als getrennt, ein Knoten nach 15 s als nicht
erreichbar. Laufende Aufträge einer getrennten Anwendung laufen weiter; das Ergebnis wartet, bis sie
wiederkommt oder die Aufbewahrung endet.

## 4. Nachrichtenarten

### 4.1 Anmeldung

| Art | Richtung | Nutzlast |
|---|---|---|
| `anwendung.anmelden` | Anwendung an Leitstelle | `name`, `version`, `bibliothek` (Name und Fassung), `faehigkeiten` (gewünscht), `signale` (true, wenn die Anwendung Signale verarbeitet), `herkunft` (Adresse), optional `x-*` |
| `anwendung.angemeldet` | Leitstelle an Anwendung | `kennung`, `rechte` (erlaubte Fähigkeiten, Zonen, Priorität, Kostengrenze), `ketten` je Fähigkeit, `auftraege` (Stand aller offenen Aufträge dieser Anwendung), `lage`, `herzschlag_s` |
| `anwendung.abgelehnt` | Leitstelle an Anwendung | `grund` (unbekannter_schluessel, gesperrt, herkunft_nicht_erlaubt) |
| `anwendung.abmelden` | Anwendung an Leitstelle | leer; laufende Aufträge laufen weiter |
| `herzschlag` | beide | optional `last` (frei formulierbar, zum Beispiel offene Aufträge) |
| `dienst.anmelden` | Dienst oder Adapter an Leitstelle | `name`, `art`, `knoten`, `adresse`, `faehigkeiten`, `modelle` (Liste mit Name, Aliasse, Fähigkeit, Größe, Kontext, Zustand), `besonderheiten` |
| `dienst.zustand` | Dienst an Leitstelle | `zustand` (bereit, rechnet, pausiert, nicht_erreichbar), `auftraege_aktiv` |
| `dienst.modell` | Dienst an Leitstelle | `modell`, `zustand` (laedt, geladen, entladen, frei), `groesse_gb` |

### 4.2 Knoten

| Art | Richtung | Nutzlast |
|---|---|---|
| `knoten.anmelden` | Agent an Leitstelle, erste Nachricht nach dem Verbinden | `name`, `betriebssystem`, `architektur`, `speicher_gb`, `agent_version`, `messwege` (Liste der verfügbaren Messungen) |
| `knoten.angemeldet` | Leitstelle an Agent, mit `bezug` | `knoten` (Kennung), `name` |
| `knoten.messwerte` | Agent an Leitstelle, im Takt (Vorgabe 5 s); nicht im Nachrichtenverkehr der Oberfläche | `speicher_gesamt_gb`, `speicher_belegt_gb`, `swap_belegt_gb`, `swap_gesamt_gb`, `cpu_prozent`, `last_1m`, `platte_frei_gb`, `grafik_prozent`, `temperatur_c`, `leistung_w`; alles in GiB; fehlende Werte sind null, nie genullt |
| `knoten.dienste` | Agent an Leitstelle, bei jeder Änderung und spätestens alle zehn Takte | `dienste`: je Dienst `kennung`, `name`, `faehigkeiten`, `port`, `zustand` (aus, startet, laeuft, stoppt, gestoert), `fremd` (läuft, aber nicht vom Agenten gestartet), `gb` (gemessen, sonst Höchstwert oder Schätzung), `gemessen`, `meldung` |
| `knoten.befehl` | Leitstelle an Agent | `befehl` (dienst_starten, dienst_anhalten), `ziel` (Kennung des Dienstes); Befehle sind auf die Dienstverwaltung begrenzt |
| `knoten.befehl_ergebnis` | Agent an Leitstelle, mit `bezug` auf den Befehl | `befehl`, `ziel`, `erfolg`, `meldung`; ein Start antwortet erst, wenn der Dienst erreichbar ist oder seine Startzeit verstrichen ist |
| `knoten.angemeldet`, `knoten.getrennt` | Leitstelle an Oberfläche | `knoten`, `name`; bei der Anmeldung dazu die Angaben aus `knoten.anmelden` |

Transport: WebSocket `/agent/kanal` mit dem Schlüssel des Agenten als Bearer. Unbekannter Schlüssel: Schließen mit
Code 4401 und Grund `unbekannter_schluessel`; ein neu erzeugter Schlüssel trennt den verbundenen Agenten mit
`schluessel_erneuert`. Die Modelle der Nutzlasten stehen in `backend/leitstelle/protokoll/knoten.py`; der Agent
führt einen Spiegel, den ein Test deckungsgleich hält.

### 4.3 Aufträge

| Art | Richtung | Nutzlast |
|---|---|---|
| `auftrag.anlegen` | Anwendung an Leitstelle | `faehigkeit`, `titel` (für Menschen), `eingabe` (je Fähigkeit, siehe 5), `modell` oder `kette` (optional, sonst Kette der Anwendung), `prioritaet` (optional), `streaming` (true/false), `anhaltbar` (true, wenn die Anwendung mit Pausen leben kann), `frist` (optional, bis wann sinnvoll), `x-*` |
| `auftrag.angenommen` | Leitstelle an Anwendung | `auftrag` (Kennung), `platz` in der Warteschlange, `zustand` (eingereiht, zugeteilt, wartet_speicher), `voraussichtlich_start_s`, `zuteilung` (Dienst, Modell, Knoten, Zone) wenn bekannt, `begruendung` |
| `auftrag.abgelehnt` | Leitstelle an Anwendung | `grund` (faehigkeit_nicht_erlaubt, zone_nicht_erlaubt, kostengrenze, kontingent, gesperrt, kein_dienst), `begruendung` |
| `auftrag.laeuft` | Leitstelle an Anwendung | `auftrag`, `zuteilung`, `gestartet` |
| `auftrag.fortschritt` | Leitstelle an Anwendung | `auftrag`, `prozent` (0 bis 100 oder null), `schritt` (Wort), `abschnitt`, `abschnitte`, `rest_s` (Schätzung), `token`, `token_s` |
| `auftrag.stueck` | Leitstelle an Anwendung | `auftrag`, `folge` (laufende Nummer), `inhalt` (Textstück oder Verweis auf Datenblock), `rolle` (text, denken, werkzeugaufruf) |
| `auftrag.ergebnis` | Leitstelle an Anwendung | `auftrag`, `ergebnis` (je Fähigkeit, siehe 5), `messung` (Dauer, erstes Stück, Token rein und raus, Modell, Dienst, Knoten, Kosten) |
| `auftrag.fehler` | Leitstelle an Anwendung | `auftrag`, `grund` (Wort), `meldung` (Text des Dienstes), `wiederholbar` (true/false), `teilergebnis` (optional) |
| `auftrag.abgebrochen` | Leitstelle an Anwendung | `auftrag`, `grund`, `teilergebnis` (bisher Erzeugtes), `speicher_frei_in_s`; nur bei sofortigem Stopp. Beim Auslaufen endet der Auftrag normal mit `auftrag.ergebnis`, und die Anwendung erhält `signal.gesperrt` (bis auf Widerruf nichts Neues) |
| `auftrag.pausiert`, `auftrag.fortgesetzt` | Leitstelle an Anwendung | `auftrag`, `grund` (nutzer, regel_hintergrund, lage, dringend_vor) |

### 4.4 Steuerung

| Art | Richtung | Nutzlast |
|---|---|---|
| `auftrag.anhalten` | Anwendung oder Oberfläche an Leitstelle | `auftrag`; Antwort `auftrag.pausiert` oder `auftrag.fehler` mit Grund `nicht_anhaltbar` |
| `auftrag.fortsetzen` | dito | `auftrag` |
| `auftrag.stoppen` | dito | `auftrag`, `modus` (auslaufen: fertig rechnen, danach `signal.gesperrt` an die Anwendung; sofort: abbrechen mit `auftrag.abgebrochen`), `grund` (Text für die Anwendung) |
| `auftrag.prioritaet` | dito | `auftrag`, `prioritaet` |
| `anwendung.pausieren`, `anwendung.fortsetzen`, `anwendung.sperren`, `anwendung.freigeben` | Oberfläche an Leitstelle | `anwendung`, `grund` |
| `knoten.wartung`, `knoten.wartung_ende` | Oberfläche an Leitstelle | `knoten`; Wartung heißt: laufende Aufträge laufen aus, nichts Neues |
| `leitstelle.modus` | Oberfläche an Leitstelle | `modus` (normal, auslaufen, halt), `hintergrund` (true/false), `grund`; Hauptregler, wirkt sofort auf den Verbund; Antwort `leitstelle.modus_gesetzt` mit `betroffene_auftraege` |
| `leitstelle.massnahme` | Leitstelle an Oberfläche und Protokoll | `massnahme` (Kennung), `art` (umleiten, leerlauf_raeumen, vorwaermen, kette_ausweichen, extern_ausweichen, umverteilen, verlagern, doppel_aufloesen), `zustand` (geplant, ausgefuehrt, geprueft_ohne_aktion, nicht_ausgeloest, rueckgaengig), `grund`, `gewinn_s`, `kosten_s`, `schritte`, `betroffene_auftraege`, `knoten` |
| `leitstelle.massnahme_rueckgaengig`, `leitstelle.massnahme_ausfuehren` | Oberfläche an Leitstelle | `massnahme`; ausführen gilt für die Stufe Vorschlagen |
| `regel.speichern`, `regel.schalten`, `regel.trockenlauf` | Oberfläche an Leitstelle | `regel` (Kennung), `graph` (Regelgraph als Daten), `aktiv`; Antwort `regel.gespeichert` mit Fassung oder `regel.fehler` (Zyklus, offener Ausgang, Typ), `regel.trockenlauf_ergebnis` mit genommenem Weg und Zwischenwerten |
| `speicher.freigeben` | Oberfläche an Leitstelle | `knoten`, `vorschau` (true liefert nur den Plan), `nach_auftrag` (optional: erst wenn dieser Auftrag fertig ist) |

### 4.5 Signale (Leitstelle an Anwendung oder Dienst)

Signale sind Zustandsmeldungen ohne Antwortpflicht. Eine Anwendung bekommt nur, was sie betrifft.

| Art | Nutzlast | Wann |
|---|---|---|
| `signal.speicher` | `knoten`, `zustand` (frei, knapp, voll), `frei_gb`, `gesamt_gb`, `budget_gb`, `grund`, `voraussichtlich_frei_in_s`, `betroffene_auftraege` | Speicher über oder unter Schwellen; ein Auftrag der Anwendung wartet |
| `signal.lage` | `lage` (ruhig, angespannt, engpass), `begruendung` | Wechsel der Lage |
| `signal.gesperrt`, `signal.freigegeben` | `was` (anwendung, faehigkeit, zone), `grund`, `bis` (optional) | Sperre durch Nutzer oder Regel |
| `signal.pausiert`, `signal.fortgesetzt` | `was` (anwendung, auftraege, knoten), `grund` | Pause durch Nutzer oder Regel |
| `signal.modell` | `modell`, `zustand` (wird_geladen, bereit, entladen, nicht_verfuegbar), `knoten`, `dauer_s` | Modell wechselt den Zustand und die Anwendung nutzt es |
| `signal.kosten` | `anwendung`, `heute_euro`, `grenze_euro`, `anteil_prozent` | 80 Prozent und 100 Prozent der Grenze |
| `signal.zone` | `knoten`, `zone_alt`, `zone_neu` | Zonenwechsel (zum Beispiel VPN fällt aus) |
| `signal.dienst` | `dienst`, `zustand` | Dienst pausiert, zurück, nicht erreichbar |

### 4.6 Fragen (Anwendung an Leitstelle, Antwort kommt mit `bezug`)

| Art | Nutzlast | Antwort |
|---|---|---|
| `frage.kapazitaet` | `faehigkeit`, `modell` (optional), `umfang` (zum Beispiel Abschnitte) | `antwort.kapazitaet`: `jetzt` (true/false), `plaetze_frei`, `voraussichtlich_in_s`, `modell_geladen`, `begruendung` |
| `frage.modelle` | `faehigkeit` (optional) | `antwort.modelle`: Liste mit Name, Fähigkeit, Zustand, Knoten, Zone, Größe, Kontext |
| `frage.auftrag` | `auftrag` | `antwort.auftrag`: vollständiger Stand |
| `frage.lage` | leer | `antwort.lage` |

### 4.7 Reservierung (für Stapelarbeit)

| Art | Richtung | Nutzlast |
|---|---|---|
| `reservierung.anfragen` | Anwendung an Leitstelle | `faehigkeit`, `modell`, `umfang`, `dauer_s` (geschätzt), `prioritaet` |
| `reservierung.bestaetigt` | Leitstelle an Anwendung | `reservierung`, `modell`, `knoten`, `gueltig_bis`; die Leitstelle hält das Modell geladen und zählt den Platz |
| `reservierung.abgelehnt` | Leitstelle an Anwendung | `grund`, `voraussichtlich_in_s` |
| `reservierung.freigeben` | Anwendung an Leitstelle | `reservierung` |
| `reservierung.entzogen` | Leitstelle an Anwendung | `reservierung`, `grund` (dringend_vor, lage, nutzer) |

## 5. Eingabe und Ergebnis je Fähigkeit

| Fähigkeit | `eingabe` | `ergebnis` |
|---|---|---|
| text | `nachrichten` (Rolle und Inhalt wie im OpenAI-Format), `werkzeuge` (optional), `antwortformat` (optional: json_schema), `parameter` (Temperatur, höchstens Token, Denken an oder aus) | `nachricht` (Inhalt, Werkzeugaufrufe), `denken` (optional), `token` |
| einbettung | `texte` (Liste), `modell` | `vektoren` (Liste), `dimension`, `modell` |
| uebersetzen | `text`, `von`, `nach`, `stil` | `text` |
| hoeren | `datei_url` oder `datei` (Verweis auf Upload), `sprache`, `sprecher_trennen`, `woerter_mit_zeit` | `text`, `abschnitte` (Start, Ende, Text, Sprecher), `sprache` |
| stimme | `text`, `stimme`, `tempo`, `format` | `datei_url`, `dauer_s`, bei Streaming Stücke als Verweise auf Datenblöcke |
| stimme_klonen | `probe_url`, `text` | wie stimme |
| bild_beschreiben | `bild_url` oder `bild` (data-URL), `frage` | `text` |
| bild_erzeugen | `prompt`, `breite`, `hoehe`, `anzahl`, `seed`, `stil` | `bilder` (Liste von `datei_url`) |
| bild_freistellen | `bild_url` | `datei_url` |
| musik | `prompt`, `dauer_s`, `parameter` | `datei_url` |
| werkzeug | `name`, `argumente` | `ergebnis` (frei) |

Dateien: Upload über `POST /api/dateien` (multipart) liefert eine `datei_url`, die 24 Stunden gilt;
Ergebnisse liegen ebenso unter `/api/dateien/<kennung>`. Anwendungen im selben Netz dürfen auch
eigene `http://`-Adressen angeben, aus denen der Dienst liest.

## 6. Die Fassade (OpenAI-Format)

Für Anwendungen ohne Umbau. Basisadresse mit oder ohne `/v1` wird angenommen.

| Endpunkt | Wird zu | Besonderheiten |
|---|---|---|
| `GET /v1/models` | `frage.modelle` | listet Namen und Aliasse, die die Anwendung nutzen darf; Zustand im Feld `x-leitstelle` (geladen, Knoten, Zone) |
| `POST /v1/chat/completions` | `auftrag.anlegen` (text) | Streaming als SSE im OpenAI-Format; `usage` am Ende; `model` darf Alias oder Kettenname sein; fehlt `model`, gilt die Kette der Anwendung |
| `POST /v1/embeddings` | `auftrag.anlegen` (einbettung) | Modellname muss zur Kette passen (Einbettungen sind modellgebunden) |
| `POST /v1/audio/transcriptions` | `auftrag.anlegen` (hoeren) | multipart; lange Dateien laufen als Hintergrund-Auftrag, Antwort erst am Ende |
| `POST /v1/audio/speech` | `auftrag.anlegen` (stimme) | Audio-Stream |
| `POST /v1/images/generations` | `auftrag.anlegen` (bild_erzeugen) | Antwort mit Verweisen |
| `GET /api/v0/models`, `GET /api/v1/models` | `frage.modelle` | nachgebildete Form des Modell-Läufers (Feld `state`, `loaded_instances`), weil mehrere Anwendungen genau diese Form lesen |

Hinweise an Fassaden-Anwendungen: Signale lassen sich über die Fassade nicht zustellen. Die Leitstelle
legt deshalb Hinweise in die Antwort: Köpfe `X-Leitstelle-Lage`, `X-Leitstelle-Wartet-S` (geschätzte Wartezeit,
wenn der Auftrag auf Speicher oder einen Platz wartet) und `X-Leitstelle-Auftrag` (Kennung); bei Streams
kommen während des Wartens Kommentarzeilen (`: wartet, 16.2 GB passen nicht neben ..., etwa 25 s`), die jeder SSE-Leser überliest und
die zugleich die Verbindung offen halten. In der Oberfläche heißen solche Nachrichten "Hinweis" statt "Signal".

Priorität der Fassaden-Aufträge: Vorgabe der Anwendung; ein Kopf `X-Leitstelle-Prioritaet` kann sie je
Aufruf absenken (nie heben), ebenso `X-Leitstelle-Titel` für einen lesbaren Titel (prozentkodiert, weil HTTP-Köpfe nur
ASCII tragen). Mehr als diese zwei Köpfe gibt
es nicht; wer mehr will, nutzt das Protokoll.

## 7. Fehler und Gründe

Gründe sind Wörter aus Listen, die Oberfläche übersetzt sie:

`unbekannter_schluessel`, `gesperrt`, `herkunft_nicht_erlaubt`, `faehigkeit_nicht_erlaubt`,
`zone_nicht_erlaubt`, `kostengrenze`, `kontingent`, `kein_dienst`, `kein_modell`,
`modell_passt_nicht`, `dienst_nicht_erreichbar`, `dienst_fehler`, `stillstand`, `nicht_anhaltbar`,
`nutzer`, `regel_hintergrund`, `lage`, `dringend_vor`, `wartung`.

Jede Fehler- oder Ablehnungsnachricht trägt zusätzlich `begruendung` in einem Satz und, wenn
vorhanden, die Originalmeldung des Dienstes in `meldung`.

## 8. Erweiterung und Verträglichkeit

- Neue Felder: einfach hinzufügen; Empfänger ignorieren Unbekanntes.
- Neue Arten: Schema unter `backend/leitstelle/protokoll/schema/<art>.json` ablegen; die Oberfläche
  zeigt unbekannte Arten roh an.
- Eigene Felder von Anwendungen: `x-<anwendung>-<name>`; die Leitstelle reicht sie in `auftrag.*`
  unverändert zurück, damit Anwendungen ihre eigenen Bezüge wiederfinden.
- Fassung 2 wird erst nötig, wenn ein Pflichtfeld seine Bedeutung ändert. Bis dahin bleibt es bei
  `leitstelle/1`.

## 9. Beispiel: ein Bildauftrag wartet auf Speicher

```
Kiste            -> Leitstelle   auftrag.anlegen        faehigkeit bild_beschreiben, bild als data-URL, prioritaet normal
Leitstelle       -> Kiste        auftrag.angenommen     zustand wartet_speicher, platz 2, voraussichtlich_start_s 25,
                                                       begruendung "Bildmodell (11,8 GB) passt nicht neben das Textmodell (84,7 GB); 5,1 GB frei"
Leitstelle       -> Kiste        signal.speicher        knoten mac-128, zustand knapp, frei_gb 5.1, voraussichtlich_frei_in_s 25, betroffene_auftraege [a-e77a]
Leitstelle       -> Zusage       auftrag.ergebnis       (der Textauftrag endet)
Leitstelle       -> Kiste        signal.modell          modell glm-vision, zustand wird_geladen, dauer_s 14
Leitstelle       -> Kiste        signal.modell          zustand bereit
Leitstelle       -> Kiste        auftrag.laeuft         zuteilung Modell-Läufer, GLM 4.6V Flash, Mac Studio, Heimnetz
Leitstelle       -> Kiste        auftrag.ergebnis       text "...", messung dauer 3.8 s
```

Die Anwendung kann in der Wartezeit entscheiden: warten, Priorität anheben, verwerfen oder (wenn
erlaubt) extern rechnen lassen. Sie muss nichts davon tun; ohne Reaktion läuft der Auftrag von selbst
weiter, sobald Platz ist.
