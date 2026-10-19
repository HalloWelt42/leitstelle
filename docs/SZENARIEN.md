# Szenarienkatalog: geprüftes Verhalten des Entscheidungskerns

Jedes Szenario ist ein Test in `backend/tests/`; die Nummer (S01 bis S53 für den Kern, E01 bis E16 Ende zu Ende, R01 bis R07 Schlaf)
steht im Testnamen. Alles ist
gemockt: kein echter Modell-Läufer, kein Netz, keine Uhr. Die Schein-Welt (`backend/leitstelle/simulation/`)
bildet den echten Bestand nach (8 Anwendungen, 5 Anbindungen, 4 Knoten, 14 Modellinstanzen) und kennt eine
verborgene Wahrheit, die die Leitstelle nur über Messungen erfährt. Jeder Zweig jeder Regelvorlage ist mit
mindestens einem Szenario belegt (Abschnitt 3).

```bash
cd backend && .venv/bin/python -m pytest            # alle Szenarien
cd backend && .venv/bin/python -m pytest -k s34     # ein Szenario
```

## 1. Die Schein-Welt

### Knoten

| Kennung | Name | Zone | Speicher | System | Budget für Modelle | Besonderheit |
|---|---|---|---|---|---|---|
| mac-128 | Mac Studio | heim | 128 GB | 32 GB | 96 GB | Hauptrechner |
| mac-32 | MacBook | heim | 32 GB | 6 GB | 24 GB (fest) | Nachtfenster 23 bis 7 Uhr für Hintergrund |
| pi-archiv | Pi Archiv | heim | 8 GB | 2 GB | 6 GB | keine Modelle |
| server-fern | Server Helsinki | fern | 8 GB | 3 GB | 5 GB | keine Modelle |

Budget = Speicher minus dem Größeren aus Reserve (18 GB) und System, oder ein fester Wert je Knoten.

### Anbindungen (Dienste)

| Kennung | Name | Knoten | Art | Fähigkeiten | Zustand am Anfang |
|---|---|---|---|---|---|
| laeufer-128 | Modell-Läufer Mac Studio | mac-128 | openai_kompatibel | text, einbettung, uebersetzen, bild_beschreiben | bereit |
| laeufer-32 | Modell-Läufer MacBook | mac-32 | openai_kompatibel | text, uebersetzen, bild_beschreiben | aus, installiert, Start 3 s |
| txt2voice | txt2voice | mac-128 | txt2voice | hoeren, stimme | bereit |
| hoerer-32 | Hörer MacBook | mac-32 | hoeren_http | hoeren | bereit |
| extern-anbieter | Externer Anbieter | extern | extern_openai | text, bild_beschreiben | bereit, 4 Plätze |

### Modellinstanzen

| Kennung | Name | Familie | Fähigkeiten | GB | Milliarden Parameter | Anfang |
|---|---|---|---|---|---|---|
| qwen80@128 | Qwen3 Next 80B | qwen-next-80b | text, uebersetzen | 84,7 | 80 | geladen |
| bge@128 | bge-m3 Einbettung | bge-m3 | einbettung | 1,1 | 0,6 | geladen, geschützt |
| glm@128 | GLM 4.6V Flash | glm-4.6v | bild_beschreiben | 11,8 | 9 (geschützt durch Schutzgrenze) | frei |
| gemma@128 | Gemma 4 26B | gemma-4-26b | bild_beschreiben | 16,2 | 26 | frei |
| coder@128 | Qwen3 Coder Next | qwen-coder-next | text | 46,3 | 80 | frei |
| klein@128 | Qwen3 4B | qwen-4b | text, uebersetzen | 2,5 | 4 (geschützt) | frei |
| glm@32, gemma@32, klein@32 | dieselben Familien auf dem MacBook | | | | | frei, Dienst aus |
| whisper@128 | Whisper groß v3 | whisper-gross | hoeren | 3,1 | | geladen, geschützt |
| xtts@128 | Stimmklon | xtts | stimme | 1,9 | | geladen, geschützt |
| whisperm@32 | Whisper mittel | whisper-mittel | hoeren | 1,5 | | geladen, geschützt |
| qwen35@extern, qwen27@extern | externe Modelle | | text, bild_beschreiben | 0 | | immer bereit |

