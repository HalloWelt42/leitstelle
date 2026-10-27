# Anbindung an die Leitstelle: Implementierungsanweisung

Für Menschen und für KI-Agenten, die ein Programm an die Leitstelle anschließen. Diese Anweisung ist
vollständig: wer sie befolgt, braucht keine weitere Absprache. Der Leitfaden der vier Stufen steht in
[UMBAU.md](UMBAU.md), der Vertrag der Nachrichten in [PROTOKOLL.md](PROTOKOLL.md), die Zusagen der Leitstelle
an ihre Teilnehmer in [ARCHITEKTUR.md](ARCHITEKTUR.md) Abschnitt 5 und unten in Abschnitt 8.

Stand 16.10.2026, Fassung 0.4: Die Leitstelle läuft im Betrieb (Beispieladresse in diesem Text:
`http://leitstelle:8530`). Fassade
(Stufe 1), Verwaltung, Oberfläche und Live-Kanal der Oberfläche sind in Betrieb und geprüft (siehe
[SZENARIEN.md](SZENARIEN.md), Messungen in [MESSUNGEN.md](MESSUNGEN.md)). Anmeldung und Signale über den Kanal
(Stufe 2 und 3) und die Bibliothek kommen mit Staffel 3 des [Plans](PLAN.md); die Schnittstellen hier sind
verbindlich, was noch nicht läuft, ist so gekennzeichnet.

## 0. Begriffe in einem Satz

| Begriff | Bedeutung |
|---|---|
| Anwendung | ein Programm, das Aufträge abgibt (Zusage, Fundus, TubeVault, Codehilfe) |
| Dienst | ein Programm, das rechnet (Modell-Läufer, Sprachdienst, Hörer, Bild-Werkbank, externer Anbieter) |
| Knoten | ein Rechner mit Agent (MacBook, Pi, Server) |
| Fähigkeit | was ein Auftrag braucht: text, einbettung, uebersetzen, hoeren, bild_beschreiben, bild_erzeugen, stimme, musik, werkzeug |
| Kette | geordnete Liste von Modellfamilien je Fähigkeit und Anwendung; die Leitstelle nimmt das erste, das passt |
| Zone | heim, vpn, extern; die Anwendung bestimmt, wo ihre Daten rechnen dürfen |
| Priorität | hintergrund, normal, hoch, dringend; hoch und dringend nehmen den Direktweg |
| Signal | Nachricht der Leitstelle an eine Anwendung ohne Aufforderung: Speicher, Lage, pausiert, gesperrt, Modell |
| Hauptregler | Normal, Auslaufen, Halt; geht allen Regeln vor |
| Maßnahme | eine Umschichtung der Leitstelle aus eigenem Antrieb, immer mit Grund, Gewinn und Aufwand in Sekunden |

## 1. Welche Rolle hat mein Programm?

1. Es ruft Modelle auf (Chat, Einbettung, Transkription, Sprachausgabe, Bild): **Anwendung**, weiter mit 2.
2. Es stellt Modelle oder Rechenleistung bereit (eigener Whisper, ComfyUI, Worker): **Dienst**, weiter mit 6.
3. Es ist ein Rechner, auf dem Dienste laufen: **Knoten**, weiter mit 7.
4. Beides (txt2voice ist Dienst für Stimme und Hören und zugleich Anwendung für Korrektur und
   Übersetzung): beide Wege, getrennte Schlüssel, getrennte Namen.

Jede Anwendung durchläuft bis zu vier Stufen. Keine Stufe setzt die nächste voraus; jede ist für sich
fertig und nützlich. Programme, die nur die gewöhnliche Vervollständigungs-Schnittstelle kennen, bleiben
dauerhaft auf Stufe 1. Das ist ein voller Weg, kein Übergang.

## 2. Stufe 1: Fassade (dauerhaft verträglich für alle, die nur die gewöhnliche Schnittstelle kennen)

Die Anwendung ändert nur die Adresse ihres Modell-Läufers und bekommt einen Schlüssel. Nichts sonst.

### 2.1 Was zu tun ist

| Schritt | Tun | Prüfen |
|---|---|---|
| Adresse | Basisadresse auf `http://leitstelle:8530/v1` (mit oder ohne `/v1`, beides geht) | `GET /v1/models` liefert die erlaubten Modelle |
| Schlüssel | `Authorization: Bearer <schluessel>`; den Schlüssel erzeugt die Leitstelle unter Anwendungen, Anwendung anmelden | Antwort ohne 401 |
| Modellname | darf bleiben wie er ist (jede Schreibweise des Läufers ist ein Alias), darf der Name einer Kette sein (`gross`, `schnell`, `bild`) oder fehlen (dann gilt die Kette der Anwendung) | `GET /v1/models` zeigt `x-leitstelle.geladen` |
| Zeitgrenzen | Lese-Zeitgrenze für laufende Arbeit entfernen; Verbindungsaufbau-Grenze bleibt (10 s). Die Leitstelle sendet alle 15 s einen SSE-Kommentar `: wartet, <grund>, etwa <n> s`, solange ein Auftrag wartet | eine Vervollständigung, die 3 Minuten wartet, bricht nicht ab |
| Ausweichlisten | Komma-Listen mehrerer Läufer-Adressen entfernen; die Leitstelle kennt alle Läufer | nur eine Adresse in der Konfiguration |
| Eigene Modellverwaltung | Laden, Entladen, Autowahl, Speicherprüfung in der Anwendung entfernen, nicht nur abschalten | kein Aufruf von `lms`, `/api/v0/models` zum Laden, `vm_stat` mehr |
| Gesundheitsprüfung | nur `GET /v1/models`, nie eine Vervollständigung | lädt kein Modell |

