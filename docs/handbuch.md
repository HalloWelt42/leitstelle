---
zweck: "Vermittelt alle KI-Arbeit im Haus: Apps geben Aufträge ab, die Leitstelle wählt Dienst, Modell und Rechner, plant den Speicher, lädt und entlädt Modelle und zeigt live, wer was rechnet."
geraet: [pi]
abhaengigkeiten: []
daten:
  - "Pi: Datenordner der Leitstelle {{umgebung:LEITSTELLE_DATENORDNER}} mit `leitstelle.sqlite` (Rechner, Dienste, Modelle, Anwendungen, Regeln, Prüfprotokoll) und `tresor.schluessel`"
sicherung:
  - "keine (Stand 24.10.2026): das Werkzeug Sicherungen führt die Leitstelle als Lücke; Sicherung von Hand wie im Abschnitt Sicherung"
schluessel_orte:
  - "Pi: `tresor.schluessel` im Datenordner; ohne ihn sind die im Tresor gespeicherten Schlüssel und Zugänge nicht lesbar"
  - "Datenbank (verschlüsselt mit dem Tresor): Schlüssel der Anwendungen, der Knoten (Maschinenraum) und externer Anbieter"
einrichten: einrichten.sh
stand: 45b824d
---

# Leitstelle

## Zweck

Die Leitstelle steht zwischen den Apps und allen KI-Diensten. Apps sprechen nur mit ihr, über die gewöhnliche
Schnittstelle im OpenAI-Format (`/v1/chat/completions`, `/v1/embeddings`, `/v1/images/generations`, `/v1/models`) und
über Fassadenwege zu den Diensten (`/v1/dienste/<name>/...`). Sie wählt je Auftrag Dienst, Modell und Rechner, reiht nach Priorität ein, plant
den Speicher, lädt und entlädt Modelle und hält Dienste über den [[Maschinenraum]] des Rechners an oder startet sie.
Die Oberfläche zeigt live, wer was rechnet und wer wartet. In Kopfzeile und Tab-Titel heißt sie "Leitstelle ·
KI-Vermittlung".

Ohne Leitstelle bekommen [[Fundus]], [[Assistent]], [[Vertonung]], [[Transkription]] und die übrigen Apps keine KI:
keine Antworten, keine Einbettung, keine Stimme, kein Hören, keine Bilder. Die Bilddienste des [[Bildwerk]] (je
Bildmodell ein Programm im Maschinenraum) startet sie, wenn eine App ein Bild verlangt, und prüft jede Anfrage vorher
mit dem Steckbrief des Modells (Größen, Schritte, Anzahl).

Auf dem Pi laufen zwei Container aus `docker-compose.yml`: der Kern mit Fassade und Oberfläche auf Port
{{port:docker-compose.yml/leitstelle}} und die Entwürfe auf Port {{port:docker-compose.yml/entwuerfe}}. Beide sind nur
aus privaten Netzen erreichbar.

## Was sie braucht

- Pi nach [[Grundlage Pi]] mit Docker. Der Bau braucht Netz (Pakete, der Maschinenraum als echter Knoten in den
  Tests, die Gestaltung aus dem Repo des [[Appkern]] auf GitHub) und dauert, weil dabei alle Tests laufen.
- Mac nach [[Grundlage Mac]] mit dem Modell-Läufer (Port 1234) und dem [[Maschinenraum]] als Knoten-Agent; für die
  Last des Läufers und das Eingreifen (Arbeiter ohne Auftrag, Hintergrund bei Rechnerlast) dessen Fassung ab 0.15.0,
  für den Docker-Rechner ab 0.16.0, für die Apps des [[Stellwerk]] ab 0.17.0 (das Stellwerk mit Prozessnummern je Teil).
- Das Werkzeug handbuch am Mac ([[Grundlage Mac]]): `tools/ausrollen.sh` fragt es nach Ziel, Ordner und Datenordner
  (`handbuch ziel leitstelle`); das Repo `leitstelle-privat` als Ordner `privat/` trägt die Unterlagen des Hauses.
- Für Bilder: die Dienste des [[Bildwerk]] im Maschinenraum des Macs. Die Leitstelle braucht dafür keinen Eintrag: jeder
  Bilddienst ohne eigenen Eintrag spricht das übliche Bildformat (Einstellung `LEITSTELLE_BILDABLAUF_VORGABE`); nur die
  Bildschmiede hat ab Werk einen eigenen Ablauf (`LEITSTELLE_BILDABLAEUFE`).
