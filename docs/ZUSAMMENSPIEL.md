# Zusammenspiel: Leitstelle, Maschinenraum, Apps

Entwurf vom 18.10.2026. Auftrag des Nutzers: "die zentrale sollte ja entscheiden ob und wann modelle auch entladen
werden, z.b. wenn andere gerade mehr gebraucht werden", "das schwierige ist das orchestrieren untereinander wer was
korrekt macht", "maschinenraum ist am wichtigsten", "wir müssen auch immer den blick fürs gesamt werk haben. und das
künftige vorhaben also 2. mac und externe anbindungen". Grundlage: Bestandsaufnahme des Codes und die Protokolle der
Leitstelle (4158 Aufträge, 32 Maßnahmen vom 16. bis 18.10.2026).

## Zuständigkeiten (je Sache genau ein Ort)

Nutzer, 27.10.2026: "leitstelle war und sollte schon immer zentrale steuerung und überwachung sein. die sorgt dafür, dass
ressourcen nicht überlaufen, verteilt werden, das bedeutet nicht, dass sie auch jedes bit durchschleifen muss, aber sie
muss sinnvoll eingreifen." Den Modell-Läufer spricht die Leitstelle direkt an; der Maschinenraum meldet alle übrigen
KI-Modelle und Dienste, die nicht im Läufer laufen, als alternative Anbindung, und misst für die Leitstelle, was sie zum
Eingreifen braucht (Speicher, Zugriffe am Leitstand vorbei, Last).

| Wer | entscheidet | führt aus | meldet |
|---|---|---|---|
| Leitstelle | was wo läuft: Zuteilen, Laden, Entladen, wie viele Instanzen, Vorrang, Ausweichen auf andere Knoten oder externe Anbieter; Eingreifen bei Last (Hintergrund drosseln, Arbeiter ohne Auftrag beenden, Z6) | Anfragen durchreichen (Läufer direkt, Dienste über den Maschinenraum) | Lage, Verlauf, Maßnahmen mit Begründung |
| Maschinenraum (je Rechner einer) | nur Örtliches: Neustart nach Absturz, Schutz (`leitstelle_anhalten = false`) | Starten und Anhalten auf Befehl, Durchleitung zu seinen Diensten, Beenden eines Arbeiters des Läufers auf Befehl | je Dienst Zustand, tatsächlicher Speicher, Bedarf, Plätze; Rechnerspeicher; Zugriffe am Leitstand vorbei; Last von Läufer und Rechner |
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

### Stufe Z5: Einbettung verstärken (mehrere Instanzen im Modell-Läufer)

Auftrag des Nutzers (23.10.2026): "messen ob 2, 4, 8 parallele einbettungen was bringen. dafür muss die regelung
ungenutzte modelle entladen, dynamisch die einbettungen in mehreren instanzen bis kurz vor speichergrenze einsetzen,
mit etwas toleranz". Vorher lief `text-embedding-bge-m3` in einer Instanz; die Leitstelle gab ihr 4 Plätze (Plätze
des Dienstes), Fundus schickte 2 Stapel zu 64 Abschnitten gleichzeitig. Fundus-Rate vorher: 2,17 Abschnitte/s.

**Schnittstelle des Läufers** (gelesen und probiert, nicht geraten): `POST /api/v1/models/load` mit dem Schlüssel eines
schon geladenen Modells lädt eine weitere Instanz; ihre Kennung vergibt der Läufer (`text-embedding-bge-m3:2`, `:3`
...), eine eigene nimmt die Schnittstelle nicht an ("Unrecognized key(s) in object: 'identifier'"). Eine Anfrage
erreicht eine bestimmte Instanz, wenn `model` deren Kennung nennt; Entladen per `instance_id`. Einbettungsinstanzen
melden kein `parallel`. Laden einer Instanz: 47 bis 61 s (Rechner unter Last, 9,5 GB Auslagerung).

