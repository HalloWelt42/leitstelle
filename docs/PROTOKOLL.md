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
Anwendung nach der eingestellten Frist (Vorgabe 60 s) als getrennt. Laufende Aufträge einer getrennten Anwendung laufen
weiter; das Ergebnis wartet, bis sie wiederkommt oder die Aufbewahrung endet.

Knoten-Agenten: eine Frist für Herzschläge gibt es nicht. Ein Agent, der still verschwindet (Netz weg, Strom weg),
fällt erst über den Ping der WebSocket-Verbindung auf (alle 20 s, Antwort binnen 20 s: nach 20 bis 40 s); seine Dienste
gelten dann als nicht erreichbar. Ein Rechner, der einschläft, meldet sich vorher mit `knoten.schlaeft` ab (4.2); er
gilt dann nicht als ausgefallen, sondern als schlafend, bis sich sein Agent wieder anmeldet.

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
| `knoten.dienste` | Agent an Leitstelle, bei jeder Änderung und spätestens alle zehn Takte | `dienste`: je Dienst `kennung`, `name`, `faehigkeiten`, `port`, `zustand` (aus, startet, laeuft, stoppt, gestoert), `fremd` (läuft, aber nicht vom Agenten gestartet), `gb_jetzt` (gerade gemessen, sonst null), `bedarf_gb` (was er laufend braucht: höchster gemessener Wert, mindestens die Schätzung; damit plant die Leitstelle), `aktiv` (arbeitet gerade, nach Prozessorlast), `anhalten_erlaubt` (darf die Leitstelle ihn anhalten), `meldung` |
| `knoten.fremde` | Agent an Leitstelle, im Takt der Messung; nicht im Nachrichtenverkehr der Oberfläche | Zugriffe am Leitstand vorbei auf die Modelle dieses Rechners: `beobachtet` (falsch, wenn der Agent es nicht messen kann oder die Beobachtung aus ist; dann sagt die Liste nichts), `zugriffe`: je Zugriff `art` (`laeufer`: Verbindung zum Modell-Läufer, die nicht über die Durchleitung kommt; `speicher`: Programm mit viel Speicher, das weder Dienst noch Läufer ist), `wer` (Programmname oder Adresse im Netz), `pid` (nur auf diesem Rechner), `befehl` (Befehlszeile, gekürzt), `ordner` (Arbeitsordner), `verbindungen` (bei `laeufer`), `gb` (bei `speicher`), `vom_rechner_der_leitstelle` (Adresse im Netz ist die des Rechners der Leitstelle) |
| `knoten.last` | Agent an Leitstelle, im Takt der Beobachtung (Vorgabe 15 s), aus derselben Aufnahme wie `knoten.fremde`; nicht im Nachrichtenverkehr der Oberfläche | Last des Modell-Läufers und des Rechners: `kerne` (logische Kerne), `laeufer`: je Prozess des Läufers (der Prozess am Läufer-Port samt Nachfahren) `pid`, `name`, `rolle` (`haupt`: lauscht am Port, `arbeiter`: hat eine Modelldatei offen oder eine Bibliothek eines Rechenwerks geladen, also eine geladene Instanz, `sonstig`: alles andere), `modelldatei` (bei `arbeiter`: Pfad der offenen Modelldatei, erkannt an den Endungen aus `beobachtung.modelldateien`; leer bei einem Arbeiter ohne offene Modelldatei), `cpu_prozent` (Rechenzeit seit der letzten Messung je Wandzeit, in Prozent eines Kerns; beim ersten Mal und bei neuer pid null), `gb`; `fremd_prozent` (Last aller übrigen Prozesse ohne Läufer, ohne Dienste des Maschinenraums und ohne Apps des Stellwerks, Anteil aller Kerne, 0 bis 100; beim ersten Mal null); `gemessen` (falsch ohne lsof oder ohne Läufer-Port: dann sagt `laeufer` nichts); ab Maschinenraum 0.17 `apps`: die Apps des Stellwerks (vom Stellwerk gestartet, kein KI-Dienst) mit `gemessen` (falsch, wenn das Stellwerk nicht antwortet oder keine Prozessnummern meldet), `meldung` (warum nicht) und je laufendem nativem Teil `app`, `app_name`, `teil`, `name`, `pids` (seine Prozesse samt Nachfahren, jeder nur einmal), `cpu_prozent` (Prozent eines Kerns, nach der Regel der Fremdlast) und `gb`; null ohne eingetragenes Stellwerk. Ihre Prozesse zählen weder als fremder Speicher in `knoten.fremde` noch zur Fremdlast; spricht einer den Läufer direkt an, bleibt das eine Umgehung; ab Maschinenraum 0.16 `docker`: Last des Docker-Rechners (die virtuelle Maschine der Container) mit `gemessen`, `kerne`, `speicher_gb` und je Container `name`, `projekt` (Compose-Projekt), `cpu_prozent` (Prozent eines Kerns des Docker-Rechners), `gb`; null, wenn nicht gemessen. Die Leitstelle zeigt beides beim Rechner und rechnet aus `docker` das zweite Maß der Regel "Hintergrund bei Rechnerlast" (ZUSAMMENSPIEL Z6b). Zeitbasiert, nicht mit `cpu_prozent` der Messwerte zu mischen |
| `knoten.befehl` | Leitstelle an Agent | `befehl` (dienst_starten, dienst_anhalten, laeufer_prozess_beenden), `ziel` (Kennung des Dienstes; bei laeufer_prozess_beenden die pid); Befehle sind auf die Dienstverwaltung und das Beenden eines Arbeiters des Läufers begrenzt. Bei laeufer_prozess_beenden prüft der Agent vorher selbst, dass die pid gerade ein Arbeiter des Läufers ist (den Hauptprozess, fremde und verschwundene Prozesse lehnt er ab), beendet erst freundlich (SIGTERM), nach seiner Anhaltezeit hart (SIGKILL), und nennt im Ergebnis Name, Modelldatei und Weg |
| `knoten.befehl_ergebnis` | Agent an Leitstelle, mit `bezug` auf den Befehl | `befehl`, `ziel`, `erfolg`, `meldung`; ein Start antwortet erst, wenn der Dienst erreichbar ist oder seine Startzeit verstrichen ist |
| `knoten.schlaeft` | Agent an Leitstelle, unmittelbar vor dem Einschlafen des Rechners | `grund` (`leerlauf`: nach der Leerlaufzeit, `angefordert`: von Hand, Deckel, Ein-Taste), `meldung`; danach schließt der Agent die Verbindung mit Code 1000 und Grund `schlaeft` und meldet sich erst nach dem Aufwachen wieder an |
| `knoten.schlaf_vermerkt` | Leitstelle an Agent, mit `bezug` auf `knoten.schlaeft` | leer; der Agent wartet höchstens 3 s darauf (eine ältere Leitstelle antwortet nicht) und schließt in jedem Fall |
| `knoten.angemeldet`, `knoten.getrennt` | Leitstelle an Oberfläche | `knoten`, `name`; bei der Anmeldung dazu die Angaben aus `knoten.anmelden` |
| `knoten.schlaeft`, `knoten.aufgewacht` | Leitstelle an Oberfläche | `knoten`, `name`; beim Einschlafen dazu `grund` |

