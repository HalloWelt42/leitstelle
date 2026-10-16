# Messungen

Entscheidungen der Leitstelle beruhen auf Messungen. Hier stehen die Messpunkte des Plans mit Zahlen,
Aufbau und Folgerung. Jede Messung lässt sich mit dem genannten Werkzeug wiederholen.

## Messpunkt Staffel 1: Kosten der Durchleitung (Fassade)

Frage aus dem Plan: Bremst die Durchleitung der Ströme in Python spürbar, oder kann sie in Python bleiben?

**Aufbau:** `tools/messen_fassade.py` startet einen schnellen Schein-Läufer (100 Stücke je Antwort, 2 ms Pause)
und einen frischen Kern als eigene Prozesse auf demselben Rechner. Verglichen wird ein Strom direkt vom Läufer
mit demselben Strom über `/v1/chat/completions` der Leitstelle: 50 Läufe nacheinander, dann 20 gleichzeitig.
Läufer und Kern teilen sich den Rechner; der Aufschlag enthält also auch den Wettbewerb um den Prozessor.

```bash
backend/.venv/bin/python tools/messen_fassade.py
```

Auf dem Pi im Prüfabbild:

```bash
docker build --target kern -t leitstelle-pruefung . && docker run --rm leitstelle-pruefung python tools/messen_fassade.py
```

### Pi Archiv (aarch64), 16.10.2026, Fassung 0.4.2

| Messung | direkt | über die Leitstelle | Aufschlag |
|---|---|---|---|
| Erstes Stück, Median | 3,9 ms | 11,1 ms | +7,2 ms |
| Erstes Stück, 95. Perzentil | 6,2 ms | 20,3 ms | +14,1 ms |
| Ganzer Strom, Median | 219,6 ms | 229,4 ms | +9,7 ms |
| 20 Ströme gleichzeitig, Gesamtdauer | 0,30 s | 0,53 s | +0,22 s |
| 20 Ströme gleichzeitig, Stücke je Sekunde | 6.717 | 3.846 | -43 % |
| 20 Ströme gleichzeitig, erstes Stück höchstens | 40,5 ms | 306,4 ms | +265,9 ms |

### Mac (arm64), 16.10.2026, Fassung 0.4.2

| Messung | direkt | über die Leitstelle | Aufschlag |
|---|---|---|---|
| Erstes Stück, Median | 4,0 ms | 8,2 ms | +4,2 ms |
| Erstes Stück, 95. Perzentil | 6,6 ms | 13,9 ms | +7,3 ms |
| Ganzer Strom, Median | 239,7 ms | 244,6 ms | +4,9 ms |
| 20 Ströme gleichzeitig, Gesamtdauer | 0,25 s | 0,31 s | +0,06 s |
| 20 Ströme gleichzeitig, Stücke je Sekunde | 8.117 | 6.508 | -20 % |
| 20 Ströme gleichzeitig, erstes Stück höchstens | 20,7 ms | 84,8 ms | +64,2 ms |

### Was die Messung verändert hat

Die erste Fassung horchte je Stück mit zwei Hilfsaufgaben gleichzeitig auf den Strom und auf einen Abbruch. Auf
dem Mac kostete das 40 Prozent Durchsatz bei 20 Strömen (3.740 statt 6.199 Stücke je Sekunde). Seit 0.4.2
schließt ein Abbruch den Strom des Dienstes von außen; die Schleife liest ohne Zusatzaufwand. Das brachte auf dem
Mac 6.508 Stücke je Sekunde.

### Folgerung

Ein Sprachmodell liefert je Strom etwa 20 bis 80 Token je Sekunde; ein Stück ist meist ein Token. 20 gleichzeitige
Ströme sind damit 400 bis 1.600 Stücke je Sekunde, ein Zehntel bis zwei Fünftel dessen, was der Pi durchleitet. Der
Aufschlag von 7 ms bis zum ersten Stück liegt weit unter der Zeit, die ein Modell bis zu seinem ersten Token braucht
(Hunderte Millisekunden bis Sekunden). **Die Durchleitung bleibt in Python.** Nachmessen, wenn regelmäßig mehr als
20 Ströme gleichzeitig laufen; der Durchleitungsbaustein ist so geschnitten, dass er ersetzt werden kann.

Offen beobachtet: Bei 20 gleichzeitig ankommenden Aufträgen wartet der letzte bis zu 0,3 s auf sein erstes Stück,
weil jede Annahme sofort zuteilt und speichert. Für den Alltag unerheblich; bei Stapeln über die Fassade ein Kandidat
für gebündeltes Zuteilen.
