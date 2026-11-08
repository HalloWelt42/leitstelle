# Arbeitslogik: was jede App über die Leitstelle wissen muss

Die eine Wahrheit für alle Apps, die KI über die Leitstelle nutzen (Entscheidung LS-23, Punkt 8). Was hier steht, gilt für
jede App; umgesetzt wird es auf der App-Seite einmal im Appkern, jede App nutzt nur ihn. Wie die Nachrichten aussehen,
steht im Protokoll ([PROTOKOLL.md](PROTOKOLL.md)), wie eine App angebunden wird in [ANBINDUNG.md](ANBINDUNG.md), warum es
so entschieden ist in [ZUSAMMENSPIEL.md](ZUSAMMENSPIEL.md) (Abschnitte "Entscheidung: ...").

## 1. Grundsätze

1. **Die App wählt das Modell, die Leitstelle nur Rechner und Zeitpunkt.** Ohne Modell lehnt die Leitstelle ab
   (`modell_fehlt`); ausgewichen wird nur auf Modelle, die die App selbst in `alternativen` nennt.
2. **Auslastung zählt je Rechner.** Was auf einem Mac läuft, bremst oder unterbricht nie Arbeit auf einem anderen
   (Nutzer 07.11.2026). Ruhe, Enge, Vorrang, Akku und Rolle werden je Rechner beurteilt.
3. **Laufendes rechnet zu Ende.** Keine Regel bricht einen laufenden Auftrag ab, um anderen Platz zu machen; sie
   lassen nur nichts Neues mehr starten. Abbrechen ist allein Sache des Menschen (Hauptregler Halt, Stoppen).
4. **Jede App kann sehen, was los ist**, vorher und während des Wartens (Abschnitt 5), und entscheidet selbst, ob sie
   aufschiebt.
5. **Werte stehen im Regelwerk der Leitstelle** (Oberfläche, Regeln), nicht im Code einer App.

## 2. Was die App je Auftrag mitschickt

| Angabe | Wo | Bedeutung |
|---|---|---|
| Modell | `model`, dazu `alternativen` | Pflicht; Kennung, Alias oder Name. Die Reihenfolge der App gilt streng |
| Art | Kopf `X-Leitstelle-Art: einzel` oder `masse` | Einzelauftrag (Vorgabe) oder Teil einer Massenaufgabe (Abschnitt 3) |
| Wichtig | Kopf `X-Leitstelle-Wichtig: ja` | nur, wenn der Nutzer den Auftrag ausdrücklich als wichtig markiert hat (Abschnitt 4) |
| Priorität | Kopf `X-Leitstelle-Prioritaet` | darf die Vorgabe der App absenken, nie heben |
| Titel | Kopf `X-Leitstelle-Titel` | lesbarer Titel für die Oberfläche der Leitstelle; erscheint nie in der Auskunft an andere Apps |
| Arbeit | Kopf `X-Leitstelle-Arbeit` | zusammengehörige Anfragen einer Arbeit (hält ihre Modelle) |
| Extern, Instanz | Köpfe `X-Leitstelle-Extern`, `X-Leitstelle-Instanz` | externe Modelle erlauben; Folgeaufruf an dieselbe Instanz |

## 3. Reihenfolge

1. **Wichtig** vor allem anderen, auch vor Sprachausgabe; unter wichtigen Aufträgen zählt der Eingang.
2. **Einzel vor Masse**, über alle Fähigkeiten: eine einzelne Suche (Einbettung) kommt vor dem Vorlesen eines ganzen
   Buchs (Masse).
3. Innerhalb von Einzel und innerhalb von Masse die **Rangfolge nach Fähigkeit** (Regelwerk "Rangfolge"; Vorgabe 1
   Sprachausgabe; 2 Hören, Sprecher trennen und erkennen; 3 Text, Übersetzen, Einordnen, Werkzeuge, Tonbearbeitung; 4 Bild
   beschreiben; 5 Bilder erzeugen und bearbeiten, Stimmklon; 6 Musik; 7 Einbettung).
4. Innerhalb eines Rangs die **Priorität der App**, dann der Eingang.

**Masse** rechnet nur auf einem Mac, auf dem gerade keine Einzelarbeit läuft oder wartet und die letzte seit "Ruhe ab"
(Vorgabe 60 s) vorbei ist; sonst wartet sie (`wartet_ruhe`) oder geht auf einen anderen, ruhigen Mac. Apps, die Masse
noch nicht melden, behandelt die Leitstelle über die Regel "Fähigkeiten nur bei Ruhe" (Einbettung mit Priorität
Hintergrund); sie fällt, sobald alle Apps ihre Masse selbst melden.

## 4. Wichtig (Vorrang auf Wunsch des Nutzers)

- Der Nutzer markiert in der App einen einzelnen Auftrag als wichtig (Knopf "Wichtig" am Auftrag). Je App ist
  einstellbar, ob danach jedes Mal eine Bestätigung in der Leiste kommt (mit erwarteter Wartezeit und wer verdrängt
  wird). Eine App setzt den Kopf nie von sich aus.
- Wartet ein wichtiger Auftrag auf einen Rechner, startet dort nichts anderes mehr; was läuft, rechnet zu Ende, dann
  ist er dran. Andere Rechner sind davon nicht berührt.