- Keine andere App des Verbunds; die Leitstelle kommt gleich nach der [[Kellerwolke]].

## Neu einrichten

Zwei Wege. Aus der Sicherung: den Datenordner mit `leitstelle.sqlite` und `tresor.schluessel` zurückspielen; dann
sind Rechner, Dienste, Anwendungen mit ihren Schlüsseln, Regeln und Ketten wie vorher, und keine App muss neu
angebunden werden. Frisch: leerer Datenordner; dann Läufer, Knoten und jede Anwendung neu anlegen und jeder App ihren
neuen Schlüssel geben.

### 1. Klon am Mac mit dem privaten Teil

```
git clone {{repo}} {{ordner}}
git clone git@github.com:HalloWelt42/leitstelle-privat.git {{ordner}}/privat
```

Probe: `handbuch ziel leitstelle rechner` meldet `{{rechner}}`.

### 2. Datenordner auf dem Zielrechner

Aus der Sicherung das Archiv in den Datenordner `{{umgebung:LEITSTELLE_DATENORDNER}}` entpacken, Besitzer der Benutzer, der Docker startet
(Benutzer 1000 im Container). Frisch legt das Ausrollen den Ordner leer an; `tresor.schluessel` entsteht beim ersten
Start.

Probe: auf dem Zielrechner zeigt `ls {{umgebung:LEITSTELLE_DATENORDNER}}` nach dem Zurückspielen `leitstelle.sqlite` und `tresor.schluessel`
(frisch: nichts, bis Schritt 3 gelaufen ist).

### 3. Ausrollen

Am Mac `tools/ausrollen.sh`: lädt den eingecheckten Stand hoch, klont oder holt ihn auf dem Zielrechner nach `{{wurzel}}`,
baut dort mit Docker (alle Kern-Tests und die Typprüfung der Oberfläche; rot bricht ab und der alte Stand läuft
weiter), wartet auf einen ruhigen Moment ohne laufenden Auftrag und startet beide Dienste. Läuft der neue Stand und
antwortet die Version, räumt es dort Docker auf: verwaiste Abbilder ohne Namen und den Baucache bis auf `BAUCACHE_GB`
(Vorgabe 20 GB; etwa `BAUCACHE_GB=40 tools/ausrollen.sh`), mit dem freigegebenen Platz in der Ausgabe. Scheitert das
Ausrollen, bleibt alles stehen. Auf dem Zielrechner selbst geht dasselbe mit
`LEITSTELLE_DATENORDNER={{umgebung:LEITSTELLE_DATENORDNER}} ./einrichten.sh` im Klon (ohne Aufräumen).

Probe: `curl -s http://<zielrechner>:{{port:docker-compose.yml/leitstelle}}/gesundheit` meldet `"version": "{{fassung}}"`,
und `http://<zielrechner>:{{port:docker-compose.yml/entwuerfe}}/gesundheit` antwortet.

### 4. Läufer und Knoten

Aus der Sicherung stehen sie schon da. Frisch in der Oberfläche unter Dienste den Modell-Läufer des Macs per Adresse
anschließen (Port 1234; Rechner mit Name und Speicher), dann unter Knoten beim Mac "Maschinenraum verbinden" und
Adresse und Schlüssel in der Oberfläche des [[Maschinenraum]] unter Leitstelle eintragen. Den Läufer spricht die
Leitstelle direkt an; der Maschinenraum beobachtet ihn (dort Einstellung `nachbar.modell_laeufer`, Vorgabe
`http://127.0.0.1:1234`): jeder Zugriff am Leitstand vorbei erscheint beim Knoten unter "Am Leitstand vorbei" und in der
Übersicht, die Last seiner Prozesse unter "Läufer und Last".

Probe: unter Dienste stehen die Modelle des Läufers mit Größe und Ladezustand, und er ist bereit; unter Knoten ist der Mac verbunden, meldet seinen Speicher und zeigt unter "Am
Leitstand vorbei" eine Liste oder "Nichts gefunden", unter "Läufer und Last" die Prozesse des Läufers, die Fremdlast
und den Hintergrund (ab Maschinenraum 0.15.0), darunter "Apps des Rechners" und "Docker-Rechner".

### 5. Anwendungen