### 2.2 Was die Fassade zusagt

- Gleiche Antwortform wie der Läufer: `chat/completions` mit und ohne Streaming, `embeddings`,
  `audio/transcriptions`, `audio/speech`, `images/generations`; `usage` am Ende.
- `GET /api/v0/models` und `GET /api/v1/models` werden nachgebildet (Feld `state`,
  `loaded_instances`) mit dem echten Ladezustand des Verbunds, weil TubeVault, Federflink und Kiste genau
  diese Form lesen.
- Zusätzliche Antwortköpfe, die niemand lesen muss: `X-Leitstelle-Auftrag` (Kennung), `X-Leitstelle-Lage`,
  `X-Leitstelle-Wartet-S` (geschätzte Wartezeit, wenn der Auftrag beim Antworten wartet); bei Antworten ohne Strom
  zusätzlich `X-Leitstelle-Modell` und `X-Leitstelle-Knoten`.
- Köpfe, die eine Anwendung senden darf: `X-Leitstelle-Prioritaet` (`hintergrund`, `normal`, `hoch`, `dringend`;
  senkt die Vorgabe der Anwendung, hebt sie nie), `X-Leitstelle-Titel` (lesbarer Titel für Oberfläche und
  Verlauf; HTTP-Köpfe tragen nur ASCII, Umlaute deshalb prozentkodiert, zum Beispiel `Quelltext%20pr%C3%BCfen`) und
  `X-Leitstelle-Arbeit` (Kennung einer Arbeit der Anwendung, die aus vielen Anfragen besteht, etwa ein Auftrag einer
  Vertonung; 1 bis 64 Zeichen aus `A-Z a-z 0-9 . _ : -`, sonst zählt die Anfrage für sich). Ab der zweiten Anfrage gilt
  die Arbeit als begonnen: Modelle, die sie in den letzten `arbeit_frist_s` (Vorgabe 300 s) genutzt hat, entlädt die
  Leitstelle nicht für andere, nur für die Arbeit selbst. Der Appkern setzt den Kopf in jedem Auftrag von selbst.
- `X-Leitstelle-Extern`: Erlaubnisliste der Anwendung für externe Modelle (Namen durch Komma, prozentkodiert). Nur
  Modelle auf dieser Liste oder ausdrücklich als `model` verlangte dürfen nach extern; ohne den Kopf weicht die
  Leitstelle für die Anfrage nie nach extern aus. Zusätzlich muss die Leitstelle der Anwendung die Zone extern
  erlauben. Der Appkern liest die Liste aus der Einstellung "Ausweichen nach extern" der App.
- `X-Leitstelle-Instanz` (Antwort jeder Durchleitung und Folgeaufruf): an dieselbe Instanz wie der erste Aufruf,
  wenn ein Dienst mehrfach läuft (PROTOKOLL 6, Bindung). Ohne Bindung kann "Ergebnis abholen" bei einer anderen
  Instanz landen, die die Datei nicht hat.
- `POST /v1/images/generations` (`prompt`, `size`, `n` 1 bis 4, `seed`, `model`, `stream`): Bilder als `b64_json`, mit
  dem genutzten Startwert unter `x-leitstelle.seed`; gleicher Startwert und gleiche Beschreibung ergeben dasselbe Bild.
  Den Ablauf der Bildschmiede kennt nur die Leitstelle (PROTOKOLL 6.1). Die Anwendung braucht das Recht
  `bild_erzeugen` und nennt den Dienst als `model` oder hat eine Kette für `bild_erzeugen`.
- `GET /v1/dienste`: die Dienste im Maschinenraum, die die Anwendung nutzen darf, mit `kennung`, `name`,
  `faehigkeiten`, `zustand` (`bereit`, `startet`, `aus`, `schlaeft`, `nicht_erreichbar`) und `rechner`
  (PROTOKOLL 6.2); etwa für eine Auswahl "Bilder erzeugen mit".
- `GET /v1/steckbriefe` (Filter `faehigkeit`, `eignung`, `sprache`): wofür welches Modell gemacht ist
  (PROTOKOLL 4.8); dieselben Steckbriefe stehen in `GET /v1/models` unter `x-leitstelle.steckbrief`.
