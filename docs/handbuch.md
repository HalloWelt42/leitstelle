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
stand: 383d2d7
---

# Leitstelle

## Zweck

Die Leitstelle steht zwischen den Apps und allen KI-Diensten. Apps sprechen nur mit ihr, über die gewöhnliche
Schnittstelle im OpenAI-Format (`/v1/chat/completions`, `/v1/embeddings`, `/v1/models`) und über Fassadenwege zu den
Diensten (`/v1/dienste/<name>/...`). Sie wählt je Auftrag Dienst, Modell und Rechner, reiht nach Priorität ein, plant
den Speicher, lädt und entlädt Modelle und hält Dienste über den [[Maschinenraum]] des Rechners an oder startet sie.
Die Oberfläche zeigt live, wer was rechnet und wer wartet.

Ohne Leitstelle bekommen [[Fundus]], [[Assistent]], [[Vertonung]], [[Transkription]] und die übrigen Apps keine KI:
keine Antworten, keine Einbettung, keine Stimme, kein Hören.

Auf dem Pi laufen zwei Container aus `docker-compose.yml`: der Kern mit Fassade und Oberfläche auf Port
{{port:docker-compose.yml/leitstelle}} und die Entwürfe auf Port {{port:docker-compose.yml/entwuerfe}}. Beide sind nur
aus privaten Netzen erreichbar.

## Was sie braucht

- Pi nach [[Grundlage Pi]] mit Docker. Der Bau braucht Netz (Pakete, der Maschinenraum als echter Knoten in den
  Tests, die Gestaltung aus dem Repo des [[Appkern]] auf GitHub) und dauert, weil dabei alle Tests laufen.
- Mac nach [[Grundlage Mac]] mit dem Modell-Läufer (Port 1234) und dem [[Maschinenraum]] als Knoten-Agent; für den
  Weg zum Läufer über den Maschinenraum dessen Fassung ab 0.14.0.
- Das Werkzeug handbuch am Mac ([[Grundlage Mac]]): `tools/ausrollen.sh` fragt es nach Ziel, Ordner und Datenordner
  (`handbuch ziel leitstelle`); das Repo `leitstelle-privat` als Ordner `privat/` trägt die Unterlagen des Hauses.
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
weiter), wartet auf einen ruhigen Moment ohne laufenden Auftrag und startet beide Dienste. Auf dem Zielrechner selbst
geht dasselbe mit `LEITSTELLE_DATENORDNER={{umgebung:LEITSTELLE_DATENORDNER}} ./einrichten.sh` im Klon.

Probe: `curl -s http://<zielrechner>:{{port:docker-compose.yml/leitstelle}}/gesundheit` meldet `"version": "{{fassung}}"`,
und `http://<zielrechner>:{{port:docker-compose.yml/entwuerfe}}/gesundheit` antwortet.

### 4. Läufer und Knoten

Aus der Sicherung stehen sie schon da. Frisch in der Oberfläche unter Dienste den Modell-Läufer des Macs per Adresse
anschließen (Port 1234; Rechner mit Name und Speicher), dann unter Knoten beim Mac "Maschinenraum verbinden" und
Adresse und Schlüssel in der Oberfläche des [[Maschinenraum]] unter Leitstelle eintragen. Danach unter Dienste beim
Läufer (Bearbeiten) den Schalter "Über den Maschinenraum" einschalten: die Leitstelle spricht den Läufer dann über die
Durchleitung des Maschinenraums an (dort Einstellung `nachbar.modell_laeufer`, Vorgabe `http://127.0.0.1:1234`), und
jeder Zugriff am Leitstand vorbei erscheint beim Knoten unter "Am Leitstand vorbei" und in der Übersicht. Die Adresse
des Läufers bleibt eingetragen; Schalter aus heißt sofort wieder direkt (Rückfall von Hand, nie von selbst).

Probe: unter Dienste stehen die Modelle des Läufers mit Größe und Ladezustand, beim Läufer steht "über den
Maschinenraum" und er ist bereit; unter Knoten ist der Mac verbunden, meldet seinen Speicher und zeigt unter "Am
Leitstand vorbei" eine Liste oder "Nichts gefunden".

### 5. Anwendungen

Aus der Sicherung stehen sie schon da. Frisch je App eine Anwendung anlegen (Name, Priorität, Fähigkeiten, Zonen,
Ketten; die Seite jeder App nennt ihre); der Schlüssel erscheint einmal und geht in die Einstellungen der App.

Probe: die App meldet unter ihren Verbindungen die Leitstelle als verbunden, und ihr erster Auftrag erscheint in der
Oberfläche der Leitstelle.

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
- Modelle laden nicht: der Läufer am Mac schläft oder lauscht auf dem direkten Weg nur lokal (Netzwerk des Läufers,
  siehe [[Grundlage Mac]]; über den Maschinenraum genügt lokal), oder das Budget des Rechners reicht nicht (Oberfläche,
  Modelle).
- Der Läufer ist nicht erreichbar mit "Maschinenraum nicht verbunden; Rückfall: Schalter 'über den Maschinenraum' aus":
  der Schalter ist an, aber der Maschinenraum des Macs meldet sich nicht. Antwortet er mit "Diesen Dienst gibt es hier
  für die Leitstelle nicht: laeufer", ist er älter als 0.14.0; mit "keinen Modell-Läufer eingetragen" fehlt dort
  `nachbar.modell_laeufer`. Rückfall von Hand: unter Dienste beim Läufer den Schalter aus.
- In der Übersicht steht "Zugriffe am Leitstand vorbei": ein Programm spricht ein Modell des Rechners ohne die Leitstelle
  an oder hält ein eigenes Modell im Speicher. Unter Knoten stehen Wer, Prozess und Arbeitsordner; das Programm auf die
  Leitstelle umstellen. "Vermutlich die Leitstelle selbst (direkter Weg)" zählt nicht; der Schalter "über den
  Maschinenraum" macht auch diesen Fall eindeutig.
- Gespeicherte Schlüssel sind unlesbar: `tresor.schluessel` fehlt oder gehört zu einer anderen Datenbank.
