"""Wertelisten des Kerns. Gespeichert und gesprochen werden die Schlüssel, gezeigt wird das Wort."""

from __future__ import annotations

from enum import Enum, IntEnum


# Speicher in GB meint überall 1024^3 Byte, wie macOS und der Maschinenraum zählen (vorher teils 10^9: 7 % Abweichung)
GIB = 1024**3


class Faehigkeit(str, Enum):
    TEXT = "text"
    EINBETTUNG = "einbettung"
    UEBERSETZEN = "uebersetzen"
    HOEREN = "hoeren"
    BILD_BESCHREIBEN = "bild_beschreiben"
    BILD_ERZEUGEN = "bild_erzeugen"
    STIMME = "stimme"
    STIMME_KLONEN = "stimme_klonen"
    SPRECHER_ERKENNEN = "sprecher_erkennen"
    SPRECHER_TRENNEN = "sprecher_trennen"
    MUSIK = "musik"
    WERKZEUG = "werkzeug"
    TON = "ton"                       # Tonarbeit ohne Modell (wandeln, messen, mischen): rechnet auf dem Mac


class Eignung(str, Enum):
    """Wofür ein Modell oder Dienst besonders taugt, über seine Fähigkeiten hinaus (Selbstauskunft, PROTOKOLL 4.8 der Leitstelle)."""

    DENKEN = "denken"                 # schließt schrittweise; für schwierige Fragen, dauert länger
    PROGRAMMIEREN = "programmieren"
    LANGE_TEXTE = "lange_texte"       # großer Kontext (ab 100 000 Token)
    SCHNELL = "schnell"               # kurze Wartezeit, auch auf Kosten der Tiefe
    GRUENDLICH = "gruendlich"         # beste Ergebnisse, auch auf Kosten der Zeit


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
    WARTET_RUHE = "wartet_ruhe"       # Arbeit "nur bei Ruhe": wartet, bis keine andere Arbeit läuft oder wartet (Regelwerk)
    ZUGETEILT = "zugeteilt"
    LAEUFT = "laeuft"
    PAUSIERT = "pausiert"
    FERTIG = "fertig"
    ABGEBROCHEN = "abgebrochen"
    FEHLGESCHLAGEN = "fehlgeschlagen"
    ABGELEHNT = "abgelehnt"


OFFENE_ZUSTAENDE = frozenset({Auftragszustand.EINGEREIHT, Auftragszustand.WARTET_SPEICHER, Auftragszustand.WARTET_RUHE, Auftragszustand.ZUGETEILT,
                              Auftragszustand.LAEUFT, Auftragszustand.PAUSIERT})
WARTENDE_ZUSTAENDE = frozenset({Auftragszustand.EINGEREIHT, Auftragszustand.WARTET_SPEICHER, Auftragszustand.WARTET_RUHE})


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
    AUSFALL = "ausfall"               # antwortet seit mehreren Prüfungen nicht; geprüft wird in wachsenden Abständen
    SCHLAEFT = "schlaeft"             # sein Rechner schläft: keine Prüfung, kein Fehlschlag, bis er wach ist


class Knotenzustand(str, Enum):
    ERREICHBAR = "erreichbar"         # mindestens ein Dienst antwortet
    NICHT_ERREICHBAR = "nicht_erreichbar"
    SCHLAEFT = "schlaeft"             # hat sich beim Einschlafen abgemeldet; Aufträge warten in den Apps, bis er wach ist


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
    WEITERE_INSTANZ = "weitere_instanz"
    EINBETTUNG_VERSTAERKEN = "einbettung_verstaerken"
    EINBETTUNG_ZURUECKBAUEN = "einbettung_zurueckbauen"
    LAEUFER_OHNE_AUFTRAG = "laeufer_ohne_auftrag"
    HINTERGRUND_RECHNERLAST = "hintergrund_rechnerlast"


#: Szenarien, die ab Werk aus sind (die übrigen sind an); gilt auch für ein gespeichertes Regelwerk, das sie nicht kennt
SZENARIEN_AB_WERK_AUS = frozenset({Massnahmenart.LAEUFER_OHNE_AUFTRAG})


# Rolle eines Prozesses des Modell-Läufers, wie der Maschinenraum sie misst (knoten.last, PROTOKOLL 4.2). Ohne Docstring:
# das Schema muss dem Spiegel im Maschinenraum gleichen (Test test_protokoll_von_agent_und_kern_ist_deckungsgleich).
class Laeuferrolle(str, Enum):
    HAUPT = "haupt"                   # lauscht am Port des Läufers; wird nie beendet
    ARBEITER = "arbeiter"             # hat eine Modelldatei offen oder eine Bibliothek eines Rechenwerks geladen: eine geladene Instanz
    SONSTIG = "sonstig"               # alles andere im Baum des Läufers, etwa das Fenster


class Hintergrundstufe(str, Enum):
    """Was Hintergrundarbeit auf einem Rechner darf, nach der Fremdlast (Regel "Hintergrund bei Rechnerlast")."""

    FREI = "frei"                     # wie immer
    GEDROSSELT = "gedrosselt"         # nur die Grundinstanz einer Familie, keine weitere
    ANGEHALTEN = "angehalten"         # nichts Neues; der Rechner gehört gerade dem Menschen


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
    "bild_beschreiben": "Bild beschreiben", "bild_erzeugen": "Bild erzeugen", "stimme": "Stimme", "stimme_klonen": "Stimmklon", "sprecher_erkennen": "Sprecher erkennen",
    "sprecher_trennen": "Sprecher trennen", "musik": "Musik", "werkzeug": "Werkzeuge", "ton": "Ton bearbeiten",
    "eingereiht": "Eingereiht", "wartet_speicher": "Wartet auf Speicher", "wartet_ruhe": "Wartet auf Ruhe", "zugeteilt": "Zugeteilt", "laeuft": "Läuft", "pausiert": "Pausiert",
    "fertig": "Fertig", "abgebrochen": "Abgebrochen", "fehlgeschlagen": "Fehlgeschlagen", "abgelehnt": "Abgelehnt",
    "umleiten": "Umleiten", "leerlauf_raeumen": "Leerlauf räumen", "vorwaermen": "Vorwärmen", "kette_ausweichen": "Kette ausweichen",
    "extern_ausweichen": "Extern ausweichen", "umverteilen": "Umverteilen", "verlagern": "Verlagern", "doppel_aufloesen": "Doppel auflösen",
    "hintergrund_lage": "Hintergrund bei Lage", "weitere_instanz": "Weitere Instanz",
    "einbettung_verstaerken": "Einbettung verstärken", "einbettung_zurueckbauen": "Einbettung zurückbauen",
    "laeufer_ohne_auftrag": "Läufer ohne Auftrag", "hintergrund_rechnerlast": "Hintergrund bei Rechnerlast",
    "bereit": "Bereit", "aus": "Aus", "startet": "Startet", "nicht_erreichbar": "Nicht erreichbar", "ausfall": "Ausfall", "schlaeft": "Schläft", "erreichbar": "Erreichbar",
    "leerlauf": "nach Leerlauf", "angefordert": "von Hand",
    "denken": "Denkt schrittweise", "programmieren": "Programmieren", "lange_texte": "Lange Texte", "schnell": "Schnell", "gruendlich": "Gründlich",
}