- Externe Modelle gezielt wählen: bietet ein Anbieter ein Mischmodell mit wenigen aktiven Parametern und ein dichtes
  an, heißt das erste im Steckbrief `schnell` (für kurze Aufgaben) und das zweite `gruendlich` (für lange Texte und
  schwierige Fragen). Die Wahl bleibt bei der Anwendung: das gewünschte Modell als `model` nennen (und die Zone extern
  erlaubt haben) oder auf die Erlaubnisliste setzen; die Leitstelle wählt dann nur beim Ausweichen. Grenzen je Minute
  des Anbieters (Anfragen, Token hinein und heraus) hält die Leitstelle ein; wer darüber läge, wartet mit Hinweis.
- Mehr gleichzeitige Aufträge als erlaubt warten in der Warteschlange statt abgelehnt zu werden.
- Fehlt `model`, setzt die Leitstelle das erste passende Modell der Kette ein.
- Reasoning-Modelle mit leerem Inhalt: die Leitstelle wiederholt mit größerem Budget und entfernt die
  Denkblöcke, bevor die Antwort die Anwendung erreicht.
- Fehler in der Form des Läufers, dazu ein Wort im Feld `error.code`:

| HTTP | `error.code` | Wann | Was die Anwendung tut |
|---|---|---|---|
| 401 | `unbekannter_schluessel` | Schlüssel falsch oder widerrufen | Hinweis zeigen, nicht wiederholen |
| 403 | `faehigkeit_nicht_erlaubt`, `zone_nicht_erlaubt` | Rechte der Anwendung | Hinweis zeigen |
| 404 | `kein_modell` | Modellname unbekannt, oder kein Modell genannt und keine Kette eingerichtet | Namen prüfen oder in der Leitstelle einen Zweitnamen oder eine Kette eintragen |
| 429 | `gesperrt` | Anwendung gesperrt (von Hand oder nach Auslaufen) | `Retry-After` beachten, Hinweis zeigen |
| 503 | `halt` | Hauptregler steht auf Halt | Hinweis zeigen, nach `Retry-After` erneut |
| 503 | `dienst_nicht_erreichbar`, `modell_passt_nicht` | Dienst weg, oder er hat das Laden dreimal abgelehnt | Hinweis zeigen, später erneut |
| 503 | `rechner_schlaeft` | der Rechner mit dem Modell schläft; `error.x-leitstelle.rechner` nennt ihn, `Retry-After` 60 s | "wartet, bis MacBook M4 Max 128 GB wach ist" zeigen und ohne Grenze erneut versuchen, bis er wach ist (Abbrechen erlauben) |
| 502 | `dienst_fehler` | der Dienst hat den Auftrag nicht geschafft; `wiederholbar` im Text | einmal wiederholen, wenn wiederholbar |

- Bricht der Nutzer einen Auftrag in der Leitstelle sofort ab, endet der Strom mit einem letzten Stück
  `finish_reason: "leitstelle_abbruch"` und dem bisherigen Text. Die Anwendung zeigt den Teiltext mit
  Hinweis statt ihn zu verwerfen. Beim Auslaufen rechnet der Auftrag fertig.
- Stufe-1-Anwendungen gelten als nicht anhaltbar und haben die Priorität, die am Schlüssel steht.

### 2.3 Abnahme Stufe 1

1. Vervollständigung mit Streaming läuft, Antwort gleich wie vorher.
2. Ein Auftrag, der 3 Minuten auf Speicher wartet, kommt an (kein Abbruch durch Zeitgrenze).
3. Halt am Hauptregler: die Anwendung zeigt einen Hinweis statt einer Fehlerspur.
4. In der Leitstelle erscheint die Anwendung unter Anwendungen mit Name und Schlüssel, der Auftrag im
   Verlauf mit Dauer und Modell.
5. Rückbau sichtbar: kein eigener Modell-Manager, keine Ausweichliste, keine Lese-Zeitgrenze.

## 3. Stufe 2: Anmeldung

Die Anwendung sagt, wer sie ist und was sie braucht, und hält die Verbindung. Dafür gibt es die
Bibliothek `leitstelle-client` (Python und TypeScript, Staffel 3). Bis sie da ist, reichen zwei
Nachrichten über den Kanal, wie unten gezeigt.

### 3.1 Einstellungen in der Anwendung

Genau zwei Werte: `LEITSTELLE_ADRESSE` und `LEITSTELLE_SCHLUESSEL`. Alles andere (Ketten, Rechte,
Priorität, Herzschlag-Takt, Zeitgrenzen) kommt mit `anwendung.angemeldet` von der Leitstelle. Keine Zahl
dazu steht in der Anwendung.

### 3.2 Ablauf

1. WebSocket auf `ws://leitstelle:8530/api/kanal` mit `Authorization: Bearer <schluessel>` öffnen
   (`wss://` außerhalb des Heimnetzes, Pflicht für Zone extern).