### Anwendungen

| Kennung | Priorität | Fähigkeiten | Zonen | Ketten | Extern erlaubt |
|---|---|---|---|---|---|
| zusage | hoch | text, bild_beschreiben | heim, fern | text: qwen-next-80b, qwen-4b; bild: glm-4.6v, gemma-4-26b | nein |
| tubevault | hintergrund | hoeren, stimme, text | heim | hoeren: whisper-gross, whisper-mittel; stimme: xtts; text: qwen-next-80b | nein |
| fundus | normal | text, einbettung | heim, fern, extern | text: qwen-next-80b, qwen-35b-extern; einbettung: bge-m3 | ja |
| medienpool | normal | uebersetzen | heim | qwen-next-80b, qwen-4b | nein |
| kiste | normal | bild_beschreiben, text | heim | bild: glm-4.6v, gemma-4-26b; text: qwen-next-80b | nein |
| Codehilfe | hoch | text | heim, fern, extern | qwen-coder-next, qwen-next-80b, qwen-35b-extern | ja |
| rufzeichen | dringend | text, hoeren, stimme | heim | text: qwen-next-80b, qwen-4b; hoeren: whisper-mittel, whisper-gross; stimme: xtts | nein |
| bildschmiede | hintergrund | bild_beschreiben, uebersetzen | heim | bild: gemma-4-26b, glm-4.6v; uebersetzen: qwen-4b, qwen-next-80b | nein |

### Vorgaben des Regelwerks

| Regel | Vorgabe | Bedeutung |
|---|---|---|
| Reserve je Knoten | 18 GB | bleibt dem System, wenn kein festes Budget gesetzt ist |
| Schutzgrenze | 10 Milliarden Parameter | darunter wird nie entladen (Wunsch des Nutzers) |
| Mindestverweildauer | 600 s | frisch Geladenes weicht nicht |
| Bedarfsfrist | 60 s | so lange muss ein Modell ohne Auftrag sein, bevor es einem Wartenden weicht |
| Leerlaufgrenze | 1800 s | ab wann ein Modell in den Listen als Leerlauf gilt |
| Gewinnfaktor | 2 | Gewinn muss das Doppelte des Aufwands sein (Kette: 1) |
| Extern-Schwelle | 120 s | ab dieser erwarteten Wartezeit darf extern ausgewichen werden |
| Hintergrund spätestens | 900 s | danach rückt Hintergrund auf Normal |
| Fenster, Höchstzahl, Ruhezeit | 600 s, 6, 1800 s | Flatterschutz und Deckel je Fenster |
| Umleitungen je Auftrag | 1 | |
| Takt des Umschichters | 5 s | |
| Geladene zuerst | an | der Zuteiler nimmt ein geladenes Modell der Kette vor dem ersten der Kette |
| Automatik | selbst | aus, vorschlagen, selbst |

### Was die Schein-Welt kann

- **Verborgene Wahrheit**: wahre Ladezeit (0,35 s je GB, je Familie und Knoten überschreibbar), wahre
  Startzeit je Dienst, wahre Laufzeit je Auftrag. Die Leitstelle schätzt zuerst (0,4 s je GB, mindestens
  5 s) und lernt aus jeder Messung (gleitendes Mittel).
- **Vollzug**: Dienst starten, Modell laden und entladen, umleiten, extern, melden, Signal, abbrechen mit
  Teilergebnis, neu einreihen, bevorzugter Knoten, Hintergrund an und aus. Alles wird aufgezeichnet:
  Signale je Anwendung, Meldungen, Lade- und Startvorgänge.
- **Wächter**: entlädt jemand ein rechnendes Modell, wirft die Welt eine Ausnahme; kein Test darf sie
  auslösen.
- **Zeit**: Schritte von 1 s; Ankünfte zu festen Zeiten; `laufen_bis_fertig` läuft, bis nichts mehr offen
  ist; `wechsel_je_familie_knoten` zählt Ladevorgänge je Familie und Knoten (Flatterzähler).