Durchleitung: der Agent meldet in `knoten.anmelden` den Port `durchleitung_port`. Die Leitstelle ruft dort
`/<dienst>/<pfad>` mit demselben Schlüssel als Bearer auf; der Agent reicht an den Dienst weiter, der nur auf seinem
Rechner lauscht. Ziel ist die Adresse, von der aus sich der Agent verbunden hat.

Den Modell-Läufer eines Rechners spricht die Leitstelle direkt unter seiner Adresse an; durch die Durchleitung gehen nur
die Dienste des Agenten. Die Leitstelle ist die zentrale Steuerung und Überwachung: sie muss nicht jedes Bit
durchschleifen, aber sie sieht, was auf den Rechnern geschieht, und greift ein, wo es nötig ist.

Am Leitstand vorbei: die Leitstelle deutet jeden Zugriff aus `knoten.fremde`. Eine Verbindung zum Läufer aus dem Netz
von der Adresse der Leitstelle ist, solange sie einen Läufer dieses Rechners eingetragen hat (den sie direkt anspricht),
vermutlich sie selbst (`leitstelle_direkt`, keine Umgehung); sonst ist es ein anderes Programm auf ihrem Rechner
(`rechner_der_leitstelle`); alles andere heißt `umgehung`. Das Lagebild trägt je Knoten `fremde` (`beobachtet`,
`zugriffe` mit `deutung`, `umgehungen` als Zahl der echten Umgehungen). Jede Umgehung (Schlüssel aus Art, wer und
Prozess) steht einmal in den Meldungen, wenn sie auftaucht, und einmal, wenn sie verschwunden ist; verschwunden heißt
seit `LEITSTELLE_FREMDE_NACHLAUF_S` (Vorgabe 60 s) nicht mehr gemeldet, damit Programme, die den Läufer immer wieder kurz
ansprechen, nicht flackern.