2. `anwendung.anmelden` senden mit `name`, `version`, `bibliothek`, `faehigkeiten` (gewünscht),
   `signale: true`, wenn Stufe 3 umgesetzt ist, sonst `false`.
3. `anwendung.angemeldet` lesen und merken: `kennung`, `rechte`, `ketten`, `herzschlag_s`, `lage`,
   `auftraege` (Stand aller offenen Aufträge, wichtig nach Wiederverbindung).
4. Alle `herzschlag_s` einen `herzschlag` senden; die Leitstelle antwortet mit `herzschlag`. Bleibt die
   Antwort zweimal aus, gilt die Verbindung als weg: neu verbinden mit wachsender Pause (1, 2, 4, bis
   höchstens 30 s), dabei den Zustand "ohne Leitstelle" in der eigenen Oberfläche zeigen.
5. Nach jeder Wiederverbindung erneut anmelden; `auftraege` in der Antwort mit dem eigenen Stand
   abgleichen (Aufträge, die inzwischen fertig sind, nachholen).

### 3.3 Umschlag

Jede Nachricht ist ein JSON-Objekt:

```json
{"protokoll": "leitstelle/1", "art": "anwendung.anmelden", "id": "a1f3...", "zeit": "2026-10-16T19:04:12+02:00",
 "von": "fundus", "an": "leitstelle", "bezug": null,
 "nutzlast": {"name": "Fundus", "version": "2.4.0", "bibliothek": "leitstelle-client-python 0.1",
              "faehigkeiten": ["text", "einbettung", "werkzeug"], "signale": true, "herkunft": "192.168.1.30"}}
```

Antworten tragen in `bezug` die `id` der Frage. Unbekannte Arten werden ignoriert, eigene Felder beginnen
mit `x-`.

### 3.4 Python ohne Bibliothek (FastAPI-Backend)

```python
import asyncio, json, uuid
from datetime import datetime, timezone
import websockets

class Leitstelle:
    def __init__(self, adresse: str, schluessel: str, name: str, faehigkeiten: list[str]) -> None:
        self.adresse, self.schluessel, self.name, self.faehigkeiten = adresse, schluessel, name, faehigkeiten
        self.verbunden = False
        self.rechte: dict = {}
        self.ketten: dict = {}
        self.handler: dict[str, list] = {}

    def umschlag(self, art: str, nutzlast: dict, bezug: str | None = None) -> str:
        return json.dumps({"protokoll": "leitstelle/1", "art": art, "id": uuid.uuid4().hex,
                           "zeit": datetime.now(timezone.utc).isoformat(), "von": self.name.lower(),
                           "an": "leitstelle", "bezug": bezug, "nutzlast": nutzlast})

    def signal(self, art: str):
        def merken(f):
            self.handler.setdefault(f"signal.{art}", []).append(f)
            return f
        return merken

    async def laufen(self) -> None:
        pause = 1
        while True:
            try:
                async with websockets.connect(self.adresse.replace("http", "ws") + "/api/kanal",
                                              additional_headers={"Authorization": f"Bearer {self.schluessel}"}) as ws:
                    await ws.send(self.umschlag("anwendung.anmelden", {"name": self.name, "version": "1.0",
                                   "bibliothek": "eigen 0.1", "faehigkeiten": self.faehigkeiten, "signale": True}))
                    pause = 1
                    herzschlag = None
                    async for roh in ws:
                        n = json.loads(roh)
                        if n["art"] == "anwendung.angemeldet":
                            self.rechte, self.ketten = n["nutzlast"]["rechte"], n["nutzlast"]["ketten"]
                            self.verbunden = True
                            herzschlag = asyncio.create_task(self._herzschlag(ws, n["nutzlast"]["herzschlag_s"]))
                        for f in self.handler.get(n["art"], []):
                            await f(n["nutzlast"])
            except (OSError, websockets.WebSocketException):
                pass
            self.verbunden = False            # Oberfläche zeigt "ohne Leitstelle"
            await asyncio.sleep(pause)
            pause = min(pause * 2, 30)

    async def _herzschlag(self, ws, takt_s: float) -> None:
        while True:
            await asyncio.sleep(takt_s)
            await ws.send(self.umschlag("herzschlag", {}))
```

Die geplante Bibliothek bietet dasselbe als `from leitstelle_client import Leitstelle` mit identischen
Namen; der Umstieg ist ein Import.

### 3.5 TypeScript ohne Bibliothek (Svelte oder Node)