## 2. Katalog

### Zuteilung (`test_zuteiler.py`)

| Nr | Szenario | Erwartung |
|---|---|---|
| S01 | Zusage (hoch) schickt Text, das 80B-Modell ist geladen und frei | läuft sofort auf qwen80@128 über den Direktweg, nichts wird geladen |
| S02 | Zweiter Textauftrag, Platz belegt | wartet eingereiht mit Begründung "belegt", startet nach dem ersten |
| S03 | Fundus blockiert, dann TubeVault (hintergrund) und Zusage (hoch) | Zusage startet vor TubeVault |
| S04 | Fairness: Hintergrund wartet länger als die Frist | rückt auf Normal und startet vor einem später gekommenen Normal-Auftrag |
| S05 | Kiste braucht GLM, Platz ist da | Zuteiler lädt ohne Entladen, die Ladezeit wird gemessen |
| S06 | Kiste braucht GLM, Mac Studio voll, MacBook kann nicht helfen | wartet auf Speicher mit Begründung "passen nicht" am Mac Studio |
| S07 | Rechte: Kiste will hören (nicht erlaubt), Zusage will extern | beide abgelehnt mit Grund |
| S08 | Kontingent: Fundus darf eins gleichzeitig | zweiter Auftrag wartet mit "Kontingent" |
| S28 | Hauptregler Auslaufen, dann Halt, dann Normal | Laufendes endet normal, Neues wartet mit "Hauptregler", bei Halt keine Maßnahmen, danach läuft alles weiter |

### Speicherplan (`test_speicherplaner.py`)

| Nr | Szenario | Erwartung |
|---|---|---|
| | GLM passt ohne Entladen | Plan passt, nichts zu entladen |
| | Coder braucht 46 GB, mehrere ungenutzte Modelle | entlädt nur so viel wie nötig, größtes zuerst (qwen80) |
| S13 | 80B-Modell als geschützt markiert | Plan passt nicht, Begründung nennt "geschützt" und bge-m3 |
| S14 | 80B-Modell vor 10 s geladen | Plan passt nicht, "Mindestverweildauer" |
| S15 | 80B-Modell rechnet | Plan passt nicht, aber "frei nach" ist bekannt und qwen80 steht unter blockiert durch |
| | Nur Leerlauf: vor 60 s genutzt | mit Leerlaufgrenze 1800 s nicht entladbar, mit Bedarfsfrist 30 s entladbar, nach 5000 s immer |

### Umleiten (`test_regelzweige.py`)

| Nr | Szenario | Erwartung |
|---|---|---|
| S07 | Der Fall aus dem Entwurf: Zusage rechnet 60 s, Kiste braucht GLM, MacBook hat Platz, Dienst dort ist aus | Dienst wird gestartet, GLM geladen, Kiste läuft auf dem MacBook; Wartezeit unter 25 s; Gewinn mindestens doppelter Aufwand; Startzeit und Ladezeit gemessen; Signal `auftrag.laeuft` an Kiste |
| S09 | MacBook hat kein Budget | keine Umleitung, Ende "weiter warten", Kiste wartet auf Speicher |
| S10 | MacBook liegt in Zone fern, Kiste darf nur heim | "weiter warten" |
| S11 | Dienst auf dem MacBook ist nicht installiert | "weiter warten" |
| S12 | Laden auf dem MacBook ist gemessen langsam (60 s), das Textmodell wird in 12 s frei | "warten lohnt mehr"; danach räumt Leerlauf räumen nach der Bedarfsfrist das ungenutzte Textmodell |
| S12b | Dienst auf dem MacBook läuft schon | schon der Zuteiler nimmt das MacBook (Laden ohne Entladen), kein Dienststart |

### Leerlauf räumen