- Zwei wichtige für denselben Rechner: wer zuerst kam. Der zweite sieht als Grund, für wen der Rechner freigehalten ist.
- Der Vorrang endet mit dem Auftrag. Akku-Sperre und Prüffenster gelten auch für wichtige Aufträge.

## 5. Auskunft für die App

| Wann | Weg | Was die App bekommt |
|---|---|---|
| vor dem Senden | `POST /v1/einschaetzung` (Modell, Art, Wichtig) | `sofort`, `wartezeit_s`, `rechner`, `grund`, `vor_dir`, offene wichtige Aufträge, `abgelehnt`; nichts wird eingereiht |
| nach dem Einreihen | Köpfe der Antwort `X-Leitstelle-Wartet-S`, `X-Leitstelle-Auftrag`; bei Streams Kommentarzeilen | geschätzte Wartezeit, Kennung |
| laufend | `GET /v1/lage`, `GET /v1/lage/strom` | je eigenem Auftrag Zustand, Rang, Art, Wichtig, Rechner, `rest_s` und `grund`; Rechner mit Akku, Rolle, Vorrang; Prüffenster |

Inhalte (Titel, Texte, Eingaben) stehen nie in einer Auskunft.

**Was die App damit tut:** den Wartegrund dem Nutzer zeigen (statt still zu warten oder still aufzugeben), bei langer
Wartezeit Massenarbeit aufschieben, interaktive Anfragen nicht nach wenigen Sekunden abbrechen (Wartezeit mindestens 30 s
oder nach der Einschätzung).

**Einordnen statt JSON-Antwort:** Wählt die App aus festen Möglichkeiten (Kategorie, Schlagworte, ja oder nein, Stufe),
fragt sie `POST /v1/einordnen` (PROTOKOLL 6.7) statt das Modell eine JSON-Antwort schreiben zu lassen: schneller, nie
ungültig, mit Wahrscheinlichkeit je Möglichkeit. Die Werte sind nicht geeicht; zum Entscheiden und Sortieren.

## 6. Wo es rechnet

- **Rolle je Rechner** (Leitstelle, Knoten: "Bevorzugt für"): zwischen Rechnern mit demselben Modell gewinnt der
  bevorzugte, auch beim Laden. Eine schon geladene Kopie geht vor Laden auf dem bevorzugten. Die Rolle ändert nie das
  Modell.
- **Vorrang der Sprachausgabe** (Regelwerk "Vorrang auf dem Rechner"): läuft oder wartet Sprache auf einem Mac, startet
  dort nichts Niedrigeres; Nachlauf 30 s.
- **Akku**: unter "keine Arbeit unter" (30 %) bekommt ein Mac keine neuen Aufträge und lädt keine Modelle, auch am
  Netzteil; frei ab "wieder Arbeit ab" (im Haus 70 %).
- **Hintergrund bei Lage und Rechnerlast**: wird es auf einem Mac eng oder braucht ihn der Mensch, wartet Hintergrund
  dort; andere Macs rechnen weiter.
- **Prüffenster** (Abnahme im Betrieb): nur die Anwendung der Abnahme bekommt neue Arbeit, Sprachausgabe läuft weiter.

## 7. Entladen

Jedes Modell und jeder Dienst wird "Entladen nach" (60 s) nach dem letzten laufenden oder wartenden Auftrag entladen,
auch kleine Modelle und die Einbettung; nur der Schutz des Dienstes hält es. Ein wartender Auftrag hält sein Modell.

## 8. Pflichten der App (Prüfliste)

- [ ] nennt bei jeder Anfrage ihr Modell (Einstellung der App, Auswahl aus dem Angebot der Leitstelle)
- [ ] meldet Massenarbeit als `X-Leitstelle-Art: masse`
- [ ] ordnet feste Möglichkeiten über `POST /v1/einordnen` ein, nicht über eine JSON-Antwort
- [ ] setzt `X-Leitstelle-Wichtig: ja` nur auf ausdrückliche Angabe des Nutzers, mit Bestätigung nach ihrer Einstellung
- [ ] zeigt Wartegrund und Wartezeit, statt still aufzugeben; Wartezeit interaktiv mindestens 30 s
- [ ] spricht die Leitstelle nur über den Appkern an, nie Dienste oder Läufer direkt
- [ ] schreibt keine Inhalte in Titel, die andere nicht sehen dürfen (Titel bleiben in der Leitstelle)

## 9. Werte und wo sie stehen

| Wert | Regelwerk | Vorgabe | im Haus |
|---|---|---|---|
| Rangfolge | Vorrang, "Rangfolge" | siehe Abschnitt 3 | Vorgabe |
| Vorrang auf dem Rechner, Nachlauf | Vorrang | Sprachausgabe, 30 s | Vorgabe |
| Ruhe ab | Nur bei Ruhe | 60 s | Vorgabe |
| Entladen nach | Speicher und Laden | 60 s | Vorgabe |
| Akku: keine Arbeit unter, wieder Arbeit ab | Läufer und Last | 30 %, 35 % | 30 %, 70 % |
| Durchlass in der Prüfung, Prüffenster höchstens | Vorrang | Sprachausgabe, 1800 s | Vorgabe |
