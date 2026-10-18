# Zusammenspiel: Leitstelle, Maschinenraum, Apps

Entwurf vom 18.10.2026. Auftrag des Nutzers: "die zentrale sollte ja entscheiden ob und wann modelle auch entladen
werden, z.b. wenn andere gerade mehr gebraucht werden", "das schwierige ist das orchestrieren untereinander wer was
korrekt macht", "maschinenraum ist am wichtigsten", "wir müssen auch immer den blick fürs gesamt werk haben. und das
künftige vorhaben also 2. mac und externe anbindungen". Grundlage: Bestandsaufnahme des Codes und die Protokolle der
Leitstelle (4158 Aufträge, 32 Maßnahmen vom 16. bis 18.10.2026).

## Zuständigkeiten (je Sache genau ein Ort)

| Wer | entscheidet | führt aus | meldet |
|---|---|---|---|
| Leitstelle | was wo läuft: Zuteilen, Laden, Entladen, wie viele Instanzen, Vorrang, Ausweichen auf andere Knoten oder externe Anbieter | Anfragen durchreichen | Lage, Verlauf, Maßnahmen mit Begründung |
| Maschinenraum (je Rechner einer) | nur Örtliches: Neustart nach Absturz, Schutz (`leitstelle_anhalten = false`) | Starten und Anhalten auf Befehl, Durchleitung | je Dienst Zustand, tatsächlicher Speicher, Bedarf, Plätze; Rechnerspeicher |
| Apps | was sie brauchen und wie dringend (Fähigkeit, Priorität, Titel) | geduldig warten, wenn die Leitstelle "gleich" sagt | nichts |

Der Pi rechnet nicht (Nutzer 18.10.2026: "pi ist nur datenlieferant"); Rechenknoten sind Macs und externe Anbieter.

## Befund aus den Protokollen

1. Um 16:10 entlud die Leitstelle das 80B (44,9 GB), damit der Tondienst (1 GB) starten konnte; das nächste Übersetzen
   wartete auf das Neuladen (Wartezeiten des 80B bis 100 s). Ursache: Sie plante mit 85 GB belegt und 10,9 GB frei,
   tatsächlich frei waren über 50 % (Druckanzeige des Mac). Der Maschinenraum meldet als Bedarf den höchsten je
   gemessenen Wert, und der sinkt nie: Stimmklon 13,7 GB (tatsächlich 4,7), Trennung 9,8 (4,7), Sprechen 7,9 (3,3).
   Ein einziger Ausreißer (ein durchgegangener Klon) bläht die Planung dauerhaft auf.
2. Hören wartete bis 75 s: ein Platz; die Ausspracheprüfung der Vertonung (Priorität normal) stand hinter langen
   Hörabschnitten der KI-Transkripte (Hintergrund, je 45 bis 100 s). Eine zweite Instanz des kleinen Hördienstes (6 GB)
   hätte genügt.
3. Mac-Dienste haben fest einen Platz (die Leitstelle setzt ihn, der Maschinenraum meldet keinen); der Tondienst könnte
   viele Aufträge nebeneinander rechnen.
4. Messwerte in zwei Einheiten (Maschinenraum GiB, Modell-Läufer GB): etwa 7 % Abweichung in Budget und Systemrechnung.

## Entwurf

### Stufe Z1: Maschinenraum meldet richtig (zuerst)

Stand: umgesetzt und ausgerollt am 18.10.2026 (Leitstelle 0.12.0, Maschinenraum 0.9.0, Dienstkern 0.2.1).

- **Bedarf**: was ein Dienst im Betrieb typischerweise braucht, nicht der höchste je gemessene Wert: der 80-%-Rangwert
  der letzten 30 Arbeitsspitzen (je Arbeitsphase der höchste Wert), mindestens die Schätzung der Dienstdatei und
  mindestens der Wert gerade. Einzelne Spitzen fallen heraus und verfallen; ein Dienst, der wirklich mehr braucht, hebt
  den Wert von selbst. Ergebnis: frei 28,6 statt 10,9 GiB; Stimmklon 6,0, Trennen 4,7, Sprechen 3,3.
- **Plätze**: je Dienst in der Dienstdatei (`plaetze`, Vorgabe 1; Tondienst 4), gemeldet an die Leitstelle; die
  Leitstelle nutzt sie je Modell (auch `parallel` der Modell-Läufer) statt fest 1. Die Modellseite zeigt sie, sobald
  mehr als ein Platz da ist.
- **Eine Einheit**: GiB (2^30 Byte) überall, wie die Speicheranzeige von macOS und der Maschinenraum.
- **Start auf Befehl** setzt den Absturzzähler nicht zurück (sonst hebelt die Leitstelle "bleibt aus" aus).

### Stufe Z2: Leitstelle entscheidet sauber