```ts
type Umschlag = { protokoll: "leitstelle/1"; art: string; id: string; zeit: string; von: string; an: string; bezug: string | null; nutzlast: Record<string, unknown> };

export class Leitstelle {
  verbunden = $state(false);           // in Svelte 5; sonst ein gewöhnliches Feld
  private handler = new Map<string, Array<(n: Record<string, unknown>) => void>>();
  private ws?: WebSocket;
  constructor(private adresse: string, private schluessel: string, private name: string, private faehigkeiten: string[]) {}

  signal(art: string, f: (n: Record<string, unknown>) => void) { const l = this.handler.get(`signal.${art}`) ?? []; l.push(f); this.handler.set(`signal.${art}`, l); }

  starten(pause = 1000) {
    const ws = new WebSocket(`${this.adresse.replace(/^http/, "ws")}/api/kanal?schluessel=${encodeURIComponent(this.schluessel)}`);
    this.ws = ws;
    ws.onopen = () => { pause = 1000; ws.send(this.umschlag("anwendung.anmelden", { name: this.name, version: "1.0", bibliothek: "eigen 0.1", faehigkeiten: this.faehigkeiten, signale: true })); };
    ws.onmessage = (e) => {
      const n = JSON.parse(e.data) as Umschlag;
      if (n.art === "anwendung.angemeldet") { this.verbunden = true; this.herzschlag(n.nutzlast.herzschlag_s as number); }
      for (const f of this.handler.get(n.art) ?? []) f(n.nutzlast);
    };
    ws.onclose = () => { this.verbunden = false; setTimeout(() => this.starten(Math.min(pause * 2, 30000)), pause); };
  }
  private herzschlag(takt_s: number) { const t = setInterval(() => { if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(this.umschlag("herzschlag", {})); else clearInterval(t); }, takt_s * 1000); }
  private umschlag(art: string, nutzlast: Record<string, unknown>, bezug: string | null = null): string {
    return JSON.stringify({ protokoll: "leitstelle/1", art, id: crypto.randomUUID(), zeit: new Date().toISOString(), von: this.name.toLowerCase(), an: "leitstelle", bezug, nutzlast } satisfies Umschlag);
  }
}
```

Im Browser kann kein eigener Kopf gesetzt werden, deshalb nimmt der Kanal den Schlüssel auch als
Abfrageparameter an. Das ist nur im Heimnetz und über `wss://` erlaubt.

### 3.6 Abnahme Stufe 2

1. Die Anwendung erscheint unter Anwendungen als verbunden, mit Bibliothek und Fassung.
2. Leitstelle neu starten: die Anwendung verbindet sich selbst neu, zeigt zwischendurch "ohne Leitstelle".
3. Ketten und Rechte kommen aus der Leitstelle; ein Wechsel dort wirkt ohne Neustart der Anwendung
   (nächste Anmeldung oder `signal.*`).

## 4. Stufe 3: Signale verarbeiten

Pflichtreaktionen. Eine Anwendung, die ein Signal bekommt und nichts tut, läuft blind in Fehler. Deshalb
meldet die Anwendung in `anwendung.anmelden` nur dann `signale: true`, wenn alle Zeilen umgesetzt sind.

| Signal | Nutzlast | Pflichtreaktion |
|---|---|---|
| `signal.speicher` mit `zustand: knapp` | `knoten`, `frei_gb`, `voraussichtlich_frei_in_s` | Stapelarbeit (Masseneinbettung, Nachvertonung, Vorberechnung) drosseln: nichts Neues einreihen, Laufendes beenden |
| `signal.speicher` mit `zustand: voll` | dito, `betroffene_auftraege` | Stapelarbeit anhalten; wartende eigene Aufträge in der Oberfläche als wartend zeigen |
| `signal.speicher` mit `zustand: frei` | | Stapelarbeit wieder aufnehmen |
| `signal.lage` | `lage`, `begruendung` | angespannt: drosseln wie bei knapp; engpass: anhalten wie bei voll; ruhig: aufnehmen. Begründung in der Oberfläche zeigen |
| `signal.pausiert` | `was`, `grund` | nichts Neues senden; Oberfläche zeigt "pausiert durch Leitstelle: <grund>" |
| `signal.fortgesetzt` | | weitermachen |
| `signal.gesperrt` | `was`, `grund`, `bis` | nichts Neues für `was` senden (Anwendung, Fähigkeit oder Zone); dem Menschen zeigen, nie still weiterlaufen; kein Wiederholen in Schleife |
| `signal.freigegeben` | | Sperre aufheben |
| `signal.modell` mit `zustand: bereit` | `modell`, `knoten` | wartende Arbeit darf starten |
| `signal.modell` mit `zustand: wird_geladen` | `dauer_s` | Fortschritt "Modell wird geladen, etwa n Sekunden" zeigen |
| `signal.modell` mit `zustand: nicht_verfuegbar` | | andere Kette wählen oder Hinweis zeigen |
| `signal.dienst`, `signal.zone` | | Hinweis zeigen; bei Zonenwechsel auf extern nichts Vertrauliches mehr senden |
| `signal.kosten` | `anteil_prozent` | Hinweis zeigen; die Leitstelle sperrt selbst bei 100 Prozent |

Grundsätze:

1. Jedes Signal ist in der Oberfläche der Anwendung sichtbar (Leiste, nicht Dialog), mit der
   Begründung der Leitstelle im Wortlaut.