**Messung** (23.10.2026 am MacBook M4 Max 128 GB; Abschnitte wie die Quelle "Entwicklung" des Fundus: Code und Doku,
im Mittel 1700 Zeichen; je Instanz ein Strom; die Fundus-Einbettung lief auf der Grundinstanz weiter, in Lauf 2 dazu
eine Transkription; Speicher aus der Maschinenraum-Messung):

| Instanzen | Stapel | Lauf 1: Abschnitte/s | Lauf 2: Abschnitte/s | gegenüber einer | Anfrage im Mittel | Grafik |
|---|---|---|---|---|---|---|
| 1 | 64 | 3,10 | 2,58 | 1,0 | 21 bis 25 s | 24 % |
| 2 | 64 | 4,87 | 4,04 | 1,6 | 26 bis 32 s | 23 bis 27 % |
| 4 | 64 | 6,49 | 5,08 | 2,0 | 39 bis 49 s | 23 bis 36 % |
| 6 | 64 | 5,62 | - | (Ausreißer, Transkription) | 66 s | 24 % |
| 8 | 64 | 7,43 | 6,27 | 2,4 | 64 bis 80 s | 23 bis 25 % |

| Eine Instanz, Stapel je Anfrage | Abschnitte/s |
|---|---|
| 8 | 2,58 |
| 16 | 2,71 |
| 64 | 2,41 |
| 128 (eine Anfrage) | 1,29 |
| 4 Instanzen, 16 / 64 / 128 | 6,00 / 6,49 / 5,77 |
| 2 gleichzeitige Anfragen an eine Instanz (je 64) | 2,42 |

Befund: Eine Instanz rechnet ihre Anfragen nacheinander (zwei gleichzeitige bringen nichts); größere Stapel bringen
nichts, ab 128 wird es langsamer; mehr Instanzen bringen mehr, mit abnehmendem Gewinn (4: 2,0-fach, 8: 2,4-fach). Die
Grafik bleibt bei einem Viertel, die Grenze liegt im Läufer, nicht im Speicher. Speicher je weiterer Instanz: 1,0 GB
(8 Instanzen entladen gaben 7,9 GB frei), geplant mit der Größe der Gewichte 0,59 GiB; den Rest rechnet der
Maschinenraum danach dem System zu.

**Umsetzung** (Leitstelle 0.20.0):

- **Instanzen als eigene Modelle**: der Adapter des Läufers meldet jede geladene Instanz als eigenes Modell derselben
  Familie (Grundinstanz trägt den Schlüssel, weitere sind `zusatz`); Einbettungsmodelle haben je Instanz einen Platz.
  Die Leitstelle verteilt so Stapel über die Instanzen: jeder geht an eine freie Instanz, sonst wartet er bei ihr.
- **Eintrag des Dienstes** (Oberfläche: Dienste, bearbeiten): `Einbettung: Instanzen` (Höchstzahl je
  Einbettungsmodell, Vorgabe 1, am MacBook M4 Max 128 GB 2 nach der Messung im Betrieb, siehe unten) und `Einbettung: Spielraum` (GB, die im Budget des
  Rechners frei bleiben, Vorgabe 4: 8 Instanzen zu je 0,4 GB mehr als geplant plus Toleranz).
- **Regel "Einbettung verstärken"**: warten Einbettungsaufträge länger als `einbettung_andrang_s` (10 s) auf eine
  Instanz, lädt die Leitstelle in einer Maßnahme so viele weitere, wie Aufträge warten (abzüglich ladender), bis zur
  Höchstzahl und nur so viele, wie mit dem Spielraum ins Budget passen. Fehlt Platz, weichen ungenutzte Modelle,
  kleinste zuerst (nie ein Gesprächsmodell, das eine Anwendung für Text in ihrer Kette hat, nie ein Modell, das in der
  Schonfrist `einbettung_schonfrist_s` von 30 Minuten genutzt wurde, nie ein rechnendes, geschütztes oder von einer
  begonnenen Arbeit gehaltenes). Kein Abwägen Gewinn gegen Aufwand: der Strom der Einbettung ist stetig.
