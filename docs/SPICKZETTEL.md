# Spickzettel Leitstelle

In den Beispielen heißt der Rechner der Leitstelle `leitstelle`; dort die eigene Adresse einsetzen.

## Adressen

| Was | Wo |
|---|---|
| Oberfläche und Verwaltung | `http://leitstelle:8530/` (nur aus privaten Netzen und VPN) |
| Fassade für Anwendungen | `http://leitstelle:8530/v1` mit `Authorization: Bearer <Schlüssel>` |
| Gesundheit | `http://leitstelle:8530/gesundheit` |
| Entwürfe | `http://leitstelle:8535/mockups/index.html` |
| Telefon | dieselbe Adresse; schmale Bildschirme bekommen die eigene Ansicht `/mobil` |

## Starten

```bash
docker compose up -d --build
```

```bash
docker compose ps
```

```bash
docker logs -f leitstelle
```

Daten: Ordner aus `LEITSTELLE_DATENORDNER` (Vorgabe `./daten`): SQLite `leitstelle.sqlite` im WAL-Modus und
`tresor.schluessel`. Ohne den Tresorschlüssel sind gespeicherte Schlüssel und Zugänge nicht lesbar; eine
Sicherung braucht beides.

## Sichern

```bash
docker compose stop leitstelle && tar -czf leitstelle_$(date +%Y%m%d_%H%M).tar.gz daten && docker compose start leitstelle
```

## Ausrollen auf einen anderen Rechner

```bash
tools/ausrollen.sh                        # Ziel des Hauses aus handbuch ziel leitstelle
ZIEL=benutzer@rechner tools/ausrollen.sh  # ein anderer Rechner
```

## Maschinenraum (Knoten-Agent je Rechner)

Der Maschinenraum ist ein eigenes Programm (Repo HalloWelt42/maschinenraum): er verwaltet die Dienste eines
Rechners mit eigener Oberfläche und meldet sich als Knoten-Agent bei der Leitstelle. Installieren auf dem Rechner:

```bash
git clone https://github.com/HalloWelt42/maschinenraum.git && cd maschinenraum && ./installieren.sh
```

Dann in der Leitstelle unter Knoten beim Rechner "Maschinenraum verbinden" und Adresse und Schlüssel in der
Oberfläche des Maschinenraums (`http://127.0.0.1:8540/`) unter Leitstelle eintragen. Dienste je Rechner liegen in
`~/Maschinenraum/dienste/`, eine Datei je Dienst.

## Erste Schritte in der Oberfläche

1. **Anschluss hinzufügen** (Dienste): Adresse des Modell-Läufers, zum Beispiel `192.168.1.20:1234`, Erkennen.
   Bei neuem Rechner Name und Speicher in GB angeben. Die Leitstelle liest Modelle, Größen und Ladezustand selbst.
2. **Anwendung anlegen** (Anwendungen): Name, Priorität, Fähigkeiten, Zonen, Ketten. Der Schlüssel erscheint
   einmal; später unter dem Auge (steht im Prüfprotokoll).
3. In der Anwendung Basisadresse und Schlüssel eintragen (siehe [ANBINDUNG.md](ANBINDUNG.md) Abschnitt 2).
4. Hauptregler oben: Normal, Auslaufen, Halt, Hintergrund.
5. **Externer Anbieter** (Dienste): Grenzen je Minute (Anfragen, Token hinein und heraus) beim Anschließen oder
   Bearbeiten eintragen; "Fähigkeiten prüfen" (Kolben) belegt mit je einer Anfrage, ob ein Modell Bilder versteht.
6. **Regeln**: je Maßnahme der Selbststeuerung ein Schalter, darunter ihre Werte mit Einheit, Vorgabe und Grenzen
   (`GET`/`PATCH /api/regelwerk`); gespeichert wird nur, was von der Vorgabe abweicht, jede Änderung steht im
   Prüfprotokoll.

## Lokal entwickeln

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[test]" -e "../agent[test]" && .venv/bin/python -m pytest
```

```bash
cd agent && ../backend/.venv/bin/python -m pytest
```

```bash
cd frontend && npm install && npm run pruefen && npm run build
```

```bash
backend/.venv/bin/python tools/schein_laeufer.py --port 8539
```

```bash
cd backend && LEITSTELLE_DATEN=../.run/entwicklung .venv/bin/python -m leitstelle
```

Der Schein-Läufer ahmt einen Modell-Läufer nach (unter Anschluss hinzufügen `127.0.0.1:8539`). Oberfläche mit
Neuladen über `cd frontend && npm run dev` auf 5530. Nach Änderungen an Pydantic-Modellen `npm run typen`; nach
Änderungen an den Stilen der Entwürfe `python3 tools/seitenstile.py`.

## Messen

```bash
backend/.venv/bin/python tools/messen_fassade.py
```

Ergebnisse und Folgerungen stehen in [MESSUNGEN.md](MESSUNGEN.md).