Last (ZUSAMMENSPIEL Z6): die Leitstelle schreibt je Arbeiter die Reihe der Messungen über `laeufer_schwelle_prozent`
fort und hält die Fremdlast über `last_frist_s` (Regelwerk). Das Lagebild trägt je Knoten `last` (`gemeldet`,
`gemessen`, `kerne`, `fremd_prozent`, `fremd_mittel_prozent`, `laeufer` mit `ohne_auftrag_seit_s` und `beenden_s`,
`auftraege` und `zuletzt_s` der Leitstelle auf dem Läufer, `umgehungen` am Läufer, `stufe`, `stufe_grund`,
`stufe_seit_s`) und dazu das ganze `regelwerk`. Ein Arbeiter, der seit `laeufer_frist_s` über der Schwelle rechnet,
während kein Auftrag der Leitstelle auf einem Läufer des Rechners lief, zugeteilt war oder geladen wurde, steht einmal in
den Meldungen, wenn er so erkannt ist, und einmal, wenn er es nicht mehr ist oder beendet wurde. Beenden von Hand:
`POST /api/knoten/<kennung>/laeufer/<pid>/beenden`, mit derselben Prüfung wie die Regel (409 `nicht_anhaltbar` sonst;
502 `dienst_fehler`, wenn der Agent ablehnt); die Leitstelle wartet höchstens `LEITSTELLE_LAEUFER_BEFEHL_S` (Vorgabe 60 s)
auf die Antwort. Befehl und Regel gibt es nur für Agenten, die `knoten.last` melden.

Schlaf: nach `knoten.schlaeft` führt die Leitstelle den Rechner als schlafend (Zustand `schlaeft`, mit Zeitpunkt; der
Vermerk übersteht ihren Neustart). Seine Dienste heißen `schlaeft`, werden nicht geprüft und zählen keine Fehlschläge;
laufende Aufträge auf ihm enden mit `rechner_schlaeft`, neue werden mit 503 `rechner_schlaeft` abgelehnt (7), solange
ihr Modell nur auf schlafenden Rechnern liegt. Die Lage bleibt ruhig und nennt ihn als Hinweis. Die nächste
`knoten.anmelden` desselben Agenten beendet den Schlaf; seine Dienste werden sofort geprüft. Von Hand beendet ihn
`POST /api/knoten/<kennung>/schlaf_beenden` ("Nicht mehr warten").