| Nr | Szenario | Erwartung |
|---|---|---|
| S16 | 80B-Modell lange ungenutzt, Kiste braucht Platz, kein Ausweichen | eine Maßnahme mit Richtung entladen, "Leerlauf geräumt", qwen80 frei, Kiste fertig auf dem Mac Studio |
| S16b | Textmodell rechnet noch 10 s, Gemma liegt ungenutzt daneben | zuerst "warten lohnt mehr" (Räumen dauert länger als Warten); sobald das Textmodell fertig ist, weicht Gemma und das eben genutzte Textmodell bleibt |
| S17 | Das ungenutzte Modell ist geschützt | "kein Leerlauf, der weichen darf", bleibt geladen |
| S18 | Ungenutzt, aber vor 30 s geladen | keine Maßnahme (Mindestverweildauer) |
| S19 | Vor 10 s genutzt | keine Maßnahme innerhalb der Bedarfsfrist |

### Vorwärmen

| Nr | Szenario | Erwartung |
|---|---|---|
| S20 | Hintergrund ist angehalten, TubeVault wartet eingereiht, das 80B-Modell ist nicht geladen, Platz ist da | Modell wird vorab geladen; wird der Hintergrund freigegeben, startet der Auftrag sofort |
| S21 | Bildschmiede wartet, nirgends Platz ohne Entladen | "kein Platz ohne Entladen" |

### Kette ausweichen

| Nr | Szenario | Erwartung |
|---|---|---|
| S22 | 80B belegt, das kleine Textmodell derselben Kette ist geladen und frei | mit "Geladene zuerst" nimmt schon der Zuteiler das kleine Modell; ohne diese Vorliebe greift die Regel und weicht aus |
| S23 | Zusage verlangt das 80B-Modell fest | keine Ausweiche, Auftrag bleibt eingereiht |

### Extern ausweichen

| Nr | Szenario | Erwartung |
|---|---|---|
| S24 | Fundus (extern erlaubt) müsste 300 s warten, Schwelle 30 s | läuft beim externen Anbieter und wird fertig |
| S25 | Kiste darf nicht extern; Fundus unter der Schwelle | "Anwendung darf nicht extern" beziehungsweise "Wartezeit unter der Schwelle", nichts extern |
| S25b | Fundus darf, aber der externe Anbieter ist nicht erreichbar | "kein externer Dienst", Auftrag bleibt eingereiht |

### Umverteilen, Verlagern, Doppel, Hintergrund bei Lage

| Nr | Szenario | Erwartung |
|---|---|---|
| S26 | Kiste läuft nach Umleitung auf dem MacBook, das MacBook fällt aus | Maßnahme Umverteilen; der Auftrag ist abgebrochen mit Teilergebnis, Signal `auftrag.abgebrochen` mit Teilergebnis |
| S27 | 23 Uhr: Nachtfenster des MacBooks beginnt | bevorzugter Knoten für Hintergrund ist das MacBook; um 9 Uhr wieder keiner |
| S29 | Gemma auf beiden Macs, auf dem MacBook wartet GLM auf Platz | genau die ungenutzte Kopie auf dem MacBook weicht, die andere bleibt, Kiste wird dort fertig |
| S30 | Gemma doppelt, niemand wartet; GLM doppelt | "kein Bedarf, Kopie bleibt"; GLM ist geschützt: "beide Kopien in Gebrauch oder geschützt" |
| S31 | TubeVault hört, dann wartet Kiste auf Speicher (Lage angespannt) | Hintergrund wird angehalten, der TubeVault-Auftrag pausiert; wird die Lage ruhig, läuft er weiter |

### Automatik und Graphprüfung

| Nr | Szenario | Erwartung |
|---|---|---|
| S32 | Automatik vorschlagen | die Umleitung steht als geplant, nichts wird ausgeführt, Kiste wartet |
| S33 | Automatik aus | keine Maßnahmen, auch keine geprüften |
| S41 | Graphprüfung | alle Vorlagen fehlerfrei; Zyklus, fehlender Nein-Ausgang und unbekannter Baustein werden gemeldet; Auswerten eines fehlerhaften Graphen wirft |
| S43 | Gewinnschwelle als Baustein | 5 gegen 3 bei Faktor 2 nein, 6 gegen 3 ja, Gewinn null nie, ohne Parameter gilt der Faktor des Regelwerks; jeder Baustein hat Wort und Erklärung |