- **Regel "Einbettung zurückbauen"**: weitere Einbettungsinstanzen, die `einbettung_ruhe_s` (300 s) nichts zu tun
  hatten, während kein Einbettungsauftrag wartet, entlädt die Leitstelle in einer Maßnahme; die Grundinstanz bleibt.
  Bei Speichermangel weichen weitere Instanzen wie bisher vor allen anderen (sie sind nie geschützt, auch unter 10B).
- **Wirkung hängt an der App**: so viele Instanzen arbeiten, wie die App Stapel gleichzeitig schickt. Fundus schickt
  `gleichzeitig` Stapel (vorher 2), die Leitstelle begrenzt Fundus auf sein Kontingent (vorher 4); für 8 Instanzen
  müssen beide auf 8.

**Messung im Betrieb** (24.10.2026, 00:45 bis 01:15, Leitstelle 0.20.0 mit der Regel; eigene Last über die Fassade:
8 Ströme zu 64 Abschnitten, Fundus lief nebenher; je Stufe etwa 5 Minuten nach dem Anlauf; das 80B mit derselben
kurzen Probefrage direkt am Läufer, ohne eigene Last 4,4 Token/s und 2,5 s bis zum ersten Stück):

| Instanzen | Abschnitte/s | gegenüber einer | 80B Token/s | 80B erstes Stück | frei (GB, Maschinenraum) | Grafik | CPU | Watt |
|---|---|---|---|---|---|---|---|---|
| 1 | 4,58 | 1,0 | 4,2 | 2,8 s | 21,1 | 26 % | 23 % | 32 |
| 2 | 6,40 | 1,40 | 2,5 | 3,1 s | 18,9 | 27 % | 23 % | 32 |
| 4 | 7,20 | 1,57 | 1,35 | 5,9 s | 14,9 | 26 % | 24 % | 33 |
| 8 | 7,77 | 1,70 | 0,5 | 14 s | 9,5 | 26 % | 26 % | 33 |

Urteil: lohnt sich höchstens bis 2 Instanzen. Zwei Instanzen bringen 40 % mehr Einbettung, das Gesprächsmodell
verliert dabei schon rund 40 % Tempo; ab 4 kostet jede weitere Instanz das 80B mehr, als sie der Einbettung bringt
(8 Instanzen: 1,7-fach, das 80B fast stehend). Speicher ist nicht die Grenze (1 GB je Instanz); Grafik- und
Leistungsanzeige bleiben flach, die Instanzen teilen sich den Rechenweg des Läufers mit dem Gesprächsmodell. Vorgabe am
MacBook M4 Max 128 GB deshalb 2. Befunde nebenbei: der Läufer reißt gelegentlich Verbindungen ab (ReadError, auch vorher und bei
Fundus); die Leitstelle setzt ihn dann 5 s auf "nicht erreichbar" und lehnt solange alle Aufträge ab, mit mehr
Instanzen häufiger (offen). Fundus schickte live nur einen Stapel gleichzeitig; mit einem Stapel entsteht kein Andrang.

### Stufe Z6: Last des Modell-Läufers messen, Hängendes beenden, Hintergrund bei Rechnerlast drosseln

Anlass (27.10.2026): Die Last des Mac lag stundenlang bei rund 60, Tests liefen in Zeitgrenzen. Zwei Prozesse des
Modell-Läufers belegten viel Rechenzeit. Erst ein Abgleich von Hand mit `/api/auftraege` zeigte: es waren die beiden
Instanzen von Bge M3, die die Leitstelle selbst für die Masseneinbettung des Fundus betreibt (rund 640 Aufträge je
Stunde). Die Leitstelle zeigte das nirgends; die Beobachtung des Maschinenraums lässt die Läufer-Prozesse bewusst aus.
Nutzer: "genau deswegen muss Leitstelle sowas zentral steuern. das war seit Beginn der Entwicklung eine fundamentale
Forderung." Gewählt im Dialog: "Selbst eingreifen nach Regel" und "Massenarbeit bei Last drosseln"; beides setzt auf
einer gemeinsamen Messung auf.