Transport: WebSocket `/agent/kanal` mit dem Schlüssel des Agenten als Bearer. Unbekannter Schlüssel: Schließen mit
Code 4401 und Grund `unbekannter_schluessel`; ein neu erzeugter Schlüssel trennt den verbundenen Agenten mit
`schluessel_erneuert`; vor dem Schlaf schließt der Agent selbst mit 1000 und `schlaeft`. Die Modelle der Nutzlasten stehen in `backend/leitstelle/protokoll/knoten.py`; der Agent
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

### 4.8 Selbstauskunft: der Steckbrief je Modell

Eine Anwendung soll keine Modellnamen kennen müssen. Sie fragt, wofür ein Modell gemacht ist, und wählt danach:
"Welches Modell übersetzt lange Texte ins Deutsche?", "Was antwortet schnell?". Jedes Modell im Verbund hat dafür
einen Steckbrief. Die Leitstelle setzt ihn aus drei Quellen zusammen und nennt je Angabe, woher sie stammt.

**Felder**

| Feld | Inhalt |
|---|---|
| `zweck` | ein Satz: wofür das Modell oder der Dienst gemacht oder optimiert ist; leer heißt: niemand sagt etwas |
| `eignung` | Wörter (Tabelle unten): wofür es über seine Fähigkeiten hinaus besonders taugt |
| `sprachen` | Kürzel nach ISO 639-1 (`de`, `en`); leer heißt nicht angegeben, nicht "keine" |
| `faehigkeiten` | wie überall im Protokoll (`text`, `uebersetzen`, `stimme`, ...) |
| `kontext` | größter Kontext in Token |
| `parameter_mrd` | Parameter in Milliarden (Gesamtzahl, nicht die aktiven) |
| `parameter_aktiv_mrd` | je Schritt aktive Parameter in Milliarden: bei Mischmodellen weniger (aus dem Namen, `A3B` heißt 3, oder von Hand), sonst gleich gesamt |
| `quantisierung` | wie der Dienst sie nennt (`4bit`, `FP8`) |
| `zone` | `heim`, `fern` oder `extern`; extern heißt: Daten verlassen das Heimnetz |
| `anfragen_je_minute`, `token_ein_je_minute`, `token_aus_je_minute` | Grenzen des Anbieters je Minute (gleitend, je Schlüssel), wenn er welche hat |
| `geprueft` | Fähigkeitsproben der Leitstelle (Quelle `gemessen`): je Fähigkeit `belegt`, `zeit_s` und die gekürzte Antwort als `meldung` |
| `gemessen` | `auftraege` (Grundlage), `rechenzeit_s`, `erstes_stueck_s`, `token_je_s` (Median der jüngsten 100 fertigen Aufträge), `ladezeit_s` (gleitender Mittelwert) |
| `herkunft` | je Feld die Quelle: `dienst`, `hand`, `gemessen`, `abgeleitet` |

**Eignung**

| Wort | Bedeutung |
|---|---|
| `denken` | schließt schrittweise; für schwierige Fragen, dauert länger |
| `programmieren` | für Quelltext |
| `lange_texte` | großer Kontext; abgeleitet ab 100 000 Token, wenn niemand etwas anderes sagt |
| `schnell` | kurze Wartezeit, auch auf Kosten der Tiefe; bei externen Anbietern abgeleitet für das Mischmodell, wenn der Anbieter auch ein dichtes anbietet |
| `gruendlich` | beste Ergebnisse, auch auf Kosten der Zeit; bei externen Anbietern abgeleitet für das dichte Modell im selben Vergleich |

**Quellen und Vorrang.** Von Hand Eingetragenes geht vor, dann die Auskunft des Dienstes, dann Abgeleitetes. Ein
Eintrag von Hand gilt je Modellfamilie (dasselbe Modell auf zwei Rechnern teilt ihn); ein leeres Feld lässt die
Auskunft des Dienstes stehen. Was die Dienste selbst sagen:

