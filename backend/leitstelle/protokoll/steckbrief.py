"""Steckbrief je Modell (PROTOKOLL.md Abschnitt 4.8): wofür ein Modell gemacht ist, was es kann und wie es sich im
Betrieb verhält. Eine App fragt danach, statt Modellnamen zu kennen.

Die Leitstelle setzt ihn aus drei Quellen zusammen und nennt je Angabe die Herkunft: was der Dienst selbst sagt
(`Selbstauskunft`), was von Hand eingetragen ist (geht vor), was sie misst. Abgeleitet heißt: aus anderen Angaben
geschlossen (etwa "lange Texte" aus einem großen Kontext).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from ..kern.text import komma
from ..kern.werte import Eignung, Faehigkeit, Zone


class Quelle(str, Enum):
    DIENST = "dienst"                 # der Dienst sagt es selbst (Modell-Läufer, Dienstdatei des Maschinenraums, Anbieter)
    HAND = "hand"                     # in der Leitstelle eingetragen
    GEMESSEN = "gemessen"             # aus dem Verlauf der Leitstelle
    ABGELEITET = "abgeleitet"         # aus anderen Angaben geschlossen


class Messwerte(BaseModel):
    """Aus den jüngsten fertigen Aufträgen des Modells (Mittelwerte als Median, Ladezeit als gleitender Mittelwert)."""

    auftraege: int = 0                # Grundlage
    rechenzeit_s: float | None = None
    erstes_stueck_s: float | None = None
    token_je_s: float | None = None   # erzeugte Token je Sekunde nach dem ersten Stück
    ladezeit_s: float | None = None


class Faehigkeitsprobe(BaseModel):
    """Eine Fähigkeit, die die Leitstelle mit einer kleinen Aufgabe geprüft hat (von Hand ausgelöst, Quelle gemessen)."""

    faehigkeit: Faehigkeit
    belegt: bool                      # die Probe hat die Fähigkeit gezeigt; falsch: abgelehnt oder falsch beantwortet
    zeit_s: float                     # Zeitpunkt der Probe (Sekunden seit 1970)
    meldung: str = ""                 # was der Dienst antwortete, gekürzt


class Groessenregel(BaseModel):
    """Welche Bildgrößen ein Bildmodell annimmt: Kanten im Raster, je Kante und für die Fläche eine Grenze."""

    raster: int = Field(gt=0)                                # jede Kante ist ein Vielfaches davon
    kante_min: int = Field(gt=0)
    kante_max: int = Field(gt=0)
    pixel_min: int = Field(gt=0)                             # Fläche Breite mal Höhe
    pixel_max: int = Field(gt=0)
    vorgabe: str                                             # "BxH", wenn die Anwendung keine Größe nennt
    empfohlen: list[str] = Field(default_factory=list)       # Größen, in denen das Modell am besten zeichnet

    def pruefen(self, breite: int, hoehe: int) -> str | None:
        """Der Grund in einem Satz, wenn das Modell die Größe nicht annimmt; sonst None."""
        if breite % self.raster or hoehe % self.raster:
            return f"Breite und Höhe müssen durch {self.raster} teilbar sein, nicht {breite}x{hoehe}."
        if not all(self.kante_min <= k <= self.kante_max for k in (breite, hoehe)):
            return f"Jede Kante {self.kante_min} bis {self.kante_max} Pixel, nicht {breite}x{hoehe}."
        if not self.pixel_min <= breite * hoehe <= self.pixel_max:
            return (f"Die Fläche muss zwischen {self.pixel_min} und {self.pixel_max} Pixeln liegen; {breite}x{hoehe} hat "
                    f"{breite * hoehe}.")
        return None


class Schrittregel(BaseModel):
    """Wie viele Schritte ein Bildmodell rechnen kann und wie viele es ohne Angabe rechnet."""

    vorgabe: int = Field(gt=0)
    kleinste: int = Field(gt=0)
    groesste: int = Field(gt=0)

    def pruefen(self, schritte: int) -> str | None:
        if not self.kleinste <= schritte <= self.groesste:
            return f"Schritte {self.kleinste} bis {self.groesste}, nicht {schritte}."
        return None


#: Grenzen für Bilddienste, die keine eigenen nennen (oder deren Steckbrief die Leitstelle noch nicht gelesen hat)
GROESSEN_VORGABE = Groessenregel(raster=16, kante_min=256, kante_max=2048, pixel_min=256 * 256, pixel_max=2048 * 2048, vorgabe="1024x1024",
                                 empfohlen=["1024x1024", "1344x768", "768x1344"])
ANZAHL_MAX = 4                                               # Bilder je Anfrage, wenn das Modell nichts anderes sagt


#: größtes Bild eines Beispiels (data-URL); die Bilddienste liefern rund 20 bis 30 KB je Bild
BEISPIEL_BILD_MAX = 200_000


class Aufgabenbeispiel(BaseModel):
    """Was ein Bildmodell an einem festen Motiv macht (Portfolio des Bildwerks, ATL-45 des Ateliers): Vorher und Nachher als
    kleine Bilder (data-URL), dazu die Dauer im Dienst beim Rechnen. Zum Vergleichen der Modelle; die Leitstelle reicht
    es nur weiter (LS-25)."""

    motiv: str = Field(default="", max_length=200)
    ausgang: str | None = Field(default=None, pattern=r"^data:image/", max_length=BEISPIEL_BILD_MAX)   # vor der Markierung, wo es sich unterscheidet
    vorher: str = Field(pattern=r"^data:image/", max_length=BEISPIEL_BILD_MAX)
    nachher: str = Field(pattern=r"^data:image/", max_length=BEISPIEL_BILD_MAX)
    dauer_s: float | None = Field(default=None, ge=0)


class Aufgabenvorlage(BaseModel):
    """Wie ein Bildmodell eine Aufgabe (anweisen, entfernen, fuellen, erweitern) als Anweisung bekommt, wie sein Dienst
    es sagt: fester Text mit dem Platzhalter `{wunsch}` für die Worte des Nutzers, die Sprache, in die der Wunsch
    übersetzt wird, und die Signalfarbe der markierten Fläche. Die Leitstelle reicht das nur weiter; zusammensetzen tut
    die Anwendung."""

    anweisung: str = Field(min_length=1)                     # mit {wunsch}, wenn die Aufgabe einen Wunsch aufnimmt
    ohne_wunsch: str | None = None                           # bei leerem Wunsch; fehlt sie, braucht die Aufgabe einen Wunsch
    sprache: str = Field(pattern=r"^[a-z]{2}$")              # ISO 639-1
    signalfarbe: tuple[int, int, int] | None = None          # RGB der markierten Fläche; ohne: die Aufgabe markiert nichts
    beispiel: Aufgabenbeispiel | None = None                 # Vorher und Nachher an einem Motiv, zum Vergleichen (LS-25)


class Bildsteckbrief(BaseModel):
    """Was ein Bildmodell annimmt, wie sein Dienst es selbst sagt (übliches Bildformat: `GET /v1/models`, Feld `steckbrief`
    des Modelleintrags). Die Leitstelle liest ihn nach jedem Start des Dienstes, hält ihn über Neustarts und prüft damit
    Anfragen, bevor sie den Dienst erreichen."""

    modell: str                                              # Kennung des Modells beim Dienst (als `model` gleichwertig zur Kennung des Dienstes)
    name: str                                                # Anzeigename des Modells
    aliase: list[str] = Field(default_factory=list)          # weitere Namen, die als `model` dasselbe meinen
    kann_bearbeiten: bool = False                            # nimmt Bildvorlagen an (`/v1/images/edits`)
    vorlagen_max: int | None = Field(default=None, ge=0)     # Bildvorlagen je Anfrage, wenn es bearbeiten kann
    vorlagen_min: int = Field(default=0, ge=0)               # Bildvorlagen, die es mindestens braucht; über 0: rechnet nur mit Vorlage
    groessen: Groessenregel | None = None                    # None: es gelten die Vorgabegrenzen der Fassade
    schritte: Schrittregel | None = None                     # None: der Dienst nennt keine; Schritte gehen ungeprüft an ihn
    anzahl_max: int | None = Field(default=None, gt=0)       # Bilder je Anfrage
    beschreibung_max_token: int | None = None                # längste Beschreibung, die das Modell liest
    textkodierer: str | None = None
    lizenz: str | None = None
    lizenz_hinweis: str | None = None                        # was die Lizenz für die Nutzung der Bilder heißt, in einem Satz
    parameter_mrd: float | None = None                       # Parameter des Bildteils
    quantisierung: str | None = None
    aufgaben: dict[str, Aufgabenvorlage] = Field(default_factory=dict)   # je Aufgabe die Anweisungsvorlage des Modells (Bildwerk)
    abgerufen_s: float = 0.0                               # wann die Leitstelle ihn zuletzt beim Dienst gelesen hat

    def namen(self) -> set[str]:
        """Alle Namen, unter denen eine Anwendung das Modell verlangen kann (klein geschrieben)."""
        return {n.lower() for n in (self.modell, self.name, *self.aliase) if n}

    def kurz(self) -> str:
        """In einer Zeile für den Verlauf: Modell, Größen, Schritte, Anzahl."""
        teile = [self.name]
        if g := self.groessen:
            teile.append(f"Kanten {g.kante_min} bis {g.kante_max} Pixel durch {g.raster} teilbar, Fläche {komma(g.pixel_min / 1e6, 2)} bis "
                         f"{komma(g.pixel_max / 1e6, 2)} Megapixel, Vorgabe {g.vorgabe}")
        if s := self.schritte:
            teile.append(f"Schritte {s.kleinste} bis {s.groesste}, Vorgabe {s.vorgabe}")
        if self.anzahl_max:
            teile.append(f"bis {self.anzahl_max} Bilder je Anfrage")
        if self.kann_bearbeiten:
            teile.append(f"bis {self.vorlagen_max or ANZAHL_MAX} Bildvorlagen")
        if self.vorlagen_min:
            teile.append(f"nur mit mindestens {self.vorlagen_min} Bildvorlage")
        return "; ".join(teile)


class Steckbrief(BaseModel):
    zweck: str = ""                                          # ein Satz: wofür gemacht oder optimiert
    eignung: list[Eignung] = Field(default_factory=list)
    sprachen: list[str] = Field(default_factory=list)        # ISO 639-1; leer: nicht angegeben
    faehigkeiten: list[Faehigkeit] = Field(default_factory=list)
    kontext: int | None = None                               # Token
    parameter_mrd: float | None = None                       # gesamt
    parameter_aktiv_mrd: float | None = None                 # je Schritt aktiv: bei Mischmodellen weniger (A3B: 3), sonst gleich gesamt
    quantisierung: str | None = None
    zone: Zone = Zone.HEIM                                   # wo gerechnet wird; extern heißt: Daten verlassen das Heimnetz
    anfragen_je_minute: int | None = None                    # Grenzen des Anbieters je Minute (gleitend, je Schlüssel)
    token_ein_je_minute: int | None = None
    token_aus_je_minute: int | None = None
    geprueft: list[Faehigkeitsprobe] = Field(default_factory=list)   # Fähigkeitsproben der Leitstelle (Quelle gemessen)
    bild: Bildsteckbrief | None = None                       # Bildmodelle im üblichen Bildformat: Größen, Schritte, Anzahl, Bearbeiten
    gemessen: Messwerte = Field(default_factory=Messwerte)
    herkunft: dict[str, Quelle] = Field(default_factory=dict)   # je Angabe, woher sie stammt