Zuständigkeiten wie immer: der Maschinenraum misst und führt aus, die Leitstelle entscheidet.

#### Messung (Maschinenraum): `knoten.last`

Im Takt der Beobachtung (`beobachtung.takt_s`, 15 s), eigene Nachricht neben `knoten.fremde`:

- `kerne`: logische Kerne des Rechners
- `laeufer`: je Prozess des Läufers (lauschender Prozess am Läufer-Port samt Nachfahren)
  - `pid`, `name` (wie bei der Beobachtung), `rolle`: `haupt` (lauscht am Port), `arbeiter` (hat eine Modelldatei
    offen), `sonstig` (alles andere, etwa das Fenster)
  - `modelldatei`: Pfad der offenen Modelldatei unterhalb des Modellordners, leer bei Nicht-Arbeitern; erkannt an den
    Endungen aus `beobachtung.modelldateien` (Vorgabe `.gguf`, `.safetensors`), ein Aufruf von lsof für alle Läufer-Prozesse
  - `cpu_prozent`: Rechenzeit seit der letzten Messung je Wandzeit, in Prozent eines Kerns (aus `rechenzeit_s` der
    Prozesstabelle; beim ersten Mal und bei neuer pid leer)
  - `gb`: Speicher wie überall (`prozess_bytes`)
- `fremd_prozent`: Prozessorlast ohne Läufer und ohne Dienste des Maschinenraums, Anteil aller Kerne (0 bis 100), aus
  den Rechenzeiten aller Prozesse der Tabelle. Das ist die Last, die der Mensch und seine übrigen Programme erzeugen;
  die eigene Arbeit der Leitstelle steckt nicht darin, darum schaukelt sich das Drosseln nicht an der eigenen Last auf.
- `gemessen`: false ohne lsof oder ohne Läufer-Port; dann gibt es keine Aussage statt einer leeren Liste

Alles zeitbasiert (Rechenzeit je Wandzeit), nicht taktgewichtet wie `cpu_prozent` aus den Messwerten; beide Maße
werden nicht gemischt.

#### Befehl (Maschinenraum): `laeufer_prozess_beenden`

Neue `Befehlsart.LAEUFER_PROZESS_BEENDEN`, `ziel` = pid. Der Maschinenraum prüft beim Ausführen, dass die pid gerade
ein `arbeiter` des Läufers ist (im Baum des lauschenden Prozesses, Modelldatei offen); den Hauptprozess und alles
andere beendet er nie (Schutz gegen wiederverwendete pids und Fehlbedienung). SIGTERM, nach 10 s SIGKILL; das Ergebnis
nennt Name, Modelldatei und Weg. Der Läufer meldet die Instanz danach als entladen; die Leitstelle lädt bei Bedarf neu.

#### Anzeige (Leitstelle)

Beim Knoten und in der Übersicht: je Läufer die Prozesse mit Rolle, Modell (Datei), Kernen (cpu_prozent / 100, mit
Komma), Speicher und dem Stand der Leitstelle daneben: wie viele Aufträge gerade auf diesem Läufer laufen und wann
zuletzt einer lief. Ein Arbeiter, der über der Schwelle rechnet, während seit der Frist kein Auftrag der Leitstelle auf
diesem Läufer lief, heißt "arbeitet ohne Auftrag"; liegt zugleich eine Umgehung am Läufer vor (`knoten.fremde`,
Deutung aus `fach/umgehungen.py`), steht sie als Erklärung daneben. Dazu die Fremdlast des Rechners und die Stufe des
Hintergrunds je Knoten (frei, gedrosselt, angehalten) mit Grund. Neue Befunde in den Verlauf (wie bei den Umgehungen).
Von Hand: Knopf "Prozess beenden" je Arbeiter (Rückfall per Hand, gleiche Prüfung wie die Regel, mit Bestätigung in der
Leiste, nie Browser-Dialog).