Aus der Sicherung stehen sie schon da. Frisch je App eine Anwendung anlegen (Name, Priorität, Fähigkeiten, Zonen,
Ketten; die Seite jeder App nennt ihre); der Schlüssel erscheint einmal und geht in die Einstellungen der App. Hat
die App Container im Docker-Rechner eines Rechners, gehören ihre Compose-Projekte (etwa `fundus`) unter
Docker-Projekte: solange sie Hintergrundarbeit hat, zählt deren Last nicht zur Docker-Last.

Probe: die App meldet unter ihren Verbindungen die Leitstelle als verbunden, und ihr erster Auftrag erscheint in der
Oberfläche der Leitstelle.

### 6. Bilddienste

Nichts einzurichten: die Leitstelle sieht die Bilddienste, sobald der Maschinenraum sie meldet. Darf eine App Bilder
erzeugen, braucht sie die Fähigkeit "Bild erzeugen". Das Bildmodell wählt die App selbst (`model`, etwa
`bildwerk-moss-image`, dazu wahlweise Alternativen in ihrer Reihenfolge); soll sie ohne Angabe ein festes Bildmodell
nutzen, steht das als ihre Wahl in ihrer Kette für Bilder. Die Leitstelle sucht nie selbst ein Modell aus. Der erste Auftrag startet den Dienst (MOSS-Image bis 5 Minuten); danach liest die
Leitstelle seinen Steckbrief und behält ihn.

Probe: unter Dienste steht bei "Dienste auf <Mac>" das Programm "Bildwerk MOSS-Image · Bild erzeugen"; nach dem ersten
Bild stehen dort und unter Modelle seine Grenzen (Modell, Kanten, Schritte, Bilder je Anfrage, Lizenz), und im Verlauf
"Steckbrief von Bildwerk MOSS-Image gelesen".

## Sicherung und Rückspielen

Es gibt keine regelmäßige Sicherung (Stand 24.10.2026); das Werkzeug Sicherungen am Mac führt die Leitstelle als
Lücke (`~/Sicherungen/LIESMICH.md`). Gesichert werden muss der ganze Datenordner: die SQLite-Datei allein nützt
nichts, weil die gespeicherten Schlüssel nur mit `tresor.schluessel` lesbar sind.

Von Hand auf dem Zielrechner im Klon: `docker compose stop leitstelle`, den Datenordner als Archiv packen
(`tar -czf leitstelle_<Zeit>.tar.gz -C <eltern> <datenordner>`), `docker compose start leitstelle`. Zurückspielen:
Dienst anhalten, Archiv in den Datenordner entpacken, starten; Probe wie in Schritt 4.

## Wenn etwas klemmt

- Das Ausrollen bricht beim Bauen ab: ein Test ist rot oder die Oberfläche hat Typfehler; der alte Stand läuft weiter.
  Die Ausgabe des Baus nennt den Test.
- Das Ausrollen wartet: es lässt laufende Aufträge auslaufen, höchstens `WARTEN_S` Sekunden (Vorgabe 600);
  `SOFORT=1 tools/ausrollen.sh` startet ohne zu warten.
- Apps melden "Leitstelle nicht erreichbar": Container prüfen (`docker compose ps`, `docker logs -f leitstelle`); der
  Appkern der Apps wartet eine Weile und versucht es erneut.
- Modelle laden nicht: der Läufer am Mac schläft oder lauscht nur lokal (Netzwerk des Läufers, siehe
  [[Grundlage Mac]]), oder das Budget des Rechners reicht nicht (Oberfläche, Modelle).
- In der Übersicht steht "Zugriffe am Leitstand vorbei": ein Programm spricht ein Modell des Rechners ohne die Leitstelle
  an oder hält ein eigenes Modell im Speicher. Unter Knoten stehen Wer, Prozess und Arbeitsordner; das Programm auf die
  Leitstelle umstellen. "Vermutlich die Leitstelle selbst (direkter Weg)" zählt nicht: die Leitstelle spricht den Läufer
  selbst direkt an.
- Unter Knoten steht bei einem Arbeiter des Läufers "arbeitet ohne Auftrag": er rechnet seit der Frist (Vorgabe 5 min)
  über der Schwelle, ohne dass die Leitstelle dort etwas rechnen lässt. Hängt am Läufer ein Programm am Leitstand
  vorbei, rechnet er vermutlich dafür (das Programm umstellen); sonst "Prozess beenden" (Bestätigung in der Leiste), der
  Läufer lädt das Modell bei Bedarf neu. Die Regel "Läufer ohne Auftrag" täte das selbst, ist ab Werk aber aus;
  einschalten unter Regeln, Läufer und Last.
