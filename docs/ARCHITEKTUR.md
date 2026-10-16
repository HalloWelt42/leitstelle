# Architektur der Leitstelle

Stand 16.10.2026, Entwurfsphase. Dieses Dokument ist die eine Wahrheit über Schichten, Verantwortungen
und Übergabepunkte. Was hier steht, gilt für Kern, Agenten, Adapter, Bibliotheken und Oberfläche.

## 1. Zweck in drei Sätzen

Die Leitstelle kennt alle Rechner (Knoten), alle KI-Dienste darauf und alle Modelle im Verbund, dazu
externe Anbieter. Anwendungen melden sich an und geben Aufträge ab; die Leitstelle wählt Dienst und
Modell, reiht nach Priorität ein, verwaltet den Speicher und führt den Auftrag aus oder leitet ihn
durch. Zurück fließen Fortschritt, Ergebnis und Signale (Speicher knapp, pausiert, gesperrt, Modell
bereit), damit sich jede Anwendung auf die Lage einstellen kann.

## Grundsätze der Rollen (Nutzer, 16.10.2026)

- **Die Leitstelle vermittelt nur.** Sie lädt nie selbst ein Modell und rechnet nie selbst; sie nutzt Kommunikation
  und Zustände. Geladen und gerechnet wird im Modell-Läufer oder im Maschinenraum des jeweiligen Rechners, auf ihre
  Anweisung. Die Leitstelle hat keine Modellbibliothek und bekommt keine.
- **Der Maschinenraum bündelt alles, was der Modell-Läufer nicht verwaltet**, je Rechner, und ist für sich allein
  bedienbar wie der Modell-Läufer.
- **Alles geht nur über die Leitstelle:** Anwendungen sprechen nur mit ihr (Fassade, auch `/v1/dienste/...`); die
  Dienste lauschen nur auf ihrem Rechner und sind nur über die Durchleitung des Maschinenraums erreichbar.
- **Die Leitstelle sieht nur Fähigkeiten:** Programme ohne Fähigkeit (Oberflächen, Backends von Anwendungen,
  Datenbanken) verwaltet allein der Maschinenraum.

## 2. Rollen und Bausteine

```
 Anwendungen                     Leitstelle (Kern)                        Knoten
 -----------                     -----------------                        ------
 Zusage, Fundus, ...   ------>   Fassade /v1    --+                    +-- Knoten-Agent (Python)
   über Bibliothek               Protokoll      --+-> Vermittlung -> Adapter -> Dienste (Modell-Läufer,
   oder nur Adresse              /api/kanal     --+   Zuteiler       (Plugins)  txt2voice, Bild-Werkbank,
                      <------   Signale, Fortschritt, Ergebnis                  extern ...)
                                 Speicherplaner, Regeln, Lage
                                 SQLite, Prüfprotokoll, Geheimnisse
                                 Oberfläche (Svelte)
```

| Baustein | Verantwortung | Sprache | Ort |
|---|---|---|---|
| Kern | Vermittlung, Zuteilung, Speicherplanung, Signale, Regeln, Daten, Oberfläche ausliefern | Python 3.12, FastAPI | ein Rechner im Heimnetz (Pi in Docker oder Mac per launchd) |
| Knoten-Agent | misst (Speicher, Swap, Last, Platte, Prozessor, Grafik, Temperatur, Leistung), verwaltet die Prozessdienste des Rechners aus seinem Ordner (starten, anhalten, Absturz, Sollzustand) | Python (Entscheidung 16.10.2026), eigenes venv, als launchd- oder systemd-Dienst; Messwege über Bordmittel (`vm_stat`, `sysctl`, `/proc`), auf dem Mac ergänzt um macmon, wenn vorhanden | jeder Rechner |
| Dienst-Adapter | übersetzt zwischen Auftrag und der Schnittstelle eines Dienstes; meldet Fähigkeiten, Modelle, Zustand; lädt und entlädt Modelle | Python, Plugins im Kern | Kern |
| Anwendungs-Bibliothek | Anmeldung, Herzschlag, Aufträge, Signalkanal in drei Zeilen | Python, TypeScript, später Swift | in den Anwendungen |
| Fassade | OpenAI-kompatible Endpunkte `/v1/*`, damit Anwendungen ohne Umbau sofort laufen | Teil des Kerns | Kern |
| Oberfläche | Lagebild, Aufträge, Knoten, Dienste, Modelle, Anwendungen, Regeln, Nachrichtenverkehr, Verlauf, Sicherheit, Protokoll, Hilfe | Svelte 5, TypeScript, Vite | vom Kern ausgeliefert |

