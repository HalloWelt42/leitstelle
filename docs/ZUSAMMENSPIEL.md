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

- **Bedarf**: was ein Dienst im Betrieb typischerweise braucht, nicht der höchste je gemessene Wert: der 95-%-Wert der
  Messungen der letzten 24 Stunden, mindestens die Schätzung der Dienstdatei. Einzelne Spitzen fallen heraus und
  verfallen; ein Dienst, der wirklich mehr braucht, hebt den Wert von selbst.
- **Plätze**: je Dienst in der Dienstdatei (`plaetze`, Vorgabe 1; Tondienst 4), gemeldet an die Leitstelle; die
  Leitstelle nutzt sie je Modell (auch `parallel` der Modell-Läufer) statt fest 1.
- **Eine Einheit**: GB (10^9 Byte) überall.
- **Start auf Befehl** setzt den Absturzzähler nicht zurück (sonst hebelt die Leitstelle "bleibt aus" aus).

### Stufe Z2: Leitstelle entscheidet sauber

- **Entladen nur bei Not**: wer weicht, bestimmt die Rangfolge (siehe unten); nie ein rechnendes, zugeteiltes oder
  geschütztes Modell (unter 10B, Einbettung); Mindestverweildauer bleibt.
- **Erst frei, dann laden**: nach dem Entladen auf die Freimeldung des Rechners warten, dann laden.
- **Vorrang** nach den Regeln des Nutzers (Rangfolge im Dialog geklärt, siehe Entscheidungen).
- **Messwerte als Rohdaten**: Lade-, Warte- und Rechenzeiten je Modell und Knoten bleiben als Reihe, damit sich die
  Regeln aus dem Verlauf einstellen lassen (Nutzer: "da wir loggen, können wir die logs ... zum verbessern nutzen").

### Stufe Z3: mehrere Instanzen kleiner Dienste

- Der Maschinenraum kann einen Dienst mehrfach starten (Instanzen mit eigenem Port); die Leitstelle entscheidet: wartet
  ein kleiner Dienst und ist Speicher frei, lohnt sich eine weitere Instanz (gemessen am Verlauf); kommt ein großer
  Auftrag, gehen die zusätzlichen Instanzen bis auf eine zurück oder ganz.

### Stufe Z4: externe Anbieter und weitere Rechner

- **Externe Anbieter** (zuerst Hetzner Experimental, OpenAI-kompatibel, etwa 10 Anfragen je Minute): Grenze je Dienst
  (Anfragen je Minute) hält die Leitstelle ein; Zone extern nur, wo die App es erlaubt.
- **Ausfälle**: ein Dienst, der nicht antwortet, wird in wachsenden Abständen geprüft (von wenigen Sekunden bis
  höchstens einmal am Tag) und als Ausfall markiert; ganz weg: einmal täglich oder von Hand ("jetzt prüfen").
- **Zweiter Mac**: ein zweiter Maschinenraum meldet sich als eigener Knoten; Umleiten und Doppel-Auflösen gibt es schon.
  Vorher prüfen: nichts im Code darf einen einzigen Mac annehmen (Namen, Budget, Tondienst je Rechner).

## Entscheidungen (Dialog 18.10.2026)

| Frage | Entscheidung |
|---|---|
| Einbettung | bleibt immer geladen und wird zuerst bedient |
| Lange Aufgaben | Begonnenes nicht wegnehmen: ein laufender langer Auftrag behält seine Modelle; kurze Anfragen anderer laden ihm nichts weg, sie warten oder weichen aus |
| Wer weicht bei Speichermangel | das größte ungenutzte Modell (kleine werden länger geduldet); nie unter 10B, nie ein rechnendes, nur so viel wie nötig |
| Mehrere Instanzen | bei Andrang, wenn Platz: wartet ein kleiner Dienst länger als eine gemessene Schwelle und ist genug frei, startet die Leitstelle eine weitere Instanz; ein großer Auftrag reduziert wieder |