| Dienst | Selbstauskunft |
|---|---|
| Modell-Läufer (`openai_kompatibel` mit nativer Schnittstelle) | Beschreibung der Modellkarte als Zweck, `capabilities.reasoning` als `denken`, Quantisierung, Kontext, Parameter, Bilder und Werkzeuge (als Fähigkeiten) |
| Externer Anbieter (`extern_openai`) | Kontext (`max_model_len`), Parameter gesamt und aktiv aus dem Namen; im Vergleich der Textmodelle des Anbieters abgeleitet schnell (Mischmodell, für kurze Aufgaben) und gründlich (dicht, für lange Texte) mit passendem Zweck; Bild beschreiben nur, wenn eine Fähigkeitsprobe es belegt (von Hand am Dienst, `POST /api/dienste/<kennung>/faehigkeiten_pruefen`: je Modell ein kleines Bild mit einer Frage, zählt gegen die Grenzen) |
| Maschinenraum (Knoten-Agent) | aus der Dienstdatei: `beschreibung` als Zweck, `eignung`, `sprachen`; im Bericht `knoten.dienste` je Dienst als `selbstauskunft` |

**Abfrage.** `GET /v1/steckbriefe` (Fassade, Schlüssel der Anwendung) mit den Filtern `faehigkeit`, `eignung` und
`sprache` liefert nur Modelle, die die Anwendung nutzen darf (Fähigkeiten, Zonen, externe nur mit Erlaubnis).
Fähigkeit und Eignung müssen passen; bei `sprache` kommen zuerst die Modelle, die sie ausdrücklich können, dann die
ohne Angabe, darin geladene vor freien. `GET /v1/models` trägt denselben Steckbrief je Eintrag unter
`x-leitstelle.steckbrief`. Von Hand eintragen: `PUT /api/steckbriefe` (Verwaltung, Heimnetz) mit `familie`, `zweck`,
`eignung`, `sprachen`, `parameter_aktiv_mrd`; alles leer entfernt den Eintrag. Die Wahl zwischen Modellen bleibt bei der
Anwendung: sie nennt das gewünschte als `model` (bei externen zusätzlich mit Erlaubnis) oder sucht über die Eignung.

```json
{"object": "list", "data": [{"id": "qwen/qwen3-next-80b", "name": "Qwen3 Next 80B", "geladen": true,
  "steckbrief": {"zweck": "Übersetzen ins Deutsche", "eignung": ["denken", "lange_texte"], "sprachen": ["de", "en"],
                 "faehigkeiten": ["text", "uebersetzen"], "kontext": 262144, "parameter_mrd": 80.0, "quantisierung": "4bit",
                 "zone": "heim", "anfragen_je_minute": null,
                 "gemessen": {"auftraege": 100, "rechenzeit_s": 6.4, "erstes_stueck_s": 0.9, "token_je_s": 41.2, "ladezeit_s": 38.0},
                 "herkunft": {"zweck": "hand", "eignung": "dienst", "sprachen": "hand", "kontext": "dienst",
                              "parameter_mrd": "dienst", "quantisierung": "dienst", "gemessen": "gemessen"}}}]}
```

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
| `GET /v1/models` | `frage.modelle` | listet Namen und Aliasse, die die Anwendung nutzen darf; Zustand im Feld `x-leitstelle` (geladen, Knoten, Zone) und dort der Steckbrief (4.8) |
| `GET /v1/steckbriefe` | Selbstauskunft (4.8) | Steckbriefe der Modelle, die die Anwendung nutzen darf; Filter `faehigkeit`, `eignung`, `sprache` |
| `POST /v1/chat/completions` | `auftrag.anlegen` (text) | Streaming als SSE im OpenAI-Format; `usage` am Ende; `model` darf Alias oder Kettenname sein; fehlt `model`, gilt die Kette der Anwendung |
| `POST /v1/embeddings` | `auftrag.anlegen` (einbettung) | Modellname muss zur Kette passen (Einbettungen sind modellgebunden) |
| `POST /v1/audio/transcriptions` | `auftrag.anlegen` (hoeren) | multipart; lange Dateien laufen als Hintergrund-Auftrag, Antwort erst am Ende |
| `POST /v1/audio/speech` | `auftrag.anlegen` (stimme) | Audio-Stream |
| `POST /v1/images/generations` | `auftrag.anlegen` (bild_erzeugen) | Bilder als `b64_json`, mit und ohne Strom; den Ablauf des Bilddienstes kennt die Leitstelle (6.1) |
| `GET /v1/dienste` | Liste der Dienste | die Dienste im Maschinenraum, die die Anwendung nutzen darf, mit Zustand und Rechner (6.2) |
| `GET, POST, PUT, PATCH, DELETE /v1/dienste/<name>/<pfad>` | `auftrag.anlegen` (Fähigkeit, die Dienst und Anwendung teilen) | jeder Dienst mit eigener Schnittstelle (Sprache, Bild, Musik): die Leitstelle startet ihn bei Bedarf über den Maschinenraum seines Rechners, plant seinen Bedarf ein und reicht Anfrage und Antwort unverändert durch (auch Binärdaten). `<name>` ist die Kennung des Dienstes im Maschinenraum (Dateiname der Dienstdatei) |
| `GET /api/v0/models`, `GET /api/v1/models` | `frage.modelle` | nachgebildete Form des Modell-Läufers (Feld `state`, `loaded_instances`), weil mehrere Anwendungen genau diese Form lesen |