2. Teilergebnisse annehmen: `auftrag.abgebrochen` bringt `teilergebnis`; es wird gezeigt, mit Hinweis,
   nie verworfen.
3. Keine eigenen Zeitgrenzen für Arbeit. Abbrechen ist Sache des Menschen oder der Leitstelle.
4. Keine Schleifen: eine abgelehnte oder gesperrte Anfrage wird nicht automatisch wiederholt. Wiederholen
   darf nur, was die Leitstelle als `wiederholbar` kennzeichnet, und das höchstens einmal.
5. Die bisherige Eigenlogik für dieselben Zwecke (Vorfahrt-Dateien, Zeitgrenzen-Regeln,
   Speicherprüfungen) wird entfernt.

Beispiel Fundus:

```python
ls = Leitstelle(einst.leitstelle_adresse, einst.leitstelle_schluessel, "Fundus", ["text", "einbettung", "werkzeug"])

@ls.signal("speicher")
async def speicher(n):
    einbettung.drossel(an=n["zustand"] != "frei")

@ls.signal("lage")
async def lage(n):
    einbettung.anhalten() if n["lage"] == "engpass" else einbettung.drossel(an=n["lage"] == "angespannt")
    leiste.zeigen(f"Leitstelle: Lage {n['lage']}, {n['begruendung']}")

@ls.signal("gesperrt")
async def gesperrt(n):
    einbettung.anhalten()
    leiste.zeigen(f"Leitstelle hat {n['was']} gesperrt: {n['grund']}", dauerhaft=True)
```

### Abnahme Stufe 3

Mit dem Schein-Verbund (`backend/leitstelle/simulation`) lassen sich alle Signale erzeugen, ohne echte
Modelle: Lage angespannt (ein Auftrag wartet auf Speicher), Engpass (zwei), Sperre, Pause, Hauptregler.
Je Signal eine Prüfung: Signal senden, Reaktion in der Anwendung beobachten, Hinweis in der Oberfläche
sichtbar. Alle Zeilen der Tabelle oben müssen grün sein, bevor `signale: true` gesetzt wird.

## 5. Stufe 4: Eigene Aufträge über das Protokoll

Für lange Arbeiten, die anhaltbar, abschnittsweise oder in Stapeln laufen (Masseneinbettung,
Nachvertonung, Tiefenrecherche, Bildserien).

1. Vor einem Stapel `frage.kapazitaet` stellen (`faehigkeit`, `modell`, `umfang`); bei `jetzt: false`
   den Stapel erst zu `voraussichtlich_in_s` beginnen und das dem Menschen zeigen.
2. Für den Stapel `reservierung.anfragen`; nur mit `reservierung.bestaetigt` loslegen. Die Leitstelle
   hält das Modell geladen. `reservierung.entzogen` heißt: laufenden Abschnitt beenden, nächsten nicht
   beginnen, Grund zeigen.
3. Jeden Auftrag mit `auftrag.anlegen` abgeben: `faehigkeit`, `titel` (für Menschen), `eingabe`,
   `anhaltbar: true`, wenn Abschnitte vorhanden sind, `prioritaet` nur, wenn sie von der Vorgabe abweichen
   soll (die Leitstelle darf sie absenken).
4. `auftrag.angenommen`, `auftrag.laeuft`, `auftrag.fortschritt`, `auftrag.stueck`, `auftrag.ergebnis`,
   `auftrag.fehler`, `auftrag.abgebrochen`, `auftrag.pausiert`, `auftrag.fortgesetzt` verarbeiten und
   als Zustand in der eigenen Oberfläche zeigen; `begruendung` und `voraussichtlich_start_s` anzeigen.
5. Nach `auftrag.ergebnis` die `messung` (Dauer, erstes Stück, Token, Modell, Knoten) speichern, wenn
   die Anwendung eine Werkbank oder Statistik hat; nicht selbst messen.
6. Abschnitte: ein anhaltbarer Auftrag meldet in `eingabe.abschnitte` die Einheiten; die Leitstelle hält
   zwischen Abschnitten an, nie mitten im Abschnitt. Die Anwendung setzt beim Fortsetzen beim nächsten
   Abschnitt an.

```python
antwort = await ls.auftrag("hoeren", titel="Folge 12 transkribieren", eingabe={"datei": pfad, "sprache": "de"},
                           anhaltbar=True, prioritaet="hintergrund")
async for ereignis in antwort.ereignisse():          # fortschritt, stueck, pausiert, fortgesetzt, ergebnis, fehler, abgebrochen
    oberflaeche.zeigen(ereignis)
```

Abnahme Stufe 4: ein Stapel von 20 Abschnitten; während des Laufs in der Leitstelle anhalten,
fortsetzen, Hauptregler auf Auslaufen und auf Halt stellen. Erwartung: Anhalten wirkt zwischen zwei
Abschnitten, Auslaufen lässt den laufenden Abschnitt fertig und sperrt danach (`signal.gesperrt`), Halt
bricht ab und liefert `teilergebnis` mit den fertigen Abschnitten. Die Anwendung zeigt jeden Zustand.