- Hintergrundarbeit stockt auf einem Rechner: in der Übersicht steht "Hintergrund gedrosselt" oder "angehalten", weil
  der Mensch den Rechner gerade braucht (Fremdlast ab 50 beziehungsweise 75 % im Mittel) oder sein Docker-Rechner
  ausgelastet ist (Docker-Last ab 70 beziehungsweise 90 %); der Grund nennt das Maß. Das gibt sich von selbst, sobald
  beide Maße 10 Punkte unter ihre Grenze fallen; normale und dringende Aufträge sind nicht betroffen. Grenzen und
  Abstand stehen unter Regeln, Läufer und Last; ausgeschaltet gibt die Regel jeden gebremsten Rechner sofort frei.
  Bremst sich die Leitstelle an der eigenen Hintergrundarbeit in einem Container (die Docker-Last fällt, sobald der
  Hintergrund steht), fehlen bei der Anwendung die Docker-Projekte.
- Einbettungen stehen lange auf "Wartet auf Ruhe": gewollt. Masseneinbettung (Priorität Hintergrund) ist Arbeit nur
  bei Ruhe; sie bekommt erst ein Modell, wenn keine andere Arbeit läuft oder wartet und die letzte seit 60 s vorbei
  ist. Der laufende Stapel rechnet zu Ende, dann warten die übrigen; die Anfrage der App bleibt offen (kein Fehler,
  keine Zeitüberschreitung). Suchen und Fragen (Priorität normal) warten nicht. Welche Fähigkeiten, bis zu welcher
  Priorität und wie lange Ruhe sein muss, steht unter Regeln, Nur bei Ruhe; ohne Fähigkeit dort gilt die Regel nicht.
- Unter Knoten steht bei "Apps des Rechners" "Nicht zugeordnet": das Stellwerk antwortet dem Maschinenraum nicht oder
  meldet keine Prozessnummern; der Grund steht dabei. Dann zählen die Apps wieder als Speicher am Leitstand vorbei und
  zur Fremdlast.
- Ein externer Anbieter lässt Aufträge warten ("Grenze von ... je Minute erreicht" oder "gesperrt bis"): unter Dienste
  stehen je Modell Anfragen und Token der letzten 60 Sekunden neben den Grenzen des Schlüssels; die Grenzen dort an die
  des Anbieters anpassen. Ob ein externes Modell Bilder versteht, belegt "Fähigkeiten prüfen" am Dienst (zählt gegen die
  Grenzen).
- Eine App bekommt bei einem Bild 400 `modell_fehlt`: sie nennt kein Bildmodell und hat in der Leitstelle keine Kette
  für Bilder; die Antwort nennt die Bildmodelle zur Wahl. In der App das Modell einstellen (oder bei der Anwendung eine
  Kette für Bilder hinterlegen).
- Eine App bekommt bei einem Bild 400 `eingabe`: Größe, Anzahl oder Schritte passen nicht zum Modell; der Satz nennt
  die Grenze (MOSS-Image: Kanten 256 bis 2048, durch 16 teilbar, Fläche mindestens 512x512, 1 bis 218 Schritte). Bis
  der Dienst einmal lief, prüft die Leitstelle mit den Vorgabegrenzen, danach mit seinem Steckbrief.
- Das erste Bild dauert Minuten: der Bilddienst startet und lädt sein Modell (Hinweis "startet auf ... seit"); ab dem
  zweiten Start nennt der Hinweis die gemessene Restzeit. 503 `dienst_nicht_bereit` heißt: der Dienst läuft, sein Modell
  ist aber nicht bereit (Protokoll des Dienstes im Maschinenraum). 503 `kein_dienst` gibt es nur, wenn die Vorgabe für
  Bilddienste abgeschaltet ist und der Dienst keinen eigenen Eintrag hat.
- Ein abgebrochenes Bild rechnet im Bilddienst zu Ende (der Maschinenraum reicht das Schließen erst weiter, wenn der
  Dienst antwortet); das nächste Bild wartet dort so lange.
- Eine Maßnahme der Selbststeuerung stört: unter Regeln abschalten oder ihre Werte ändern (wirkt sofort, steht im
  Prüfprotokoll); "von Hand" zeigt, was von der Vorgabe abweicht, der Pfeil daneben stellt sie wieder her.
- Gespeicherte Schlüssel sind unlesbar: `tresor.schluessel` fehlt oder gehört zu einer anderen Datenbank.