### 6.1 Bilder erzeugen

`POST /v1/images/generations` mit dem Schlüssel einer Anwendung, die `bild_erzeugen` darf. Die Arbeit ist ein Auftrag
wie jeder andere (Rechte, Zonen, Speicherplanung, Start des Dienstes bei Bedarf, Lage, Verlauf). Welcher Bilddienst
rechnet, sagt `model` oder die Kette der Anwendung für `bild_erzeugen`; wie er rechnet (bei der Bildschmiede ein
Arbeitsgraph mit Checkpoint, Sampler, Schritten), weiß nur sein Bildablauf in der Leitstelle (Einstellung
`LEITSTELLE_BILDABLAEUFE`, je Dienst; Vorgabe: `bildschmiede` mit FLUX.1 schnell, 4 Schritte, cfg 1.0, euler/simple).

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `prompt` | ja | Beschreibung, 1 bis 8000 Zeichen |
| `size` | nein | `BreitexHöhe`, je 256 bis 2048 und durch 16 teilbar; Vorgabe `1024x1024`, üblich auch `1344x768`, `768x1344` |
| `n` | nein | Anzahl 1 bis 4, Vorgabe 1 |
| `seed` | nein | Startwert 0 bis 2^53 - 1; fehlt er, zieht die Leitstelle einen und nennt ihn in der Antwort |
| `model` | nein | Kennung des Bilddienstes (`GET /v1/dienste`); fehlt sie, gilt die Kette der Anwendung |
| `response_format` | nein | nur `b64_json` |
| `stream` | nein | `true`: Server-Sent Events wie beim Chat |