Stand 18.10.2026 (Leitstelle 0.13.0, Appkern 0.31.0): Arbeit, Einbettung zuerst, erst frei dann laden und Bewegungen
umgesetzt; Vorrang und Wahl beim Entladen waren schon so (größtes ungenutztes zuerst, nur so viel wie nötig).

- **Begonnenes nicht wegnehmen**: jede Anfrage aus einem Auftrag einer App trägt dessen Kennung (Kopf
  `X-Leitstelle-Arbeit`, setzt der Appkern). Ab der zweiten Anfrage gilt die Arbeit als begonnen; Modelle, die sie in
  den letzten `arbeit_frist_s` (300 s) genutzt hat, weichen nicht für andere, nur für sie selbst. Die Modellseite zeigt
  "bleibt für ...", der Speicherplan nennt die Arbeit als Grund. Der Verlauf trägt die Arbeit je Auftrag, damit sich
  Frist und Schwelle aus echten Abläufen einstellen lassen.
- **Einbettung zuerst**: in der Warteschlange vor jedem Text, auch einem dringenden; geladen bleibt sie (geschützt).
- **Entladen nur bei Not**: wer weicht, bestimmt die Rangfolge (siehe unten); nie ein rechnendes, zugeteiltes oder
  geschütztes Modell (unter 10B, Einbettung); Mindestverweildauer bleibt.
- **Erst frei, dann laden**: ein Laden wartet, bis jedes laufende Entladen auf demselben Rechner zurück ist (vorher
  liefen beide nebeneinander, und der Dienst konnte das Laden mangels Speicher ablehnen).
- **Vorrang** nach den Regeln des Nutzers (Rangfolge im Dialog geklärt, siehe Entscheidungen).
- **Messwerte als Rohdaten**: Lade-, Warte- und Rechenzeiten je Modell und Knoten bleiben als Reihe, damit sich die
  Regeln aus dem Verlauf einstellen lassen (Nutzer: "da wir loggen, können wir die logs ... zum verbessern nutzen").
  Warte- und Rechenzeiten stehen in den Aufträgen (`/api/auftraege`), jedes Laden und Entladen mit Beginn, Dauer und
  Ausgang in `/api/bewegungen`.

### Stufe Z3: mehrere Instanzen kleiner Dienste

Stand 18.10.2026: umgesetzt (Maschinenraum 0.11.0, Leitstelle 0.16.0, Appkern 0.33.0 mit Bindung); das Hören darf zwei
Instanzen haben (Wartezeiten bis 75 s im Verlauf), alle Klangwerk-Dienste nehmen ihren Port aus `$MASCHINENRAUM_PORT`.

- Der Maschinenraum kann einen Dienst mehrfach starten (Instanzen mit eigenem Port); die Leitstelle entscheidet: wartet
  ein kleiner Dienst und ist Speicher frei, lohnt sich eine weitere Instanz (gemessen am Verlauf); kommt ein großer
  Auftrag, gehen die zusätzlichen Instanzen bis auf eine zurück oder ganz.

Entwurf (18.10.2026):

- **Dienstdatei**: `instanzen` (Vorgabe 1) sagt, wie viele Prozesse die Leitstelle höchstens starten darf. Jede
  Instanz bekommt ihren Port in der Umgebung `MASCHINENRAUM_PORT` (Grundinstanz `port`, Instanz n `port + 100 (n-1)`),
  der Befehl nimmt ihn als `$MASCHINENRAUM_PORT`. Weitere Instanzen heißen `<kennung>.<n>`, leben nur im Speicher des
  Maschinenraums (nach seinem Neustart startet die Leitstelle sie bei Bedarf neu) und folgen Änderungen der Datei.
- **Bericht**: je Instanz `instanz_von` (Grundinstanz) und `instanzen` (Höchstzahl). Für die Leitstelle sind alle
  Instanzen eine Modellfamilie; die Durchleitung geht an die Instanz, die den Auftrag hat.
- **Wann mehr**: wartet ein Auftrag länger als die Schwelle der Regel (Vorgabe 20 s) darauf, dass eine Instanz frei wird, ist die
  Höchstzahl nicht erreicht, passt eine weitere Instanz ohne Entladen und spart sie mehr Wartezeit als ihr Start
  kostet, startet die Leitstelle die nächste (Regel "Weitere Instanz", Maßnahme mit Begründung).
- **Wann weniger**: zusätzliche Instanzen weichen bei Speichermangel vor allen anderen Modellen (nur bei Not, wie
  jedes Entladen); die Grundinstanz bleibt nach den üblichen Regeln.