## 6. Dienste anbinden (Anbieter)

Minimal-invasiv: der Mensch gibt in der Leitstelle unter Dienste, Anschluss hinzufügen nur Art, Adresse
und, falls nötig, einen Zugang (Token) an. Alles Weitere (Modelle, Fähigkeiten, Ladezustand, Plätze)
erkennt der Adapter.

| Art | Adapter in der Leitstelle | Was der Dienst selbst tun muss |
|---|---|---|
| Modell-Läufer mit OpenAI-Form und nativer Zustandsschnittstelle | `openai_kompatibel` (Zustand, Laden, Entladen über die native Schnittstelle des Läufers) | nichts; läuft wie bisher |
| Externer Anbieter mit OpenAI-Form | `extern_openai` (nur `/v1/models`, nie Laden; Namen mit gleichem `root` sind ein Modell; Grenze je Minute und Abgleichabstand je Dienst einstellbar, Vorgabe 900 s) | nichts; Schlüssel liegt nur in der Leitstelle (verschlüsselt, mit Auge) |
| Eigener Sprach-Worker (Stimme, Stimme klonen, Hören) | `sprachdienst` | eigene Modellverwaltung entfernen; eine Sperre für die Grafik bleibt und gilt als ein Platz |
| Eigener Spracherkennungsdienst | `hoeren_http` | `GET /zustand` mit Modell und Speicher anbieten, sonst nichts |
| Bild-Werkbank (Bilderzeugung, Freistellen) | `bildwerkbank` | nichts; Bindung an 127.0.0.1 bleibt, der Knoten-Agent stellt den Weg her |
| Musik-Worker | `musik` | nichts |
| Neue Dienstart | neuer Adapter nach der Schnittstelle unten | `GET /zustand` |

Schnittstelle eines Adapters (`backend/leitstelle/ports/dienst.py`, Staffel 1):

```python
class DienstAdapter(Protocol):
    art: str                                                   # zum Beispiel "hoeren_http"
    async def erkunden(self) -> Dienstbeschreibung: ...        # Fähigkeiten, Modelle, Plätze, Besonderheiten
    async def zustand(self) -> Dienstzustandsbericht: ...      # bereit, rechnet, pausiert, nicht_erreichbar; Modelle mit Ladezustand und GB
    async def laden(self, modell: str) -> None: ...            # darf fehlen, wenn der Dienst nicht laden kann
    async def entladen(self, modell: str) -> None: ...
    def ausfuehren(self, auftrag: Auftrag) -> AsyncIterator[Stueck | Fortschritt | Ergebnis | Fehler]: ...
    async def abbrechen(self, auftrag: str) -> Teilergebnis | None: ...
```

Regeln für Adapter: die Gesundheitsprüfung lädt nie ein Modell; `zustand()` ist billig und läuft im Takt
(abgefragte Dienste nach ihrem Abgleichabstand, nach Fehlschlägen in wachsenden Abständen von 5 s bis höchstens einem
Tag, ab dem fünften Fehlschlag in Folge im Zustand `ausfall`; Dienste mit `meldet_sich_selbst`, etwa der Maschinenraum,
jedes Mal); jede gesendete Anfrage meldet der Adapter über `beim_senden`, damit die Leitstelle Grenzen je Minute einhält;
jede Zeit (Laden, Lauf, erstes Stück) wird gemessen und an das Messwerk gemeldet; Fehler kommen mit dem
Wortlaut des Dienstes und einem Wort als Grund; Teilergebnisse werden gesammelt, damit ein Abbruch sie
liefern kann.

Alternativ meldet sich ein Dienst selbst über den Kanal an (`dienst.anmelden`, `dienst.zustand`,
`dienst.modell`), wenn er ohnehin ein Programm von uns ist; dann braucht er keinen Adapter.

## 7. Knoten anbinden

Ein Befehl pro Rechner (Staffel 2), der den Agenten installiert, einen Schlüssel holt und sich anmeldet.
Der Agent meldet Messwerte im Takt, entdeckt bekannte Dienste an ihren Ports und Prozessen und führt
genau fünf Befehle aus: Dienst starten, anhalten, neu starten, Messtakt ändern, Speicher prüfen. Er lädt
nie selbst Modelle. Auf dem Mac läuft er unter launchd, auf dem Pi und dem Server unter systemd. Eine
Anwendung, die nur lokale Adressen zulässt, bekommt vom Agenten eine lokale Weiterleitung
`127.0.0.1:1234` auf die Leitstelle.

## 8. Was die Leitstelle ihren Teilnehmern zusagt

Darauf dürfen sich Anwendungen und Dienste verlassen; es ist im Kern getestet (SZENARIEN.md).