Warum Python für den Agenten (Entscheidung des Nutzers): eine Sprache im ganzen Projekt, dieselben
Modelle und Schemata wie im Kern, auf Macs und Pis ist Python ohnehin da. Umgesetzt ist der Agent als eigenes
Programm, der Maschinenraum (Repo HalloWelt42/maschinenraum, Entscheidung des Nutzers 16.10.2026: eine zweite
zentrale Stelle neben dem Modell-Läufer, mit eigener Oberfläche und Menüleistensymbol, auch ohne Leitstelle
nutzbar). Sein Installationsskript legt ein eigenes venv an und richtet den Dienst ein; er misst mit Bordmitteln des Systems (ohne Zusatzpaket),
auf dem Mac kommen Grafik, Leistung und Temperatur über macmon dazu, wenn es installiert ist. Die Prozessdienste
des Rechners erscheinen in der Leitstelle als ein Dienst der Art `agent`, dessen Modelle die Programme sind:
Starten ist Laden, Anhalten ist Entladen. So gelten Speicherplanung, Prüfprotokoll und Oberfläche ohne Sonderweg
(Einzelheiten im README des Maschinenraums). Bremst der Agent
einen Pi messbar, wird der Messteil später in ein Binary ausgelagert, die Schnittstelle bleibt. Warum
Python für den Kern: Standard aller Backends des Hauses, die Last ist Vermittlung und Durchleitung, nicht
Rechnen. Die Durchleitung (Streams vom Dienst zur Anwendung) ist ein eigener Baustein hinter einer
Schnittstelle; zeigt eine Messung, dass sie bremst, kann sie in Go oder Rust nachgebaut werden, ohne
dass der Rest etwas merkt (siehe Staffel 1, Messpunkt).

## 3. Schichten im Kern

Ordnung nach dem Muster, das Zusage und Kiste schon verwenden (Kern, Fach, Ports, Vorgänge, API):

```
backend/leitstelle/
  kern/          reine Fachlogik ohne Ein- und Ausgabe: Modelle (Pydantic), Zustände (Enums),
                 Zuteiler, Speicherplaner, Prioritätsrechner, Lagebeurteilung, Zeitgrenzen-Regeln
  fach/          Anwendungsfälle: Vermittlung (Auftrag annehmen, planen, zuteilen, ausführen),
                 Speicherverwaltung, Signalgeber, Kostenwächter, Anmeldung, Prüfprotokoll
  ports/         Schnittstellen (Protokolle) und ihre Umsetzungen:
    dienste/     Adapter-Schnittstelle + Plugins (openai_kompatibel, txt2voice, hoeren_http,
                 bildwerkbank, sprecher_klein, extern_openai, eigener Adapter über das Protokoll)
    knoten/      Gegenstelle der Knoten-Agenten (Messwerte, Entdeckung, Befehle)
    ablage/      SQLite-Repositorien (Knoten, Dienste, Modelle, Anwendungen, Aufträge, Nachrichten,
                 Messwerte roh/Minute/Stunde, Regeln, Prüfprotokoll)
    geheimnisse/ verschlüsselte Ablage der Schlüssel (Anwendungen, Agenten, externe Anbieter)
    durchleitung/ Streams vom Dienst zur Anwendung (austauschbar)
    uhr.py       Zeitquelle (für Tests ersetzbar)
  vorgaenge/     Dauerläufer: Läufer (führt zugeteilte Aufträge aus), Umschichter (Selbststeuerung),
                 Herzschlag-Wächter, Messwert-Verdichter, Aufräumer (Aufbewahrung), Kosten-Abgleich
  api/           FastAPI-Router: /api/* (eigene Schnittstelle), /v1/* (Fassade),
                 /api/kanal (WebSocket), /api/nachrichten (Umschläge per HTTP)
  protokoll/     Umschlag, Nachrichtenarten, JSON-Schemata (eine Wahrheit, auch für die Bibliotheken)
  konfig.py      Einstellungen (pydantic-settings, Vorsilbe LEITSTELLE_), Version aus version.json
```

Regeln für die Schichten:

- `kern` importiert nichts aus den anderen Schichten. Jede Entscheidung (Zuteilung, Speicherplan,
  Lage) ist eine reine Funktion über Eingabedaten und liefert neben dem Ergebnis eine **Begründung**
  in Worten. Die Oberfläche zeigt diese Begründung an ("Wartet: Modell ist mit einem Auftrag höherer
  Priorität belegt"). So bleibt alles erklärbar und testbar.
- `fach` orchestriert Kern und Ports, hält aber keinen Zustand außer über die Ablage.
- `ports` sind schmale Protokolle (typing.Protocol) mit mindestens einer echten Umsetzung und einer
  Attrappe für Tests.
- Niemand spricht an der Schnittstelle vorbei mit einem Dienst oder der Datenbank.

## 4. Fachmodell

Alle Daten sind Pydantic-Modelle (Python) beziehungsweise Interfaces (TypeScript), nie rohe Dicts.
Schlüssel sind UUIDs; nach außen zeigen wir Wörter, nie Schlüssel.

| Begriff | Bedeutung | Wichtige Felder |
|---|---|---|
| Knoten | ein Rechner mit Agent | Kennung, Name, Zone (heim, fern, extern), Adresse, Messwerte, Zustand (erreichbar, nicht erreichbar, wartung), Regeln (Budget, Zeitfenster) |
| Dienst | ein Anbieter von Fähigkeiten auf einem Knoten oder extern | Kennung, Art (Adapter), Adresse, Fähigkeiten, Modelle, Zustand (bereit, rechnet, pausiert, nicht erreichbar), Besonderheiten, Kosten |
| Modell | ein ladbares Modell eines Dienstes | Kennung, Name, Aliasse (Namen beim Anbieter: Schlüssel und Instanz-Kennung), Fähigkeit, Größe, Kontext, Parameterzahl, Zustand (frei, lädt, geladen, rechnet, extern), geschützt |
| Fähigkeit | was ein Auftrag braucht | Werteliste: text, einbettung, uebersetzen, hoeren, bild_beschreiben, bild_erzeugen, bild_freistellen, musik, stimme, stimme_klonen, werkzeug; erweiterbar über die Registry |
| Anwendung | ein angemeldeter Verbraucher | Kennung, Name, Schlüssel (verschlüsselt), erlaubte Fähigkeiten, Zonen, Kostengrenze, Vorgabe-Priorität, Kette je Fähigkeit, Herkunft (Adressen), Umbau-Stufe, Signalkanal ja/nein |
| Auftrag | eine Arbeit einer Anwendung | Kennung, Anwendung, Fähigkeit, Eingabe, Modellwunsch oder Kette, Priorität, Zustand, Zuteilung (Dienst, Modell, Knoten), Fortschritt, Schritte, Begründung, Messwerte (Dauer, erstes Stück, Token), Kosten |
| Regelwerk | alles Einstellbare an einem Ort | Prioritäten, Speicher je Knoten, Schutzgrenze, Leerlauf, Zeitgrenzen, Zeitfenster, Extern |
| Lage | Gesamtzustand des Verbunds | ruhig, angespannt, engpass; mit Begründung |
| Nachricht | Umschlag des Protokolls | siehe PROTOKOLL.md |

### Zustände eines Auftrags

```
 angelegt -> eingereiht -> zugeteilt -> laeuft -> fertig
                │             │           │
                │             │           ├-> pausiert -> laeuft (fortsetzen)
                │             │           ├-> auslaufend -> fertig
                │             │           └-> abgebrochen
                ├-> wartet_speicher -> zugeteilt
                └-> abgelehnt
 jeder Zustand -> fehlgeschlagen
```

Anhalten ist nur erlaubt, wenn der Adapter es für diese Auftragsart kann (Stapelarbeit mit
Abschnitten: ja; ein laufender Textstrom: nein, der kann nur auslaufen oder stoppen). Das weiß die
Oberfläche vorab, ein Knopf ohne Wirkung gibt es nicht.

## 5. Die vier Entscheidungen des Kerns

### 5.1 Zuteilung (Zuteiler)

Eingabe: Auftrag, Zustand aller Dienste und Modelle, Warteschlange, Regelwerk. Ausgabe: Zuteilung
(Dienst, Modell, Knoten) oder "warten" mit Grund, oder "ablehnen" mit Grund.

Reihenfolge der Prüfung:

1. Darf die Anwendung diese Fähigkeit und diese Zone? Sonst ablehnen (Server erzwingt, was die
   Oberfläche versteckt).
2. Kette der Anwendung für die Fähigkeit, sonst Kette der Leitstelle. Innerhalb der Kette gilt:
   ein schon geladenes Modell geht vor einem nicht geladenen; ein freies vor einem rechnenden.
3. Passt das Modell in den Speicher des Knotens (Speicherplaner)? Wenn nein: `wartet_speicher`
   mit Vorhersage, wann es passt (Rest des blockierenden Auftrags).
4. Plätze: je Modell höchstens die eingestellte Zahl gleichzeitiger Aufträge (Vorgabe 1 für große
   Textmodelle, Stapel für Einbettung).
5. Priorität: dringend > hoch > normal > hintergrund; innerhalb gleicher Stufe nach Eingang.
   Fairness: eine Anwendung bekommt höchstens den eingestellten Anteil der Plätze, Hintergrund kommt
   spätestens nach der eingestellten Wartezeit dran. Dringend darf laufende Hintergrundarbeit
   anhalten, wenn der Adapter das kann.
6. Direktweg: Ist das Modell geladen und frei und die Priorität dringend oder hoch, geht der
   Auftrag ohne Umweg über die Warteschlange zum Dienst (Latenz für Sprachassistent und
   Schreibhilfe).

### 5.2 Speicherplan (Speicherplaner)

Löst die zwei bisherigen Modell-Manager (txt2voice, Zusage) ab und übernimmt ihre Regeln:

- Budget je Knoten (Vorgabe Gesamtspeicher minus 18 GB), echte Größen aus dem Dienst.
- Nie entladen: Modelle unter der Schutzgrenze (Vorgabe 10 Milliarden Parameter), Einbettungsmodelle,
  rechnende Modelle, Modelle mit wartenden Aufträgen.
- Nur so viel entladen wie nötig, größte zuerst (einstellbar: älteste zuerst).
- Leerlauf-Entladen ist aus; es wird nur entladen, wenn Platz für ein angefordertes Modell fehlt.
- Nach dem Entladen wartet der Planer, bis der Knoten den Speicher wirklich freigemeldet hat
  (Agent-Messwert), statt eine feste Pause zu raten; dann laden mit Wiederholung bei "nicht genug
  Speicher".
- Gesundheitsprüfungen laden nie ein Modell.
- Der Plan ist eine reine Funktion und damit zugleich die **Vorschau** ("Speicher freigeben" zeigt
  erst, was passieren würde).

### 5.3 Lage

Aus Messwerten und Warteschlange: ruhig (alles erreichbar, keine Wartezeit), angespannt (ein Knoten
über der Speicherwarnschwelle oder ein Auftrag wartet auf Speicher), engpass (mehrere warten oder ein
Knoten fehlt). Die Lage steuert Regeln (Hintergrund bei angespannter Lage anhalten) und wird als
Signal verteilt.

### 5.4 Signale

Der Signalgeber beobachtet Zustandsänderungen (Speicher, Lage, Modell geladen oder entladen, Sperre,
Pause, Kosten, Zone) und schickt jeder betroffenen Teilnehmerin genau die Signale, die sie angeht:
eine Anwendung erfährt vom knappen Speicher, wenn einer ihrer Aufträge wartet oder sie den Knoten
abonniert hat; ein Dienst erfährt, dass er pausiert ist. Keine Sendung an alle, kein Rauschen.

### 5.5 Hauptregler (Betriebsmodus)

Ein zentraler Schalter mit drei Stellungen, in der Kopfleiste jeder Ansicht und am Telefon:

| Stellung | Wirkung | Signale |
|---|---|---|
| Normal | Aufträge werden angenommen und verteilt | - |
| Auslaufen (sanft) | laufende Aufträge rechnen zu Ende, die Warteschlange ruht, neue Anfragen werden mit Grund abgelehnt | `signal.gesperrt` (was: leitstelle) an alle Anwendungen, `signal.lage` |
| Halt (harter Schnitt) | alle laufenden Aufträge stoppen sofort, Anwendungen bekommen den bisherigen Stand als Teilergebnis | `auftrag.abgebrochen` je Auftrag, `signal.gesperrt`, `signal.lage` |

Dazu der Schalter "Hintergrund" (Stapelarbeit anhalten oder laufen lassen). Halt und Auslaufen zeigen vor dem
Tun ihre Folgen (Zahl der betroffenen Aufträge, längster Rest, was die Anwendungen bekommen) und nehmen einen
Grund für die Anwendungen entgegen. Nachricht: `leitstelle.modus` (siehe PROTOKOLL.md). Zurück zu Normal nimmt
die Warteschlange wieder auf; abgebrochene Aufträge bleiben als abgebrochen stehen und lassen sich neu einreihen.

### 5.6 Selbststeuerung (verbundweite Umschichtung)

Die Leitstelle wartet nicht nur auf Anfragen, sie beobachtet den ganzen Verbund laufend und schichtet
von selbst um. Ein Dauerläufer `vorgaenge/umschichter.py` prüft im Takt (Vorgabe 5 s) die Lage aller
Knoten, die Warteschlange und die Messwerte und leitet aus Regeln Maßnahmen ab. Jede Maßnahme ist ein
Fachobjekt mit Grund, erwartetem Gewinn, gemessenen Kosten, Zustand (geplant, ausgeführt, geprüft ohne
Aktion, nicht ausgelöst, rückgängig) und Nachricht `leitstelle.massnahme`; sie erscheint in Meldungen und
Protokoll und lässt sich rückgängig machen oder als Regel abschalten ("so nicht mehr").

| Szenario | Maßnahme | Bedingungen |
|---|---|---|
| Ein Auftrag wartet auf Speicher am großen Rechner, ein anderer Rechner hat Platz | **Umleiten**: Modell dort laden, Auftrag dorthin zuteilen; fehlt der Dienst, startet ihn der Agent (installiert, aber nicht laufend) | Anwendung darf den Knoten (Zone), Modell passt, Gewinnschwelle erfüllt |
| Ein Modell belegt Speicher ohne Auftrag, ein wartender Auftrag braucht den Platz | **Leerlauf räumen**: entladen, dann laden | nur bei Bedarf, nie geschützte oder rechnende Modelle, Bedarfsfrist (Vorgabe 60 s ohne Auftrag) erreicht, Mindestverweildauer vorbei; Gewinn ist die Wartezeit, die der Auftrag sonst hätte (bis ein rechnendes Modell fertig wäre, sonst unbestimmt lange) |
| In der Warteschlange steht ein Auftrag für ein nicht geladenes Modell, irgendwo ist Platz | **Vorwärmen**: Modell laden, bevor der Auftrag an der Reihe ist | Platz ohne Entladen, oder Platz nach einem absehbaren Ende (Rest eines laufenden Auftrags) |
| Der große Rechner ist ausgelastet, der kleine hat ein kleineres Modell derselben Kette frei | **Ausweichen in der Kette**: nächstes passendes Modell der Kette auf dem freien Rechner | Kette erlaubt es, Anwendung hat kein festes Modell verlangt |
| Erwartete Wartezeit über der Schwelle, Anwendung darf extern | **Extern ausweichen** | Tagesgrenze, Zone extern erlaubt, Schwelle (Vorgabe 2 min) |
| Dienst oder Knoten fällt aus | **Umverteilen**: laufende Aufträge der Anwendung mit Teilergebnis melden, wartende auf andere Knoten | Fähigkeit anderswo vorhanden |
| Zeitfenster beginnt (Nacht) | **Verlagern** von Hintergrundarbeit auf den dafür freigegebenen Rechner | Regel Zeitfenster |
| Dasselbe Modell auf zwei Rechnern, eines ohne Auftrag, anderswo fehlt Platz | **Doppel auflösen**: die ungenutzte Kopie entladen | nur bei Bedarf, Mindestverweildauer |
| Lage wechselt auf angespannt oder Engpass | **Hintergrund bei Lage**: Hintergrundaufträge anhalten (nur zwischen Abschnitten), bei ruhiger Lage fortsetzen | Regel schaltbar; die Fairness bleibt: nach spätestens 15 min rückt Hintergrund auf Normal und läuft trotzdem |

Entscheidungen beruhen auf Messungen, nicht auf Geld: Ladezeit je Modellfamilie und Knoten, Startzeit je
Dienst, Laufzeit je Anwendung und Fähigkeit, Zeit bis erstes Stück, alle als gleitendes Mittel im
`Messwerk`. Ohne Messung gilt ein vorsichtiger Schätzwert (Laden: 0,4 s je GB, mindestens 5 s), der mit
der ersten Messung ersetzt wird. Gewinn und Aufwand jeder Maßnahme sind Sekunden. Die Leitstelle kennt
die wahre Restlaufzeit eines Auftrags nie; sie schätzt sie aus gemessenen Laufzeiten und Fortschritt.

Schleifenschutz (alles im Kern geprüft, siehe [SZENARIEN.md](SZENARIEN.md)):

1. **Hauptregler vor Regelwerk**: bei Auslaufen und Halt wird nichts umgeschichtet.
2. **Gewinnschwelle**: Maßnahme nur, wenn der geschätzte Gewinn den gemessenen Aufwand um den Faktor
   (Vorgabe 2) übersteigt; in der Kette (Aufwand null) Faktor 1.
3. **Mindestverweildauer** je Modell (Vorgabe 10 min): frisch Geladenes weicht nicht.
4. **Bedarfsfrist** (Vorgabe 60 s): ein Modell weicht einem wartenden Auftrag erst, wenn es so lange
   keinen Auftrag hatte. Ohne Bedarf wird nie entladen; die Leerlaufgrenze (Vorgabe 30 min) sagt nur, ab
   wann ein Modell in den Listen als Leerlauf steht.
5. **Schutzgrenze**: Modelle unter 10 Milliarden Parametern, Einbettungen und ausdrücklich geschützte
   werden nie entladen; rechnende oder zugeteilte sowieso nicht.
6. **Flattern**: dieselbe Bewegung (Laden oder Entladen derselben Familie auf demselben Knoten) zum
   zweiten Mal innerhalb des Fensters (Vorgabe 10 min) gilt als Flattern; die beteiligten Familien sind
   auf dem Knoten für die Ruhezeit (Vorgabe 30 min) gesperrt, die Maßnahme erscheint als gesperrt mit
   Grund. Ladevorgänge des Zuteilers zählen mit.
7. **Höchstzahl** von Maßnahmen je Fenster (Vorgabe 6) und höchstens eine Maßnahme je Knoten und Takt.
8. **Höchstens eine Umleitung je Auftrag** (einstellbar).
9. **Fairness**: Hintergrund rückt nach spätestens 15 min auf Normal, auch bei angehaltenem Hintergrund.
10. **Takt**: der Umschichter läuft alle 5 s, Auslöser greifen erst nach einer Mindestwartezeit (5 s),
    damit der Zuteiler zuerst seine Arbeit tun kann (geladene Modelle zuerst, Laden ohne Entladen).

Automatik-Stufen (Regel): Aus, Vorschlagen (Maßnahmen warten auf einen Klick), Selbst handeln (Vorgabe,
Wunsch des Nutzers). Jedes Szenario ist einzeln schaltbar. Der Hauptregler geht immer vor: bei Auslaufen
und Halt schichtet die Leitstelle nichts um.

### 5.7 Regelwerk als Graph

Alle Regeln der Selbststeuerung (und die Zuteilungsregeln aus 5.1) sind keine festen Programmzweige,
sondern **Regelgraphen**: ein Auslöser, eine Folge von Prüfungen mit Ja- und Nein-Ausgängen, Aktionen
und ein Abschluss. Die Leitstelle liefert die Szenarien aus 5.6 als Vorlagen mit; der Nutzer kopiert,
ändert, schaltet ab oder baut eigene Regeln ("Nachts alles auf das MacBook", "Rufzeichen immer zuerst").

- **Bausteine** mit festen Ein- und Ausgängen: Auslöser (Auftrag wartet auf Speicher, Modell im Leerlauf,
  Lage wechselt, Zeitfenster beginnt, Knoten fällt aus, Warteschlange enthält, Wartezeit überschreitet),
  Prüfungen (anderer Knoten mit Platz, Anwendung darf Zone, Gewinn gegen Kosten, Modell geschützt,
  Mindestverweildauer vorbei, Dienst installiert, Tagesgrenze reicht, Kette hat Ausweich), Aktionen (Dienst
  starten, Modell laden, Modell entladen, Auftrag umleiten, Priorität ändern, Signal senden, Melden, Extern
  rechnen, Aufträge anhalten), Fluss (Ja oder Nein, Alle erfüllt, Eine erfüllt, Warten bis, Ende).
  Neue Bausteine kommen über eine Registry (Python-Klasse mit Parametern, Ein- und Ausgängen, Erklärung,
  Begründungstext mit Platzhaltern); der Editor liest die Registry und zeigt sie als Palette.
- **Auswertung** im Kern: der Umschichter nimmt den Graph als Daten (Pydantic-Modell `Regelgraph`),
  prüft ihn beim Speichern (Zyklen, offene Ausgänge, Typen der Anschlüsse) und wertet ihn deterministisch
  aus; jeder Lauf erzeugt den genommenen Weg mit allen Zwischenwerten. Daraus entstehen Begründung
  (Platzhalter gefüllt), Maßnahme und Trockenlauf. Kein beliebiger Code im Graph; Prüfungen und Aktionen
  sind die mitgelieferten Bausteine mit Parametern.
- **Trockenlauf**: derselbe Auswerter gegen den aktuellen Zustand ohne Aktionen; der genommene Weg leuchtet
  im Graph, die Zwischenwerte stehen an den Knoten.
- **Fassungen**: jede Speicherung ist eine neue Fassung mit Änderungsnotiz; Zurück zur Vorlage jederzeit.
- **Darstellung** wie der Techbaum in Orbit: Spalten als Ebenen, Knoten als Kacheln, Kanten rechtwinklig
  wie im Schaltplan, Fläche verschieb- und zoombar. Der Editor nutzt eine Graph-Bibliothek (siehe 13); die
  rechtwinklige Verdrahtung und Anordnung (aus einem Techbaum-Editor eines anderen Projekts des Autors) wird
  als Auto-Anordnung für Vorlagen übernommen.
- **Vorrang**: Hauptregler vor Regelwerk; Regeln mit Zahl (Reihenfolge) für den Fall, dass mehrere
  gleichzeitig greifen; jede Regel einzeln an oder aus.

## 6. Übergabepunkte (Schnittstellen)

| Punkt | Wer mit wem | Form |
|---|---|---|
| Fassade | Anwendung ohne Umbau mit Leitstelle | HTTP, OpenAI-Format `/v1/models`, `/v1/chat/completions`, `/v1/embeddings`, `/v1/audio/transcriptions`, `/v1/audio/speech`, `/v1/images/generations`; Schlüssel als Bearer; Streaming als SSE |
| Protokoll | Anwendung, Dienst, Knoten mit Leitstelle | JSON-Umschlag über WebSocket `/api/kanal` oder HTTP `/api/nachrichten`, siehe PROTOKOLL.md |
| Adapter | Kern mit Dienst | Python-Protokoll `DienstAdapter`: `faehigkeiten()`, `modelle()`, `gesundheit()` (lädt nie), `laden(modell)`, `entladen(modell)`, `ausfuehren(auftrag) -> AsyncIterator[Ereignis]`, `abbrechen(auftrag)`, `anhalten(auftrag)` optional |
| Knoten-Agent | Agent mit Kern | dasselbe Protokoll, Arten `knoten.*`; Agent verbindet sich zum Kern (ausgehend), der Kern öffnet keine Ports auf den Knoten |
| Ablage | Fach mit Datenbank | Repositorien je Aggregat, SQLite WAL, Migrationen beim Start |
| Oberfläche | Browser mit Kern | `/api/*` lesend seitenweise, `/api/kanal` für Live-Daten, je Datenart eigener Takt |

## 7. Datenhaltung

SQLite im WAL-Modus im Datenordner (zum Beispiel auf der SSD eines Pi). Tabellen: knoten,
dienste, modelle, modell_aliasse, anwendungen, auftraege, auftrag_schritte, nachrichten (14 Tage),
messwerte_roh (24 Stunden), messwerte_minute (30 Tage), messwerte_stunde (365 Tage), regeln,
geheimnisse (verschlüsselt), pruefprotokoll (nur anhängen, nie löschen), kosten.

Der Aufräumer verdichtet Messwerte und löscht nach der eingestellten Aufbewahrung; Diagramme lesen
immer die passende Verdichtung. Lange Listen liefert die Schnittstelle seitenweise.

## 8. Sicherheit

- Zonen: heim (Heimnetz), fern (über VPN erreichbar), extern (fremder Anbieter). Daten verlassen das
  Heimnetz nur, wenn die Anwendung es darf und die Tagesgrenze es zulässt; jeder externe Auftrag steht
  im Prüfprotokoll.
- Schlüssel: je Anwendung und je Agent ein eigener, stabil, verschlüsselt abgelegt; in der Oberfläche
  verdeckt, das Auge deckt auf (mit Eintrag im Prüfprotokoll), neu erzeugen nur bewusst mit Bestätigung.
  Herkunftsadressen je Anwendung, Rate je Minute, alles serverseitig geprüft.
- Externe Anbieter: der Schlüssel liegt nur in der Leitstelle; Anwendungen sehen ihn nie.
- Oberfläche: nur aus Heimnetz und VPN, Anmeldung mit Passkey, Einmalcode als Rückfall, HTTPS mit
  eigenem Zertifikat.
- Agenten lesen keine Nutzerdaten; sie messen und steuern Dienste nur auf Befehl.
- Alles, was die Oberfläche ausgraut, weist der Server selbst ab.
- Anschlussstellen minimal-invasiv: jede Anschlussstelle (Rechner, Dienst, externer Anbieter, Anwendung)
  wird in der Oberfläche mit den wenigsten nötigen Angaben eingerichtet (Adresse; Zugang oder Schlüssel nur,
  wenn die Gegenstelle einen verlangt). Art, Fähigkeiten, Modelle, Knoten und Zone erkennt die Leitstelle über
  eine Erkennung, die nichts verändert und nichts lädt. Rechner brauchen nur den Installationsbefehl des Agenten.
- Verschlüsselter Weg: Knoten-Agenten verbinden sich immer über TLS (WebSocket wss) zur Leitstelle, deren
  Zertifikat beim Installieren fest hinterlegt wird, auch im Heimnetz. Eigene Dienste auf fremden Servern
  (Mietserver) werden über ihren Agenten oder den VPN-Tunnel angebunden, nie offen ins Internet. Externe Anbieter
  nur über HTTPS mit geprüftem Zertifikat. Im Heimnetz ist Klartext zu Diensten erlaubt, HTTPS wird bevorzugt.

## 9. Zeit und Robustheit

- Arbeit bekommt keine Lese-Zeitgrenze, nur eine Verbindungsgrenze (30 s) und einen
  Stillstands-Wächter (ohne neues Stück länger als eingestellt: Warnung, kein Abbruch ohne Regel).
- Teilausfall vernichtet nie den teuren Zwischenstand: ein Stream, der abbricht, liefert das bisher
  Erzeugte mit dem Signal `abgebrochen`.
- Jeder Dauerläufer hat einen Herzschlag, der im Protokoll sichtbar ist.
- Wiederholungen nur für Verbindungsfehler und "nicht genug Speicher", mit sichtbaren Pausen.

## 10. Erweiterbarkeit

- Neue Dienstart = neues Adapter-Modul in `ports/dienste/` plus Eintrag in der Registry; kein
  Sonderfall im Kern.
- Neue Fähigkeit = Eintrag in der Fähigkeiten-Registry mit Wort, Symbol, Farbe; Oberfläche und
  Protokoll nehmen sie automatisch auf.
- Neue Nachrichtenart = Schema in `protokoll/`, Bibliotheken ignorieren Unbekanntes.
- Oberfläche: je Seite ein Baustein, Datenfrische je Datenart im Store.

## 11. Testbarkeit

- `kern`: reine Funktionen, Tabellen-Tests für Zuteilung, Speicherplan, Lage.
- `fach`: mit Attrappen der Ports (Schein-Dienst, Schein-Agent, Schein-Uhr).
- Adapter: gegen aufgezeichnete Antworten, nie gegen den echten Modell-Läufer in Tests.
- Protokoll: JSON-Schemata prüfen Umschläge; dieselben Schemata laufen in den Bibliotheken.
- Ende zu Ende: ein Schein-Dienst im OpenAI-Format in `tests/schein/`, dagegen Fassade und Protokoll.
- Lasttest der Durchleitung mit messbaren Zahlen (Staffel 1), damit die Sprachfrage nach Messung
  entschieden wird.
- **Schein-Verbund** (`backend/leitstelle/simulation/`): eine vollständig gemockte Welt mit 4 Knoten,
  5 Anbindungen, 14 Modellinstanzen und 8 Anwendungen nach dem echten Bestand. Die Welt kennt eine
  verborgene Wahrheit (wahre Ladezeiten, Startzeiten, Laufzeiten), die Leitstelle sieht nur, was sie misst.
  Darauf laufen der Szenarienkatalog [SZENARIEN.md](SZENARIEN.md) (jeder Zweig jeder Vorlage), die
  Schleifenschutz-Tests und Zufallsläufe über eine Stunde mit Invarianten (Budget nie überschritten,
  Geschütztes nie entladen, Zone nie verletzt, extern nie ohne Erlaubnis, nichts verhungert).
  `cd backend && .venv/bin/python -m pytest`.

## 12. Bibliotheken für Wichtiges

Für tragende Teile werden erprobte Bibliotheken genommen, kein Eigenbau (Wunsch des Nutzers). Eigenbau nur
für Fachlogik und für Dinge, die es nicht passend gibt.

| Zweck | Bibliothek | Warum |
|---|---|---|
| Oberfläche | Svelte 5 mit TypeScript, Vite | Hausstandard |
| Regel-Graph-Editor | `@xyflow/svelte` (Svelte Flow): eigene Knotenbausteine, rechtwinklige Kanten, Zoom, Ziehen, Auswahl | ausgereifter Editor statt eigenem Canvas; Anordnung der Vorlagen aus Orbits Techbaum-Verdrahtung |
| Diagramme (Verlauf, Knoten) | `chart.js` | im Haus erprobt (txt2voice), dunkles Thema bekannt; Netzbild bleibt eigenes SVG, weil es die Fachsemantik zeigt |
| Hilfe-Fenster | Muster aus `hilfe-fenster-demo`, Markdown mit `marked` | bewährt in morf-gpt |
| Schriften, Symbole | `@fontsource/barlow`, `@fontsource/chakra-petch`, `@fortawesome/fontawesome-free` | kein CDN |
| Kern | FastAPI, Pydantic v2 (Modelle und JSON-Schema-Export), httpx (Streams ohne Lese-Zeitgrenze), uvicorn | Hausstandard |
| Datenhaltung | SQLAlchemy 2 (async) mit aiosqlite, Alembic für Migrationen | Migrationen beim Start wie TubeVault |
| Geheimnisse | `cryptography` (Fernet) für Schlüssel und Anbieter-Token | geprüfte Verschlüsselung statt eigener |
| Anmeldung Oberfläche | `py_webauthn` (Passkey), `pyotp` (Einmalcode) | wie bei FauPeeN bewährt |
| Knoten-Agent | `websockets` für den Kanal, `pydantic` für die Nutzlasten; Messwerte über Bordmittel, auf dem Mac macmon als Zusatz | eine Sprache, überall vorhanden, keine Übersetzung nötig |
| Protokoll-Typen | JSON-Schema aus Pydantic, TypeScript-Typen daraus mit `json-schema-to-typescript` | eine Wahrheit für Kern, Bibliothek und Oberfläche |
| Tests | pytest (Tabellen-Tests für Zuteiler, Speicherplaner, Regelgraphen), vitest, Playwright für die Oberfläche | Standard |

Nicht genommen: eine fertige Regel-Engine (die Bausteine sind fachlich, der Auswerter ist klein und
muss Begründungen liefern) und ein Zeitreihen-Server (SQLite mit Verdichtung reicht für die Messmengen).

## 13. Betrieb

- Version nur aus `version.json`; `tools/version.sh` zählt hoch, Git-Hooks erzwingen es.
- Betriebsort ist der Pi (Entscheidung 16.10.2026): `docker compose` mit Leitstelle und Datenordner auf der SSD;
  Entwicklung lokal auf dem Mac, Ausrollen per pull und compose.
- Agent: ein Installationsbefehl je Plattform, Dienst als launchd oder systemd, meldet sich selbst an.
- Sicherung: Datenordner als Archiv, Knopf in den Einstellungen.
- Spickzettel der Wartung in `docs/SPICKZETTEL.md` (ab Staffel 1).
