"""Grenzen eines Dienstes je Minute (ZUSAMMENSPIEL Z4): Anfragen und Token im gleitenden Fenster von 60 s.

Externe Anbieter begrenzen je Schlüssel, gleitend über 60 s, die Zahl der Anfragen und die Token hinein und heraus (Hetzner
Experimental: 10 Anfragen, 4 Mio. hinein, 100.000 heraus). Jede gesendete Anfrage zählt (der Haken des HTTP-Clients im
Adapter meldet sie mit dem Modell, das sie nennt). Token bucht die Vermittlung: vor dem Senden geschätzt aus der Länge der
Anfrage, nach der Antwort mit dem echten Verbrauch (`usage`). Token hinein zählen ab dem Senden, Token heraus ab dem Ende
der Antwort (bis dahin die Schätzung ab dem Senden). Eine Anfrage, die der Anbieter mit Überlast ablehnt, verbraucht
keine Token; ihre Buchung fällt weg.
"""

from __future__ import annotations

from pydantic import BaseModel

FENSTER_S = 60.0                     # Grenzen gelten je Minute, gleitend


class Gesendet(BaseModel):
    """Eine an den Dienst gesendete Anfrage (Arbeit, Wiederholung, Zustandsabfrage)."""

    zeit_s: float
    familie: str | None = None       # Modell, das sie nennt; None: Zustandsabfrage oder unbekannt


class Tokenbuchung(BaseModel):
    """Token einer Anfrage: vor dem Senden geschätzt, nach der Antwort echt."""

    kennung: str                     # Auftrag (oder Probe), zu dem sie gehört
    familie: str | None = None
    zeit_s: float                    # gesendet: ab hier zählen Token hinein
    ende_s: float                    # ab hier zählen Token heraus (solange offen: der Sendezeitpunkt)
    token_ein: int = 0
    token_aus: int = 0
    offen: bool = True               # noch die Schätzung: die Antwort steht aus


class Bedarf(BaseModel):
    """Was Anfragen von den Grenzen eines Dienstes brauchen."""

    anfragen: int = 0
    token_ein: int = 0
    token_aus: int = 0

    def __add__(self, anderer: Bedarf) -> Bedarf:
        return Bedarf(anfragen=self.anfragen + anderer.anfragen, token_ein=self.token_ein + anderer.token_ein, token_aus=self.token_aus + anderer.token_aus)


class Nutzung(BaseModel):
    """Anfragen und Token im gleitenden Fenster; Token offener Anfragen sind geschätzt."""

    anfragen: int = 0
    token_ein: int = 0
    token_aus: int = 0
    geschaetzt: bool = False         # enthält Schätzungen von Anfragen, deren Antwort aussteht


class Frei(BaseModel):
    """Wann der Dienst die nächste Anfrage mit einem Bedarf annimmt, und welche Grenze bindet."""

    in_s: float = 0.0
    grund: str = ""


def im_fenster(zeit_s: float, jetzt_s: float) -> bool:
    return jetzt_s - zeit_s < FENSTER_S


def aufraeumen(gesendet: list[Gesendet], token: list[Tokenbuchung], jetzt_s: float) -> tuple[list[Gesendet], list[Tokenbuchung]]:
    """Nur behalten, was noch zählt; offene Buchungen bleiben bis zur Antwort (dann zählen ihre Token heraus)."""
    return ([g for g in gesendet if im_fenster(g.zeit_s, jetzt_s)],
            [t for t in token if t.offen or im_fenster(t.zeit_s, jetzt_s) or im_fenster(t.ende_s, jetzt_s)])


def nutzung(gesendet: list[Gesendet], token: list[Tokenbuchung], jetzt_s: float, familie: str | None = None) -> Nutzung:
    """Im Fenster, für den ganzen Dienst oder ein Modell."""
    g = [x for x in gesendet if im_fenster(x.zeit_s, jetzt_s) and (familie is None or x.familie == familie)]
    t = [x for x in token if familie is None or x.familie == familie]
    ein = [x for x in t if im_fenster(x.zeit_s, jetzt_s)]
    aus = [x for x in t if im_fenster(x.ende_s, jetzt_s)]
    return Nutzung(anfragen=len(g), token_ein=sum(x.token_ein for x in ein), token_aus=sum(x.token_aus for x in aus),
                   geschaetzt=any(x.offen for x in ein + aus))


def frei_in_s(eintraege: list[tuple[float, int]], dazu: int, grenze: int, jetzt_s: float) -> float:
    """Sekunden, bis im gleitenden Fenster Platz für `dazu` ist (0: jetzt). Ein Bedarf über der Grenze geht, sobald das
    Fenster leer ist (sonst wartete er für immer); der Anbieter sagt dann selbst, was er davon hält."""
    summe = sum(n for _, n in eintraege) + dazu
    if summe <= grenze or not eintraege:
        return 0.0
    for zeit, n in sorted(eintraege):
        summe -= n
        if summe <= grenze:
            return max(0.0, zeit + FENSTER_S - jetzt_s)
    return max(0.0, max(z for z, _ in eintraege) + FENSTER_S - jetzt_s)


def zahl(n: int) -> str:
    """Deutsch mit Tausenderpunkt: 100000 -> '100.000'."""
    return f"{n:,}".replace(",", ".")
