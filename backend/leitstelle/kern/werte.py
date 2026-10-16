"""Wertelisten des Kerns. Gespeichert und gesprochen werden die Schlüssel, gezeigt wird das Wort."""

from __future__ import annotations

from enum import Enum, IntEnum


class Faehigkeit(str, Enum):
    TEXT = "text"
    EINBETTUNG = "einbettung"
    UEBERSETZEN = "uebersetzen"
    HOEREN = "hoeren"
    BILD_BESCHREIBEN = "bild_beschreiben"
    BILD_ERZEUGEN = "bild_erzeugen"
    STIMME = "stimme"
    MUSIK = "musik"
    WERKZEUG = "werkzeug"


class Prioritaet(IntEnum):
    HINTERGRUND = 0
    NORMAL = 1
    HOCH = 2
    DRINGEND = 3


class Zone(str, Enum):
    HEIM = "heim"
    FERN = "fern"
    EXTERN = "extern"


class Auftragszustand(str, Enum):
    EINGEREIHT = "eingereiht"
    WARTET_SPEICHER = "wartet_speicher"
    ZUGETEILT = "zugeteilt"
    LAEUFT = "laeuft"
    PAUSIERT = "pausiert"
    FERTIG = "fertig"
    ABGEBROCHEN = "abgebrochen"
    FEHLGESCHLAGEN = "fehlgeschlagen"
    ABGELEHNT = "abgelehnt"


OFFENE_ZUSTAENDE = frozenset({Auftragszustand.EINGEREIHT, Auftragszustand.WARTET_SPEICHER, Auftragszustand.ZUGETEILT, Auftragszustand.LAEUFT, Auftragszustand.PAUSIERT})
WARTENDE_ZUSTAENDE = frozenset({Auftragszustand.EINGEREIHT, Auftragszustand.WARTET_SPEICHER})


class Modellzustand(str, Enum):
    FREI = "frei"          # heruntergeladen, nicht im Speicher
    LAEDT = "laedt"
    GELADEN = "geladen"
    RECHNET = "rechnet"


IM_SPEICHER = frozenset({Modellzustand.LAEDT, Modellzustand.GELADEN, Modellzustand.RECHNET})


class Dienstzustand(str, Enum):
    BEREIT = "bereit"
    AUS = "aus"                       # installiert, läuft nicht
    STARTET = "startet"
    PAUSIERT = "pausiert"
    NICHT_ERREICHBAR = "nicht_erreichbar"


class Betriebsmodus(str, Enum):
    NORMAL = "normal"
    AUSLAUFEN = "auslaufen"
    HALT = "halt"


class Lage(str, Enum):
    RUHIG = "ruhig"
    ANGESPANNT = "angespannt"
    ENGPASS = "engpass"


class Massnahmenart(str, Enum):
    UMLEITEN = "umleiten"
    LEERLAUF_RAEUMEN = "leerlauf_raeumen"
    VORWAERMEN = "vorwaermen"
    KETTE_AUSWEICHEN = "kette_ausweichen"
    EXTERN_AUSWEICHEN = "extern_ausweichen"
    UMVERTEILEN = "umverteilen"
    VERLAGERN = "verlagern"
    DOPPEL_AUFLOESEN = "doppel_aufloesen"
    HINTERGRUND_LAGE = "hintergrund_lage"


class Massnahmenzustand(str, Enum):
    GEPLANT = "geplant"
    AUSGEFUEHRT = "ausgefuehrt"
    GEPRUEFT_OHNE_AKTION = "geprueft_ohne_aktion"
    NICHT_AUSGELOEST = "nicht_ausgeloest"
    RUECKGAENGIG = "rueckgaengig"
    GESPERRT = "gesperrt"


class Automatik(str, Enum):
    AUS = "aus"
    VORSCHLAGEN = "vorschlagen"
    SELBST = "selbst"


WORT: dict[str, str] = {
    "text": "Text", "einbettung": "Einbettung", "uebersetzen": "Übersetzen", "hoeren": "Hören",
    "bild_beschreiben": "Bild beschreiben", "bild_erzeugen": "Bild erzeugen", "stimme": "Stimme", "musik": "Musik", "werkzeug": "Werkzeuge",
    "eingereiht": "Eingereiht", "wartet_speicher": "Wartet auf Speicher", "zugeteilt": "Zugeteilt", "laeuft": "Läuft", "pausiert": "Pausiert",
    "fertig": "Fertig", "abgebrochen": "Abgebrochen", "fehlgeschlagen": "Fehlgeschlagen", "abgelehnt": "Abgelehnt",
    "umleiten": "Umleiten", "leerlauf_raeumen": "Leerlauf räumen", "vorwaermen": "Vorwärmen", "kette_ausweichen": "Kette ausweichen",
    "extern_ausweichen": "Extern ausweichen", "umverteilen": "Umverteilen", "verlagern": "Verlagern", "doppel_aufloesen": "Doppel auflösen",
    "hintergrund_lage": "Hintergrund bei Lage",
}
