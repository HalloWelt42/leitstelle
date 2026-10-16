# Umbau der Anwendungen auf die Leitstelle

Wie die vorhandenen Programme Schritt für Schritt bidirektional mit der Leitstelle sprechen lernen.
Jede Anwendung durchläuft dieselben vier Stufen; keine Stufe erfordert die nächste, jede ist für sich
ein Gewinn. Die Anweisung Schritt für Schritt mit Abnahme steht in [ANBINDUNG.md](ANBINDUNG.md).

## Die vier Stufen

| Stufe | Name | Was die Anwendung tut | Was sie gewinnt | Aufwand |
|---|---|---|---|---|
| 1 | Fassade | Adresse des Modell-Läufers auf die Leitstelle umstellen (zum Beispiel `http://leitstelle:8530/v1`), Schlüssel als Bearer | zentrale Warteschlange, Speicherverwaltung, Aliasse, Verlauf, Kosten; keine Codeänderung | Minuten |
| 2 | Anmeldung | `anwendung.anmelden` mit Name, Fähigkeiten, gewünschter Priorität; Herzschlag | eigene Rechte, Kette, Kontingent, sichtbar als Anwendung | eine Stunde mit der Bibliothek |
| 3 | Signalkanal | WebSocket offen halten, auf `signal.*` reagieren: bei Speicher knapp Stapelarbeit zurückhalten, bei pausiert warten, bei gesperrt sauber melden, bei Modell bereit weitermachen | Anwendung verhält sich kooperativ statt blind in Fehler zu laufen | ein Tag |
| 4 | Eigene Aufträge | Aufträge über das Protokoll statt über die Fassade: Fortschritt, Anhalten, Fortsetzen, Reservierung für Stapel, Teilergebnis bei Abbruch | lange Arbeiten werden steuerbar; die Leitstelle kann sie anhalten statt nur abbrechen | ein bis drei Tage je nach Umfang |

Rückbau gehört dazu: Was die Leitstelle übernimmt (Modell-Manager, Zeitgrenzen-Regel, Modell-Autowahl,
Ausweichlisten von Adressen), wird in der Anwendung entfernt, nicht nur abgeschaltet.

## Die Bibliothek `leitstelle-client`

Python (für FastAPI-Backends) und TypeScript (für Svelte und Node), später Swift (Menüleisten-Apps).
Drei Zeilen für Stufe 2 und 3:

```python
from leitstelle import Leitstelle

ls = Leitstelle("http://leitstelle.local:8530", schluessel=einstellungen.leitstelle_schluessel,
                name="Fundus", faehigkeiten=["text", "einbettung", "werkzeug"])

@ls.signal("speicher")
async def speicher_knapp(s):              # s.zustand in frei, knapp, voll
    einbettung.drossel(an=(s.zustand != "frei"))

@ls.signal("pausiert")
async def pausiert(s):
    einbettung.anhalten()

antwort = await ls.text(nachrichten=[...], prioritaet="hoch", streaming=True)
async for stueck in antwort.stuecke():
    ...
```

Die Bibliothek kapselt Verbindung, Wiederverbindung, Herzschlag, Umschläge und die Fassade als Rückfall
(ist die Leitstelle nicht erreichbar, kann die Anwendung optional direkt an den Modell-Läufer gehen,
sichtbar als Zustand "ohne Leitstelle"). Alle Zeitgrenzen kommen aus der Leitstelle, keine Zahl steht
in der Anwendung.

## Stolpersteine, die die Leitstelle abfängt

| Stolperstein | Lösung in der Leitstelle |
|---|---|
| Modellnamen in Läufer-Schreibweise fest im Code (`text-embedding-bge-m3`, `qwen/qwen3-next-80b`, `qwen3-next-80b-a3b-instruct-mlx`) | Aliasse je Modell; jede Schreibweise löst auf dasselbe Modell |
| Basisadresse mit oder ohne `/v1` | beide werden angenommen |
| `GET /api/v0/models` mit `state` wird von manchen Anwendungen gelesen | nachgebildet, mit echtem Ladezustand aus dem Verbund |
| Fehlendes `model` ergibt 400 beim Läufer | die Leitstelle setzt das Modell aus der Kette ein |
| Gesundheitsprüfung lädt Modell | Gesundheit fragt nur den Zustand, nie eine Vervollständigung |
| Reasoning-Modelle liefern leeren Inhalt bei kleinem Token-Budget | Wiederholung mit größerem Budget und Entfernen der Denkblöcke zentral |
| Enge Zeitgrenzen in Anwendungen (30 s, 60 s, 120 s, 180 s) | Anwendungen übernehmen die Zeitgrenzen der Leitstelle; Arbeit ohne Lese-Grenze |
| Anwendungen, die nur lokale Adressen zulassen | Leitstelle im Heimnetz oder lokale Weiterleitung durch den Agenten |
| Kapazität aus fremden Joblisten geraten | `frage.kapazitaet` und `signal.speicher` |

## Was die Anwendung mindestens können muss (Stufe 3)

1. Signale empfangen und drei Dinge tun können: Stapelarbeit drosseln oder anhalten, Pausen abwarten,
   Sperren und Abbrüche dem Menschen zeigen (nie still weiterlaufen).
2. Teilergebnisse annehmen: ein abgebrochener Textstrom liefert den bisherigen Text; die Anwendung
   zeigt ihn mit Hinweis statt ihn zu verwerfen.
3. Keine eigenen Zeitgrenzen für Arbeit; Abbrechen ist Sache des Menschen oder der Leitstelle.
4. Den Zustand "ohne Leitstelle" sichtbar machen, wenn die Verbindung fehlt.