### Schleifenschutz und Invarianten (`test_schleifen_und_invarianten.py`)

| Nr | Szenario | Erwartung |
|---|---|---|
| S34 | Ohne Verweildauer, Bedarfsfrist und Schutzgrenze würden GLM und Gemma auf dem MacBook alle 20 s tauschen | nach dem ersten Kreis (laden, entladen, wieder laden) wird Flattern erkannt, die Maßnahme gesperrt mit "Flattern erkannt", höchstens drei Wechsel je Familie |
| S35 | Dieselbe Last mit Vorgaben | höchstens ein Hin und Her je Modell in 20 Minuten |
| S36 | Höchstzahl 2 je Fenster, sechs Fundus-Aufträge wollen extern | höchstens zwei Maßnahmen im Fenster, weitere gesperrt mit "Höchstzahl" |
| S37 | Kiste umgeleitet, dann fällt das MacBook aus | Umverteilen reiht neu ein, der Auftrag wird nicht ein zweites Mal umgeleitet |
| S38 | Drei Zufallsläufe (Saaten 1, 2, 3) über eine Stunde mit allen 8 Anwendungen und allen Fähigkeiten | je Schritt: Budget nie überschritten, Geschütztes nie entladen, Zone nie verletzt, extern nie ohne Erlaubnis; am Ende nichts verhungert, höchstens 8 Ladevorgänge je Familie und Knoten |
| S39 | Rechnende Modelle | der Speicherplaner schlägt sie nie vor; der Wächter der Welt wirft, falls es je geschähe |
| S40 | Lage | ruhig ohne Wartende; angespannt bei einem Auftrag, der auf Speicher wartet; Engpass bei zweien |
| S42 | Messungen fließen ein | wahre Ladezeit 40 s statt geschätzter 5 s wird gemessen; danach lohnt Umleiten bei kurzer Wartezeit nicht mehr |

### Dauerbetrieb und Rechte (`test_dauerbetrieb.py`, `test_zuteiler.py`)

| Nr | Szenario | Erwartung |
|---|---|---|
| S44 | Der Dienst hat das Laden von GLM abgelehnt (Ladesperre 30 s) | der Auftrag wartet auf Speicher mit dem Grund im Wortlaut, niemand plant vorher einen neuen Versuch, danach wird geladen |
| S45 | Zwei Stunden mit 480 Aufträgen | Verlauf, Bewegungen und Sperren des Umschichters bleiben auf das Fenster begrenzt |
| S46 | Ablehnungen und externe Wunschmodelle | Grundwörter `zone_nicht_erlaubt`, `kein_modell`, `faehigkeit_nicht_erlaubt`, `dienst_nicht_erreichbar`; Fundus bekommt das verlangte externe Modell |
| S47 | Hintergrund am Hauptregler angehalten, Fairness-Frist 20 s | der Hintergrundauftrag bleibt eingereiht, auch nach der Frist; die Regel Hintergrund bei Lage schaltet ihn nicht ein |
| S48 | Schutzvorgabe eines Dienstes | geht der Regel nach Parameterzahl vor: erlaubt der Dienst das Anhalten, darf auch ein Modell ohne Parameterzahl weichen; verbietet er es, bleibt auch ein großes stehen |
| S49 | Bedarf und Ist-Wert | verplant (Budget) wird der Bedarf, als belegt gilt der gemessene Ist-Wert |

### Schlaf eines Rechners im Kern (`test_zuteiler.py`)