Gleicher Startwert, gleiche Beschreibung, Größe und Anzahl beim selben Dienst ergeben dieselben Bilder ("dasselbe Bild,
nur dunkler": Startwert behalten, Beschreibung ändern). Unbekannte Felder werden überlesen.

```json
{"created": 1792512802,
 "data": [{"b64_json": "iVBORw0KGgo...", "revised_prompt": null}],
 "x-leitstelle": {"seed": 42, "modell": "bildschmiede", "dauer_ms": 21400}}
```

`x-leitstelle.modell` ist die Kennung des Dienstes, der gerechnet hat (als `model` mitgeschickt rechnet derselbe
wieder), `dauer_ms` die Rechenzeit im Dienst ohne das Warten auf Start oder Platz. Köpfe wie bei der übrigen Fassade
(`X-Leitstelle-Auftrag`, `X-Leitstelle-Lage`, ohne Strom auch `X-Leitstelle-Modell`, `X-Leitstelle-Knoten`).

Mit `"stream": true` (`text/event-stream`): solange der Auftrag wartet (Dienst startet, Platz belegt, Speicher) alle
15 s ein Kommentar `: wartet, <grund>, etwa <n> s`, während der Dienst rechnet `: rechnet seit <n> s`; dann genau eine
Zeile `data: <Antwort wie oben>` und `data: [DONE]`. Ein Fehler kommt als `data: {"error": {...}}` und `data: [DONE]`.
Trennt die Anwendung die Verbindung, endet der Auftrag, und die Bildschmiede nimmt ihn aus ihrer Warteschlange.

Fehler im Format der Fassade (7): 400 `eingabe` (Feld falsch, Satz in `error.message`), 401, 403
`faehigkeit_nicht_erlaubt`, 404 `kein_modell` (Name unbekannt, oder weder `model` noch Kette), 503 `kein_dienst`
(für diesen Dienst ist kein Bildablauf eingerichtet; er bleibt über `/v1/dienste/<name>/` roh erreichbar), 502
`dienst_fehler` mit der Meldung der Bildschmiede, dazu alle Gründe der Warteschlange (`rechner_schlaeft`, `halt`, ...).

### 6.2 Liste der Dienste

`GET /v1/dienste` mit dem Schlüssel einer Anwendung: die Dienste im Maschinenraum (Sprache, Bild, Musik, ...), die
sie nutzen darf (Fähigkeit und Zone). Je Dienst ein Eintrag, gleich wie viele Instanzen auf wie vielen Rechnern laufen;
`faehigkeiten` nennt nur, was die Anwendung davon nutzen darf. Ohne Schlüssel aus dem Heimnetz: alle.

```json
{"object": "list", "data": [{"kennung": "bildschmiede", "name": "Bildschmiede", "faehigkeiten": ["bild_erzeugen"],
                             "zustand": "aus", "rechner": ["MacBook M4 Max 128 GB"]}]}
```

| `zustand` | Bedeutung |
|---|---|
| `bereit` | läuft und nimmt Aufträge an |
| `startet` | wird gerade gestartet |
| `aus` | läuft nicht; der erste Auftrag startet ihn (Startzeit des Dienstes, die Bildschmiede etwa 180 s) |
| `schlaeft` | sein Rechner schläft; Aufträge warten in der Anwendung, bis er wach ist |
| `nicht_erreichbar` | sein Maschinenraum meldet sich nicht |

Laufen mehrere Instanzen, zählt die beste (eine bereite genügt). `kennung` dient als `model` und für
`/v1/dienste/<kennung>/<pfad>`.

Hinweise an Fassaden-Anwendungen: Signale lassen sich über die Fassade nicht zustellen. Die Leitstelle
legt deshalb Hinweise in die Antwort: Köpfe `X-Leitstelle-Lage`, `X-Leitstelle-Wartet-S` (geschätzte Wartezeit,
wenn der Auftrag auf Speicher oder einen Platz wartet) und `X-Leitstelle-Auftrag` (Kennung); bei Streams
kommen während des Wartens Kommentarzeilen (`: wartet, 16.2 GB passen nicht neben ..., etwa 25 s`), die jeder SSE-Leser überliest und
die zugleich die Verbindung offen halten. In der Oberfläche heißen solche Nachrichten "Hinweis" statt "Signal".

Priorität der Fassaden-Aufträge: Vorgabe der Anwendung; ein Kopf `X-Leitstelle-Prioritaet` kann sie je
Aufruf absenken (nie heben), ebenso `X-Leitstelle-Titel` für einen lesbaren Titel (prozentkodiert, weil HTTP-Köpfe nur
ASCII tragen), `X-Leitstelle-Arbeit` für die Arbeit, zu der die Anfrage gehört, `X-Leitstelle-Extern` für die
Erlaubnisliste externer Modelle und `X-Leitstelle-Instanz` für Folgeaufrufe (ANBINDUNG). Mehr als diese fünf Köpfe
gibt es nicht; wer mehr will, nutzt das Protokoll.

Bindung an eine Instanz: läuft ein Dienst mehrfach (weitere Instanz auf demselben Rechner, ein zweiter Rechner),
gehören zusammengehörige Aufrufe an dieselbe Instanz, etwa "rechnen" und danach "Ergebnis abholen". Jede Antwort einer
Durchleitung (`/v1/dienste/...`) nennt im Kopf `X-Leitstelle-Instanz` die Instanz, die gerechnet hat; schickt die
Anwendung diesen Wert bei einem Folgeaufruf mit, geht er nur dorthin. Läuft die Instanz nicht mehr, antwortet die
Leitstelle mit 409 `instanz_weg`, und der Vorgang beginnt von vorn. Der Appkern bindet mit `async with
dienst.gebunden():`.

Externe Modelle (Zone extern): eine Anfrage geht nur dorthin, wenn die Leitstelle der Anwendung die Zone extern
erlaubt und die Anwendung das Modell selbst will, also ausdrücklich als `model` verlangt oder in
`X-Leitstelle-Extern` nennt (Namen durch Komma getrennt, prozentkodiert). Ohne den Kopf weicht die Leitstelle für
diese Anfrage nie nach extern aus. Die Liste führt die Anwendung in ihren eigenen Einstellungen; sie entscheidet, wo
die Qualität reicht.

## 7. Fehler und Gründe

Gründe sind Wörter aus Listen, die Oberfläche übersetzt sie:

`unbekannter_schluessel`, `gesperrt`, `herkunft_nicht_erlaubt`, `faehigkeit_nicht_erlaubt`,
`zone_nicht_erlaubt`, `kostengrenze`, `kontingent`, `kein_dienst`, `kein_modell`,
`modell_passt_nicht`, `dienst_nicht_erreichbar`, `rechner_schlaeft`, `dienst_fehler`, `instanz_weg`, `stillstand`,
`nicht_anhaltbar`, `nutzer`, `regel_hintergrund`, `lage`, `dringend_vor`, `wartung`.

Jede Fehler- oder Ablehnungsnachricht trägt zusätzlich `begruendung` in einem Satz und, wenn
vorhanden, die Originalmeldung des Dienstes in `meldung`.

`rechner_schlaeft`: das Modell liegt nur auf Rechnern, die schlafen (4.2). Die Fassade antwortet mit 503,
`Retry-After` 60 s (einstellbar, `LEITSTELLE_SCHLAF_WIEDER_S`) und den Namen der Rechner in `error.x-leitstelle.rechner`;
der Satz lautet zum Beispiel "MacBook M4 Max 128 GB schläft; der Auftrag kann erst laufen, wenn er wach ist." Die Leitstelle hält
die Anfrage nicht selbst fest: die Anwendung wartet und versucht es erneut (der Appkern ohne Grenze, bis er wach ist).
Ein abgebrochener Strom trägt die Namen im letzten Stück unter `x-leitstelle.rechner`. `zone_nicht_erlaubt` (403)
heißt nur noch, dass die Zone wirklich nicht passt; ein Rechner, der unangekündigt verschwunden ist, gibt
`dienst_nicht_erreichbar` (503).

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
Leitstelle       -> Kiste        auftrag.laeuft         zuteilung Modell-Läufer, GLM 4.6V Flash, MacBook M4 Max 128 GB, Heimnetz
Leitstelle       -> Kiste        auftrag.ergebnis       text "...", messung dauer 3.8 s
```

Die Anwendung kann in der Wartezeit entscheiden: warten, Priorität anheben, verwerfen oder (wenn
erlaubt) extern rechnen lassen. Sie muss nichts davon tun; ohne Reaktion läuft der Auftrag von selbst
weiter, sobald Platz ist.