#### Regel 1: "Läufer arbeitet ohne Auftrag" (Vorgabe aus)

Neue Massnahmenart `LAEUFER_OHNE_AUFTRAG`, in `szenarien_an` mit Vorgabe **aus**.

- Auslöser `laeufer_arbeitet_ohne_auftrag`: je Arbeiter eines Läufers ein Lauf, wenn er seit `laeufer_frist_s`
  (Vorgabe 300) in jeder Messung mindestens `laeufer_schwelle_prozent` (Vorgabe 50, Prozent eines Kerns) rechnet und
  in diesem Fenster kein Auftrag der Leitstelle auf einem Modell dieses Läufer-Dienstes lief oder zugeteilt war
  (`letzte_nutzung_s` der Modelle und offene Aufträge).
- Prüfung `umgehung_am_laeufer`: liegt eine echte Umgehung vor (nach der Deutung, nicht die Leitstelle selbst auf dem
  direkten Weg)? Ja: nur melden ("{prozess} rechnet ohne Auftrag der Leitstelle; am Läufer hängt {wer}"), nicht
  beenden, denn dann rechnet er für einen echten Kunden. Nein: weiter.
- Aktion `laeufer_prozess_beenden` (Befehl an den Maschinenraum), dann melden ("{prozess} mit {modelldatei} rechnete
  {dauer} ohne Auftrag mit {kerne} Kernen; beendet").
- Schleifenschutz wie alle Regeln (Fenster, Ruhezeit).

#### Regel 2: "Hintergrund bei Rechnerlast" (Vorgabe an)

Neue Massnahmenart `HINTERGRUND_RECHNERLAST`, Vorgabe an. Stufe je Knoten `hintergrund_stufe`: `frei`, `gedrosselt`,
`angehalten`, mit Grund und Zeitpunkt.

- Auslöser `rechnerlast`: je wachem Knoten mit `knoten.last` ein Lauf je Takt mit dem gleitenden Mittel der Fremdlast
  über `last_frist_s` (Vorgabe 60).
- Prüfungen über die Regelwerte `last_drosseln_ab_prozent` (Vorgabe 50), `last_anhalten_ab_prozent` (Vorgabe 75) und
  `last_abstand_prozent` (Vorgabe 10, Rückweg erst darunter, gegen Flattern).
- Aktionen `hintergrund_drosseln`, `hintergrund_auf_knoten_anhalten`, `hintergrund_auf_knoten_freigeben` setzen die
  Stufe; melden mit Fremdlast und Grenze.
- Wirkung im Zuteiler und in den Prüfungen:
  - `gedrosselt`: Hintergrundaufträge (Priorität HINTERGRUND, wirksame Priorität) bekommen auf diesem Knoten nur die
    Grundinstanz einer Familie, keine weitere; `weitere_instanz_moeglich` und `einbettungsinstanzen_moeglich` sagen nein,
    solange nur Hintergrund wartet; weitere Instanzen ohne Auftrag werden sofort entladen (nicht erst nach der Ruhe).
  - `angehalten`: Hintergrundaufträge werden auf diesem Knoten nicht zugeteilt; laufende laufen zu Ende. Die Fairness
    (`hintergrund_spaetestens_s`) gilt hier nicht: angehalten heißt, der Rechner gehört gerade dem Menschen.
  - Normale, hohe und dringende Aufträge bleiben unberührt.
- Die Grenzen sind Schätzwerte; nach einer Woche mit dem Verlauf (Fremdlast, Stufenwechsel, Durchsatz der Einbettung)
  nachstellen.

#### Prüfung

- Maschinenraum: Messung mit nachgestellter Prozesstabelle und lsof (Rollen, Modelldatei, Prozent aus zwei Messungen,
  Fremdlast ohne Läufer und Dienste); Befehl beendet nur Arbeiter, lehnt Hauptprozess, fremde pid und verschwundene pid
  ab.
- Leitstelle: Regel 1 löst nur nach voller Frist ohne Auftrag aus, nicht bei Umgehung, nicht wenn ein Auftrag lief;
  Regel 2 drosselt, hält an, gibt erst unter Grenze minus Abstand frei, lässt Normales unberührt, entlädt weitere
  Instanzen ohne Auftrag; Spiegeltest des Protokolls; Szenarien in `docs/SZENARIEN.md`.

**Umsetzung** (Leitstelle 0.23.0, Maschinenraum 0.15.0, 27.10.2026):

- **Maschinenraum**: `knoten.last` und `knoten.fremde` entstehen aus einer Aufnahme je Takt (ein Aufruf von ps, einer
  von lsof am Läufer-Port, dazu einer für die Modelldateien aller Läufer-Prozesse). Die Modelldatei kommt als Pfad (Heim
  als `~`), die Oberfläche zeigt den Dateinamen. Ohne eingetragenen Läufer gibt es keinen, der herauszurechnen wäre: dann
  ist `gemessen` falsch, die Fremdlast aber gemessen; ohne lsof fehlen beide. Die Wartezeit zwischen SIGTERM und SIGKILL
  ist die Einstellung `beobachtung.anhaltezeit_s` (Vorgabe 10 s), nicht fest. Gemessen wird erst, wenn der Start alle
  laufenden Dienste übernommen hat (sonst hielte die Beobachtung eigene Dienste für fremd); weitere Instanzen findet der
  Start über Stand und Port wieder.
- **Kern**: `Knoten.last` (je Prozess die Reihe über der Schwelle, Fremdlast im Fenster), `laeufer_umgehungen` (aus dem
  Umgehungsbuch, nur Verbindungen zum Läufer) und die Stufe des Hintergrunds. Eine Stelle für Befund, Arbeit der
  Leitstelle auf dem Läufer und Sätze: `kern/rechnerlast.py`. Läufer eines Rechners sind seine Dienste der Art
  `openai_kompatibel`; ein Laden der Leitstelle dort zählt wie ein Auftrag.
- **Regel 1**: der Weg mit Umgehung endet ohne Aktion ("rechnet für ein Programm am Leitstand vorbei, nicht beendet");
  gemeldet ist der Fall schon als Befund im Verlauf (einmal je Arbeiter, mit "am Läufer hängt ..."), so verbraucht er
  nicht in jedem Takt eine Maßnahme des Fensters. Die Meldung der Maßnahme endet mit "wird beendet"; das Ergebnis des
  Maschinenraums (Weg oder Ablehnung) steht danach im Verlauf. Schleifenschutz: Beenden zählt als Bewegung
  `beenden:<Pfad der Modelldatei>@<knoten>`; ein zweites Beenden desselben Modells im Fenster ist Flattern. Beenden von Hand
  (Knopf "Prozess beenden", `POST /api/knoten/<k>/laeufer/<pid>/beenden`) nur für einen Arbeiter mit Befund, dieselbe
  Prüfung wie die Regel.
- **Regel 2**: ohne frische Messung (Maschinenraum getrennt) gibt die Regel einen gebremsten Hintergrund frei. Das
  sofortige Entladen weiterer Instanzen ohne Auftrag betrifft die Einbettungsinstanzen des Läufers (Regel "Einbettung
  zurückbauen" ohne Ruhezeit, wartender Hintergrund zählt nicht); für weitere Instanzen von Diensten des Maschinenraums
  gibt es keine Rückbau-Regel, sie bekommen gedrosselt nur keinen Hintergrund. Gesperrt für Hintergrund sind auch
  Umleiten, Ausweichen in der Kette und Vorwärmen auf einen gebremsten Rechner.
- **Regelwerte** (Regelwerk, im Lagebild): `laeufer_schwelle_prozent`, `laeufer_frist_s`, `last_frist_s`,
  `last_drosseln_ab_prozent`, `last_anhalten_ab_prozent`, `last_abstand_prozent`; ein gespeichertes Regelwerk ohne die
  neuen Szenarien bekommt ihre Vorgaben ab Werk (keine Migration nötig). Eine Seite Regeln gibt es in der App noch nicht;
  Werte und Erklärungen stehen dort, wo sie wirken: unter Knoten bei "Läufer und Last".
- **Prüfung**: Szenarien L01 bis L23 ([SZENARIEN.md](SZENARIEN.md) Abschnitt 3d), Spiegeltest des Protokolls; im
  Maschinenraum `tests/test_laeuferlast.py` und die Instanztests in `tests/test_dienste.py`.

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

## Entscheidung: Warten, bis der Mac wach ist (19.10.2026)

Vorher scheiterten Aufträge sofort, wenn der Mac schlief: nach wenigen Sekunden galt er als nicht erreichbar, und der
Zuteiler lehnte mit 403 `zone_nicht_erlaubt` ab, worauf die Apps nicht warteten. Dienste im OpenAI-Format auf demselben
Rechner zählten die ganze Nacht Fehlschläge und standen morgens im Ausfall mit Prüfabständen bis zu einem Tag; laufende
Aufträge hingen, außer bei Automatik "selbst".

| Frage | Entscheidung |
|---|---|
| Was tun, wenn der Mac schläft | warten, bis er wach ist (Nutzer: "Warten, bis er wach ist") |
| Wer erkennt den Schlaf | der Maschinenraum selbst (IOKit, auch ohne Menüleiste); er meldet `knoten.schlaeft` vor dem Einschlafen und meldet sich beim Aufwachen neu an |
| Wer wartet | die App (Appkern `geduldig`, ohne Grenze, mit Abbrechen); die Leitstelle hält keine Anfrage fest, sie antwortet 503 `rechner_schlaeft` mit Retry-After 60 s und den Rechnern in `error.x-leitstelle.rechner` |
| Laufende Aufträge beim Einschlafen | enden mit `rechner_schlaeft`, auch ohne Automatik; zugeteilte und wartende entscheidet der Zuteiler neu |
| Dienste auf dem schlafenden Rechner | Zustand `schlaeft`: keine Prüfung, keine Fehlschläge; beim Aufwachen Prüfstand zurück und sofort prüfen |
| Lage | bleibt ruhig, "MacBook M4 Max 128 GB schläft" als Hinweis; nirgends als Gefahr gezeigt |
| Neustart der Leitstelle im Schlaf | der Schlaf bleibt vermerkt (Einstellungsablage, Schlüssel `schlaf`); unbekannte Namen auf einem schlafenden Rechner heißen `rechner_schlaeft` |
| Von Hand | "Nicht mehr warten" auf der Knotenseite beendet den Schlafzustand; Prüfprotokoll |
| Zonenfehler | 403 nur, wenn die Zone wirklich nicht passt; unangekündigt verschwundene Rechner geben 503 `dienst_nicht_erreichbar` |
| Leerlaufschlaf während eines Auftrags | aufschieben, solange der Maschinenraum eine Anfrage durchreicht (Einstellung `schlaf.leerlauf_aufschieben`, Vorgabe an); Deckel, Menü und Ein-Taste wirken immer |
| Geduld der Apps bei anderen Ausfällen | Einstellung "Geduld bei Ausfall" je App (Vorgabe 30 Minuten); der Schlaf zählt nicht dazu |