| Nr | Szenario | Erwartung |
|---|---|---|
| S50 | Stimme liegt nur auf Mac Studio, der schläft | Ablehnung `rechner_schlaeft` mit dem Rechner und dem Satz "Mac Studio schläft; der Auftrag kann erst laufen, wenn er wach ist."; Knotenzustand `schlaeft`; Lage ruhig mit Hinweis, nicht "nicht erreichbar" |
| S51 | Mac Studio unangekündigt weg (nicht schlafend) | `dienst_nicht_erreichbar` statt `zone_nicht_erlaubt`; ein externes Modell ohne Erlaubnis und eine Anwendung ohne Heimnetz bleiben `zone_nicht_erlaubt` |
| S52 | Hören liegt auf Mac Studio (schläft) und MacBook | das MacBook rechnet; ist es nur weg, `dienst_nicht_erreichbar`; schlafen beide, `rechner_schlaeft` mit beiden Namen |
| S53 | Laufender Auftrag auf einem schlafenden Rechner, GLM auf ihm und auf dem MacBook geladen | kein Lauf "Umverteilen bei Ausfall", kein Doppel, Lage ruhig; derselbe Fall ohne Schlaf: Ausfall, Doppel und Engpass |

## 3. Ende zu Ende (`test_ende_zu_ende.py`)

Leitstelle und Schein-Läufer laufen auf echten Ports; die Aufrufe kommen wie von einer Anwendung, die nur die
OpenAI-Schnittstelle kennt. Rechner, Dienst und Anwendung werden über die Verwaltung eingerichtet.

| Nr | Szenario | Erwartung |
|---|---|---|
| E01 | Strom an das geladene 80B-Modell | Antwort unverändert, Köpfe mit Auftrag und Lage, Verlauf mit Token, erstem Stück und Zeitleiste, Tageskennzahlen |
| E02 | Bild an ein nicht geladenes Modell, Name ohne Anbieter | die Leitstelle lädt vorher über die native Schnittstelle, misst die Ladezeit, Fähigkeit Bild beschreiben erkannt |
| E03 | Einbettung und Modelllisten | `/v1/embeddings`, `/v1/models` und die nachgebildete Läuferliste `/api/v0/models` mit Ladezustand |
| E04 | Ablehnungen | 404 `kein_modell`, 401 `unbekannter_schluessel`, 503 `halt` mit `Retry-After`, 429 `gesperrt`, nach Freigabe wieder 200; Prüfprotokoll |
| E05 | Sofort stoppen mitten im Strom | letztes Stück `leitstelle_abbruch` mit Teiltext-Länge, Auftrag abgebrochen mit Grund, der Läufer bricht ab |
| E06 | Anwendung trennt während des Stroms | Auftrag abgebrochen mit Grund `anwendung`, das Modell ist wieder frei |
| E07 | Drei Aufrufe bei einem Platz | der Läufer sieht nie mehr als einen gleichzeitig |
| E08 | Der Läufer lehnt das Laden wegen Speicher ab | Wartehinweise im Strom, wachsende Pausen, nach dem dritten Mal Fehler `modell_passt_nicht` im Strom |
| E09 | Budget reicht nicht neben dem ungenutzten 80B | Leerlauf räumen entlädt es über den Läufer, lädt GLM, der Auftrag läuft |
| E10 | Der Läufer hat das Modell selbst entladen | Antwort "not loaded", Neuversuch mit Laden, Erfolg |
| E11 | Herkunft außerhalb der erlaubten Netze | Verwaltung 403, Fassade weiter erreichbar |
| E12 | Live-Kanal | der erste Umschlag ist das Lagebild, danach Ereignisse bis `auftrag.ergebnis` |
| E13 | Titel mit Umlauten | prozentkodiert und als rohe UTF-8-Bytes richtig im Verlauf |
| E14 | Nach einem Neustart schon geladene Modelle | ohne bekannten Ladezeitpunkt gilt keine Mindestverweildauer; das ungenutzte 80B weicht nach der Bedarfsfrist |
| E15 | 60 Aufrufe von wenigen Millisekunden über die Dienstfassade und 20 sofortige Ablehnungen, alle gleichzeitig | jeder Auftrag steht mit seinem Endzustand im Verlauf (fertig oder abgelehnt), keine gescheiterte Schreibung; Speichern geht über die Schreibfolge |
| E16 | Anwendung trennt während der Durchleitung über die Dienstfassade, vor dem Antwortkopf und mitten in der Antwort, bei langsamem Schließen | abgebrochen mit Grund `anwendung` im Verlauf, Speicher leer, das Modell wieder frei, die Antwort des Dienstes geschlossen |