- **Bindung** (Befund der Prüfung auf einen zweiten Mac, 18.10.2026): Tondienst, Sprechen und Stimmklon arbeiten in
  zwei Schritten (rechnen, Ergebnis abholen); bei mehreren Instanzen derselben Familie konnte das Abholen bei einer
  anderen landen. Die Antwort nennt deshalb die Instanz (`X-Leitstelle-Instanz`), der Folgeaufruf schickt sie mit
  (Appkern `dienst.gebunden()`). Erst danach bekommen solche Dienste `instanzen > 1`; einstufige (Hören,
  Sprechertrennung, Sprechermerkmal) gehen sofort.

### Stufe Z4: externe Anbieter und weitere Rechner

- **Externe Anbieter** (zuerst Hetzner Experimental, OpenAI-kompatibel, etwa 10 Anfragen je Minute): Grenze je Dienst
  (Anfragen je Minute) hält die Leitstelle ein; Zone extern nur, wo die App es erlaubt.
- **Ausfälle**: ein Dienst, der nicht antwortet, wird in wachsenden Abständen geprüft (von wenigen Sekunden bis
  höchstens einmal am Tag) und als Ausfall markiert; ganz weg: einmal täglich oder von Hand ("jetzt prüfen").

Entwurf (18.10.2026, Messung an Hetzner: `/v1/models` nennt je Modell `id`, `max_model_len` und `root`; mehrere `id`
mit gleichem `root` sind dasselbe Modell; keine Grenzwerte in den Antwortköpfen):

- **Jede Anfrage zählt**: der Adapter zählt jede Anfrage, die er an den Dienst schickt (Arbeit, Wiederholungen,
  Zustandsabfragen) über einen Haken seines HTTP-Clients; der Kern führt je Dienst das gleitende Fenster der letzten
  60 s. Ist die Grenze erreicht, gilt der Dienst wie ein belegter Platz: der Auftrag wartet mit Frist (bis die älteste
  Anfrage aus dem Fenster fällt) oder weicht aus. Antwortet der Dienst trotzdem mit 429, sperrt die Leitstelle ihn für
  `Retry-After` (sonst 60 s).
- **Überlast beim Anbieter ist kein Fehlschlag**: externe Anbieter melden ein ausgelastetes Modell über ihren
  Vorschaltrechner mit 502, 503 oder 504. Die Leitstelle behandelt das wie 429: Sperre, der Auftrag geht zurück in die
  Warteschlange (höchstens 3 Neuversuche) und wartet oder weicht auf ein erlaubtes Modell aus; der Zustand des Dienstes
  bleibt bereit. Welche Antwortcodes Überlast bedeuten, weiß der Adapter (`ueberlast_status`).
- **Immer als Strom**: zum Anbieter geht jede Anfrage als Strom, auch wenn die App keinen will; dann setzt der Adapter
  die Antwort zusammen. Ohne Strom bricht der Vorschaltrechner lange Antworten ab.
- **Seltener Abgleich**: externe Dienste werden im gesunden Zustand nur alle `abgleich_s` (Vorgabe 900 s) nach ihren
  Modellen gefragt, nur über `/v1/models`; Namen mit gleichem `root` werden zu einem Modell mit Aliassen.
- **Prüfabstände bei Ausfall** (alle abgefragten Dienste; Dienste des Maschinenraums melden sich selbst und sind
  ausgenommen): nach jedem Fehlschlag verdoppelt sich der Abstand, von `pruefung_ab_s` (5 s) bis höchstens
  `pruefung_hoechstens_s` (1 Tag); ab dem fünften Fehlschlag in Folge heißt der Zustand **Ausfall** statt "nicht
  erreichbar". "Jetzt prüfen" in der Oberfläche prüft sofort und setzt den Abstand zurück, wenn der Dienst antwortet.
- **Daten verlassen das Heimnetz nur mit Erlaubnis, und die App entscheidet**: die Leitstelle erlaubt der App die
  Zone extern (äußere Grenze); die App führt in ihren eigenen Einstellungen eine Erlaubnisliste externer Modelle und
  schickt sie mit jeder Anfrage (`X-Leitstelle-Extern`). Nur was auf der Liste steht oder ausdrücklich verlangt ist,
  darf nach extern; die Leitstelle weicht dorthin aus, wenn lokal länger als `extern_schwelle_s` (120 s) gewartet
  würde, und entlastet so die lokale KI.

Stand 18.10.2026: umgesetzt in Leitstelle 0.14.0 (Grenze, Abgleich, Ausfall, 429) und 0.15.0 (Erlaubnisliste,
Steckbrief); Hetzner Experimental eingetragen (10 Anfragen je Minute, Abgleich alle 15 Minuten).

Grenzen von Hetzner Experimental (Doku des Anbieters, Stand 24.07.2026; je Schlüssel, gleitend 60 s): 10 Anfragen,
4 Mio. Eingabe-Token, 100.000 Ausgabe-Token; darüber 429. Eine Zeitgrenze nennt die Doku nicht. Gemessen 19.10.2026:

| Befund | Messung |
|---|---|
| Anfrage ohne Strom mit langem Denken | 504 nach 300 s (vor 0.17.1) |
| Anfrage als Strom, Modell fängt an | Kopf nach 1 bis 2 s, danach beliebig lang (624 s und 20 min), Lücken höchstens 4,7 s |
| Anfrage als Strom, Modell ausgelastet | kein Kopf, nach 300 s 504 vom Vorschaltrechner (2 von 3 Anfragen an Qwen 3.8 am Abend des 18.10.) |

Umgesetzt in 0.17.2: 502, 503 und 504 externer Anbieter gelten als Überlast. Die Token-Grenzen je Minute sind nicht
eingebaut; eine einzelne Anfrage bleibt weit darunter. Messungen zum Modellvergleich laufen mit den lokalen Modellen
(Entscheidung 19.10.2026: dasselbe Modell ist lokal da), Hetzner bleibt Entlastung im Betrieb.

## Selbstauskunft: Steckbrief je Modell

Nutzer 18.10.2026: "die modelle [können] auskunft über sich selber geben ... so kann eine anfrage einer software eine
antwort bekommen, für welchen zweck ein dienst oder ki optimiert ist". Jedes Modell im Verbund hat einen Steckbrief;
die Leitstelle setzt ihn aus drei Quellen zusammen und nennt je Angabe, woher sie stammt:

| Quelle | Angaben |
|---|---|
| der Dienst selbst | Modell-Läufer: Kontext, Parameter, Quantisierung, Bilder verstehen, Werkzeuge; Hetzner: Kontext; Dienste des Maschinenraums: was in ihrer Dienstdatei steht (Zweck, Sprachen, Eignung) |
| gemessen von der Leitstelle | Wörter je Sekunde, Zeit bis zum ersten Stück, Ladezeit, wie oft erreichbar |
| eingetragen von Hand | Zweck und Eignung, wo der Dienst nichts sagt (etwa bei externen Anbietern) |

Eine App fragt über `GET /v1/steckbriefe` (Fassade, mit `faehigkeit` und `eignung` als Filter) oder `frage.modelle`
(Protokoll); `/v1/models` trägt den Steckbrief zusätzlich je Eintrag unter `leitstelle`. Festgelegt in
docs/PROTOKOLL.md Abschnitt 4.8.
- **Zweiter Mac**: ein zweiter Maschinenraum meldet sich als eigener Knoten; Umleiten und Doppel-Auflösen gibt es schon.
  Vorher prüfen: nichts im Code darf einen einzigen Mac annehmen (Namen, Budget, Tondienst je Rechner).
  Geprüft am 18.10.2026 (Suche über Leitstelle, Maschinenraum, Appkern und Apps): Adressen, Budget, Messwerte, Agenten
  und Oberfläche gehen je Rechner. Behoben: zweistufige Aufrufe (Bindung an die Instanz), Vorzug für Hintergrund
  flatterte bei überschneidenden Fenstern, Wartende hielten die Kopie auf dem anderen Rechner, ein Rechner nur mit
  Maschinenraum ließ sich in der Oberfläche nicht anlegen, Angebot nannte den Rechner mit Kennung. Offen und bewusst so:
  ein Name meint eine Familie (kein Wunschrechner), eine gemeinsame Reserve für alle Rechner (Ausweg: festes Budget je
  Rechner), Messwerte der Steckbriefe je Familie über beide Rechner. Für den zweiten Mac: Maschinenraum installieren,
  in der Leitstelle "Rechner hinzufügen", auf seiner Karte einen eigenen Schlüssel ausstellen.

## Entscheidungen (Dialog 18.10.2026)

| Frage | Entscheidung |
|---|---|
| Einbettung | bleibt immer geladen und wird zuerst bedient |
| Lange Aufgaben | Begonnenes nicht wegnehmen: ein laufender langer Auftrag behält seine Modelle; kurze Anfragen anderer laden ihm nichts weg, sie warten oder weichen aus |
| Wer weicht bei Speichermangel | das größte ungenutzte Modell (kleine werden länger geduldet); nie unter 10B, nie ein rechnendes, nur so viel wie nötig |
| Mehrere Instanzen | bei Andrang, wenn Platz: wartet ein kleiner Dienst länger als eine gemessene Schwelle und ist genug frei, startet die Leitstelle eine weitere Instanz; ein großer Auftrag reduziert wieder |
| Frist begonnener Arbeiten | bleibt: 300 s nach der letzten Nutzung, ab der zweiten Anfrage; Wert nach dem Verlauf prüfen |
| Externe Anbieter | die Apps entscheiden selbst per Einstellung (Erlaubnisliste), nur wo die Qualität nicht leidet; freiwillig, entlastet die lokale KI; Vertonung, TubeVault, Transkription; txt2voice nicht (wird abgelöst) |