| Zusage | Bedeutung für den Teilnehmer |
|---|---|
| Nie ein rechnendes oder zugeteiltes Modell entladen | ein laufender Auftrag verliert sein Modell nie unter sich weg |
| Geschützte Modelle (Einbettung, unter 10 Milliarden Parametern, ausdrücklich geschützt) bleiben | Einbettungen sind jederzeit da |
| Entladen nur bei Bedarf: ein wartender Auftrag braucht den Platz, das Modell ist seit der Bedarfsfrist (Vorgabe 60 s) ohne Auftrag und die Mindestverweildauer (Vorgabe 10 min) ist vorbei | kein vorsorgliches Räumen, kein Hin und Her |
| Hintergrund rückt nach spätestens 15 Minuten auf Normal | Stapelarbeit verhungert nicht |
| Höchstens eine Umleitung je Auftrag; Flattern (dieselbe Bewegung zweimal in 10 Minuten) sperrt die Beteiligten 30 Minuten | kein Dauerwechsel |
| Jede Maßnahme nur, wenn der gemessene Gewinn den gemessenen Aufwand um den Faktor (Vorgabe 2) übersteigt | Umschichten lohnt sich für den Auftrag, der wartet |
| Hauptregler vor Regelwerk: Auslaufen lässt fertig rechnen und sendet dann `signal.gesperrt`; Halt bricht ab und liefert Teilergebnisse | vorhersehbares Verhalten bei Eingriff des Menschen |
| Jede Entscheidung trägt eine Begründung in Worten | die Anwendung kann sie dem Menschen zeigen |
| Unbekannte Nachrichten und `x-`-Felder werden ignoriert, nie abgelehnt | ältere und neuere Teilnehmer vertragen sich |

## 9. Anweisung für KI-Agenten (Schritt für Schritt)

Du bindest ein Programm an die Leitstelle an. Arbeite genau so:

1. Erfasse, wie das Programm heute Modelle aufruft: Adressen, Modellnamen, Zeitgrenzen, eigene
   Modellverwaltung, Ausweichlisten. Gibt es dazu eine Bestandsaufnahme, lies sie zuerst.
2. Lege die Zielstufe fest ([UMBAU.md](UMBAU.md)) und was die Leitstelle übernimmt (Rückbau).
3. Bestimme die Rolle (Abschnitt 1) und die Stufe, die jetzt dran ist. Baue nie zwei Stufen in einem
   Schritt.
4. Lege im Projekt des Programms die Datei `docs/LEITSTELLE.md` an (oder ergänze sie): Rolle, Stufe ist,
   Stufe soll, was geändert wurde, was zurückgebaut wurde, offene Punkte. Diese Datei ist die einzige
   Wahrheit über den Stand der Anbindung dieses Programms.
5. Ändere so wenig wie möglich: Adresse und Schlüssel aus der Konfiguration des Programms (Umgebung oder
   Einstellungsdatei, wie das Projekt es sonst hält), keine neuen Konfigurationsarten.
6. Entferne, was die Leitstelle übernimmt (Abschnitt 2.1, Zeilen Zeitgrenzen, Ausweichlisten, eigene
   Modellverwaltung). Abschalten reicht nicht, der Code geht raus. Nenne jede entfernte Datei oder
   Funktion in `docs/LEITSTELLE.md`.
7. Schreibe Tests gegen eine Attrappe, nie gegen die echte Leitstelle oder einen echten Läufer: für
   Stufe 1 einen Schein-Server mit den Antworten aus Abschnitt 2.2 (auch 429, 503, Abbruch mit
   Teiltext); für Stufe 2 und 3 einen Schein-Kanal, der `anwendung.angemeldet` und jedes Signal aus der
   Tabelle in Abschnitt 4 sendet. Jede Zeile der Pflichtreaktionen ist ein Test.
8. Führe die Abnahme der Stufe durch (Abschnitte 2.3, 3.6, 4, 5) und trage das Ergebnis in
   `docs/LEITSTELLE.md` ein. Was nicht grün ist, bleibt als offener Punkt stehen; nichts wird als fertig
   gemeldet, was nicht geprüft ist.
9. Commit je Stufe, Versionsregel des Projekts beachten. Keine Hinweise auf Werkzeuge oder Hersteller in
   Commits, Code oder Texten. Deutsche Texte mit Umlauten, gerade Anführungszeichen, einfacher
   Bindestrich.
10. Melde zurück: Programm, Rolle, Stufe, geänderte Dateien, entfernte Teile, Testlauf (Zahl grün und
    rot), offene Punkte. Keine Schätzungen über Dinge, die nicht geprüft wurden.

Was du nie tust: eigene Zeitgrenzen für Arbeit einbauen; eine abgelehnte Anfrage in Schleife
wiederholen; Modelle aus der Anwendung heraus laden oder entladen; einen Schlüssel in den Code
schreiben; `signale: true` melden, ohne alle Pflichtreaktionen umgesetzt zu haben.