## 3a. Knoten-Agent (`test_knoten_agent.py`; A07 bis A10 im Repo des Maschinenraums, `tests/test_dienste.py`)

Echte Leitstelle auf einem Port, als Agent der Maschinenraum (Paket `maschinenraum`), ein kleiner HTTP-Server als
Prozessdienst.

| Nr. | Situation | Erwartet |
|---|---|---|
| A01 | Agent verbindet sich mit Schlüssel | Lagebild zeigt ihn verbunden mit Fassung; Speicher des Rechners ist der gemessene, System = belegt minus bekannte Modelle |
| A02 | Falscher Schlüssel | Verbindung wird mit 4401 `unbekannter_schluessel` geschlossen |
| A03 | Dienstliste des Agenten | Dienst "Dienste auf <Rechner>" (Art `agent`) entsteht; der Prozessdienst erscheint als Modell mit seinem Bedarf, ohne Ist-Wert, nicht geschützt; Laden startet ihn bis erreichbar, Entladen hält ihn an; beides im Prüfprotokoll |
| A04 | Agent trennt | eingetragene Speicherwerte gelten wieder; sein Dienst wird nicht erreichbar |
| A06 | Dienst braucht mehr, als er nach dem Start belegt | verplant wird der Bedarf (Budget), dem System zugerechnet nur, was die Modelle nicht wirklich belegen (Ist-Wert) |
| A07 | Dienstdatei verbietet der Leitstelle das Anhalten | Modell gilt als geschützt, Speicher freigeben lässt es stehen, ein Entladen von Hand lehnt der Maschinenraum ab |
| A08 | Anwendung ruft einen ausgeschalteten Dienst über `/v1/dienste/<name>/...` | Leitstelle startet ihn über den Maschinenraum, reicht Anfrage und Antwort unverändert durch (auch Fehlerstatus des Dienstes), Auftrag fertig mit Messung; ohne passende Fähigkeit `faehigkeit_nicht_erlaubt`, unbekannter Dienst `kein_modell`, ohne Schlüssel 401 |
| A05 | Neuer Agent-Schlüssel | der verbundene Agent wird getrennt und kommt mit dem alten Schlüssel nicht wieder herein |
| A07 | Absturz eines Dienstes, der laufen soll | Neustart nach Pause; mehr Abstürze im Zeitfenster als erlaubt: bleibt aus |
| A08 | Dienst läuft schon, von außen gestartet | wird übernommen statt doppelt gestartet; Anhalten trifft den lauschenden Prozess und seine Nachfahren |
| A09 | Agent oder Rechner startet neu | Sollzustand bleibt; eigene Gruppen werden innerhalb derselben Systemlaufzeit wiedererkannt, nach Rechnerneustart wird gestartet, was laufen soll |
| A10 | Dienst wird in der Startzeit nicht erreichbar | Versuch wird beendet, Meldung mit der letzten Protokollzeile |
| A11 | Der echte Kanal des Maschinenraums schläft ein und wacht auf | Leitstelle vermerkt sofort (unter 2 s), Dienstfassade 503 `rechner_schlaeft` mit Rechner; die Verbindung ruht; nach dem Aufwachen Anmeldung, Rechner erreichbar, Durchleitung wieder 200 |

## 3b. Schlaf eines Rechners (`test_schlaf.py`)

Leitstelle, Schein-Läufer und Schein-Agent (`tests/schein/agent.py`) auf echten Ports; Läufer und Agent liegen auf
demselben Rechner, wie LM Studio neben dem Maschinenraum.

| Nr | Szenario | Erwartung |
|---|---|---|
| R01 | Agent meldet `knoten.schlaeft` | Antwort `knoten.schlaf_vermerkt`; Rechner und beide Dienste `schlaeft`, null Fehlschläge, der Läufer wird nicht mehr gefragt; Lage ruhig mit "Mac Studio schläft"; Meldungen nennen Grund und Trennung |
| R02 | Aufrufe während des Schlafs | Chat mit und ohne Strom und Dienstfassade: 503 `rechner_schlaeft`, Retry-After 60, `error.x-leitstelle.rechner` = Mac Studio; im Verlauf abgelehnt mit diesem Grund |
| R03 | Zwei laufende Aufträge (mit und ohne Strom), Automatik "vorschlagen" | beide enden mit `rechner_schlaeft` (503 beziehungsweise letztes Stück `leitstelle_abbruch` mit Rechner), im Verlauf abgebrochen |
| R04 | Zwölf Stunden Schlaf mit vielen Takten (Stelluhr), Läufer antwortet nicht | kein Fehlschlag, kein Ausfall, keine Abfrage; nach dem Aufwachen ohne Takt sofort bereit, Meldung "aufgewacht nach 12,0 h", Chat geht |
| R05 | Neustart der Leitstelle während des Schlafs | Rechner und Dienste weiter `schlaeft`; ein danach unbekannter Name auf ihm gibt `rechner_schlaeft`; nach dem Aufwachen geht der Chat |
| R06 | Agent verschwindet ohne Meldung, Läufer antwortet nicht | 503 `dienst_nicht_erreichbar` (früher 403 `zone_nicht_erlaubt`), Retry-After 30, ohne Rechner |
| R07 | "Nicht mehr warten" von Hand | Dienste geprüft, Rechner nicht erreichbar, Aufrufe `dienst_nicht_erreichbar`; Prüfprotokoll; ein zweites Mal 404 |

## 4. Zweige je Vorlage

| Vorlage | Ende | Szenario |
|---|---|---|
| Umleiten | umgeleitet | S07 |
| | weiter warten | S09 (kein Platz), S10 (Zone), S11 (nicht installiert) |
| | warten lohnt mehr | S12, S42 |
| | Dienst läuft schon (Prüfung ja) | S12b |
| Leerlauf räumen | geräumt | S16, S12, S16b |
| | kein Leerlauf, der weichen darf | S17 (geschützt), S18 (Verweildauer), S19 (Bedarfsfrist) |
| | warten lohnt mehr | S16b |
| Vorwärmen | vorgewärmt | S20 |
| | kein Platz ohne Entladen | S21 |
| Kette ausweichen | ausgewichen | S22 |
| | keine geladene Alternative | S23 |
| | warten lohnt mehr | nur erreichbar, wenn die erwartete Wartezeit null ist; der Baustein ist in S43 geprüft |
| Extern ausweichen | extern | S24 |
| | Anwendung darf nicht extern | S25 |
| | Wartezeit unter der Schwelle | S25 |
| | kein externer Dienst | S25b |
| Umverteilen | umverteilt | S26, S37 |
| Verlagern | verlagert | S27 |
| Doppel auflösen | aufgelöst | S29 |
| | beide Kopien in Gebrauch oder geschützt | S30 |
| | kein Bedarf, Kopie bleibt | S30 |
| Hintergrund bei Lage | angehalten | S31 |
| | fortgesetzt | S31 |
| | nichts zu tun | S20, S34 (im Verlauf) |
| Sperren des Umschichters | Flattern | S34 |
| | Höchstzahl je Fenster | S36 |
| | eine je Knoten und Takt | im Zufallslauf S38 |
| | Umleitung nur einmal | S37 |
| | Automatik vorschlagen und aus | S32, S33 |
| | Hauptregler | S28 |

## 5. Ein Szenario hinzufügen

1. Nummer vergeben (nächste freie), Test in die passende Datei, Docstring mit dem Satz, der das
   Szenario für Menschen erklärt.
2. Welt mit `welt_mit(**regeln)` aufbauen, Zustand mit `lade`, `entlade`, Budgets und Dienstzuständen
   einstellen; nie an der Wahrheit der Welt vorbei entscheiden (die Leitstelle sieht nur Messungen).
3. Erwartung über `ausgefuehrt`, `gesperrt`, `abschluesse` (Ende-Titel der Regel) und die Zustände im
   Verbund prüfen; Begründungen als Wortlaut prüfen, weil sie in der Oberfläche stehen.
4. Zeile hier eintragen, bei neuen Zweigen auch in Abschnitt 3.
