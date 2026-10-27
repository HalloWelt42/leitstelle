"""Regelwerk lesen und von Hand ändern: Maßnahmen ein- und ausschalten, Regelwerte in ihren Grenzen einstellen.

Die Bedeutung jedes Werts (Wort, Erklärung, Einheit, Gruppe, Grenzen) steht im Kern (`kern/regelwerk.py`); hier wird sie für
Oberfläche und Schnittstelle zusammengestellt, eine Änderung geprüft, gespeichert (nur Abweichungen von der Vorgabe), mit
wer, was, alt und neu ins Prüfprotokoll geschrieben und sofort wirksam. Was eine Regel als Zustand hinterlässt, nimmt die
Leitstelle zurück, sobald sie nicht mehr wirkt.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from ..kern.regelwerk import AUTOMATIK_WORT, GRUPPEN, SZENARIEN, Einheit, Regelgruppe, Regelwerk, einstellbar, regelwert
from ..kern.umschichter import zuruecknehmen
from ..kern.werte import WORT, Automatik, Massnahmenart
from ..ports.ablage.eintraege import PruefEintrag
from .betrieb import Betrieb
from .fehler import Ablehnung

Wert = bool | int | float | str


class Wahl(BaseModel):
    wert: str
    wort: str


class RegelwertSicht(BaseModel):
    feld: str
    titel: str
    erklaerung: str
    einheit: Einheit
    wert: Wert
    vorgabe: Wert
    min: float | None
    max: float | None
    schritt: float | None
    wahl: list[Wahl]                   # bei Einheit wahl: die möglichen Werte mit Wort
    szenario: Massnahmenart | None     # gehört zu dieser Maßnahme; None: gilt für mehrere


class SzenarioSicht(BaseModel):
    art: Massnahmenart
    titel: str
    erklaerung: str
    an: bool
    vorgabe: bool


class RegelgruppeSicht(BaseModel):
    gruppe: Regelgruppe
    titel: str
    erklaerung: str
    szenarien: list[SzenarioSicht]
    werte: list[RegelwertSicht]


class RegelwerkSicht(BaseModel):
    """Alle Gruppen mit ihren Maßnahmen und Werten, je mit Vorgabe ab Werk und Grenzen für Änderungen von Hand."""

    gruppen: list[RegelgruppeSicht]


class RegelwerkAenderung(BaseModel):
    """Von Hand: einzelne Werte und Schalter; was fehlt, bleibt."""

    werte: dict[str, Wert] = Field(default_factory=dict)
    szenarien_an: dict[Massnahmenart, bool] = Field(default_factory=dict)


def sicht(r: Regelwerk) -> RegelwerkSicht:
    vorgabe = Regelwerk()
    gruppen = []
    for g, beschreibung in GRUPPEN.items():
        szenarien = [SzenarioSicht(art=a, titel=WORT[a.value], erklaerung=s.erklaerung, an=r.szenarien_an[a], vorgabe=vorgabe.szenarien_an[a])
                     for a, s in SZENARIEN.items() if s.gruppe == g]
        werte = []
        for feld in einstellbar():
            rw = regelwert(feld)
            if rw.gruppe != g:
                continue
            werte.append(RegelwertSicht(feld=feld, titel=rw.titel, erklaerung=rw.erklaerung, einheit=rw.einheit, wert=_json(getattr(r, feld)),
                                        vorgabe=_json(getattr(vorgabe, feld)), min=rw.min, max=rw.max, schritt=rw.schritt, szenario=rw.szenario,
                                        wahl=[Wahl(wert=a.value, wort=w) for a, w in AUTOMATIK_WORT.items()] if rw.einheit == Einheit.WAHL else []))
        gruppen.append(RegelgruppeSicht(gruppe=g, titel=beschreibung.titel, erklaerung=beschreibung.erklaerung, szenarien=szenarien, werte=werte))
    return RegelwerkSicht(gruppen=gruppen)


def _json(wert: Wert) -> Wert:
    return wert.value if isinstance(wert, Automatik) else wert


def wert_text(feld: str, wert: Wert) -> str:
    """Ein Regelwert für Menschen, mit Einheit: 300 s, 18 GB, 92 %, an."""
    e = regelwert(feld).einheit
    if e == Einheit.SCHALTER:
        return "an" if wert else "aus"
    if e == Einheit.WAHL:
        return AUTOMATIK_WORT[Automatik(wert)]
    zahl = float(wert)
    if e == Einheit.SEKUNDEN:
        if zahl >= 3600 and zahl % 3600 == 0:
            return f"{_zahl(zahl / 3600)} h"
        return f"{_zahl(zahl / 60)} min" if zahl >= 120 and zahl % 60 == 0 else f"{_zahl(zahl)} s"
    text = _zahl(zahl)
    return {Einheit.GB: f"{text} GB", Einheit.MILLIARDEN: f"{text} Milliarden", Einheit.PROZENT: f"{text} %", Einheit.PUNKTE: f"{text} Punkte",
            Einheit.PROZENT_KERN: f"{text} % eines Kerns", Einheit.ANTEIL: f"{_zahl(round(zahl * 100, 2))} %", Einheit.FAKTOR: f"{text}-fach"}.get(e, text)


def _zahl(x: float) -> str:
    """Deutsch: Punkt für Tausender, Komma für Nachkommastellen, ohne Nullen am Ende (86.400, 1,5, 0,25)."""
    text = f"{x:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return text.rstrip("0").rstrip(",")


def _neu(r: Regelwerk, a: RegelwerkAenderung) -> Regelwerk:
    """Das geänderte Regelwerk, geprüft: nur bekannte Werte, in ihren Grenzen, Anhalten nicht unter Drosseln."""
    felder = set(einstellbar())
    if unbekannt := sorted(set(a.werte) - felder):
        raise Ablehnung("unbekannt", f"Diese Werte gibt es im Regelwerk nicht: {', '.join(unbekannt)}.")
    for feld, wert in a.werte.items():
        rw = regelwert(feld)
        if rw.einheit == Einheit.SCHALTER:
            if not isinstance(wert, bool):
                raise Ablehnung("eingabe", f"{rw.titel} ist an oder aus.")
        elif rw.einheit == Einheit.WAHL:
            if wert not in {x.value for x in Automatik}:
                raise Ablehnung("eingabe", f"{rw.titel} ist einer dieser Werte: {', '.join(AUTOMATIK_WORT.values())}.")
        elif isinstance(wert, bool) or not isinstance(wert, (int, float)):
            raise Ablehnung("eingabe", f"{rw.titel} braucht eine Zahl.")
        elif rw.einheit == Einheit.ANZAHL and wert != int(wert):
            raise Ablehnung("eingabe", f"{rw.titel} braucht eine ganze Zahl.")
        elif (rw.min is not None and wert < rw.min) or (rw.max is not None and wert > rw.max):
            raise Ablehnung("eingabe", f"{rw.titel} geht von {wert_text(feld, rw.min)} bis {wert_text(feld, rw.max)}, nicht {wert_text(feld, wert)}.")
    try:
        neu = Regelwerk.model_validate(r.model_dump() | a.werte | {"szenarien_an": r.szenarien_an | a.szenarien_an})
    except ValidationError as fehler:      # nach den Prüfungen oben nicht zu erwarten; dann mit dem Feld statt englischem Wortlaut
        feld = str(fehler.errors()[0]["loc"][0])
        raise Ablehnung("eingabe", f"{regelwert(feld).titel if feld in einstellbar() else feld} passt so nicht.") from fehler
    if neu.last_anhalten_ab_prozent < neu.last_drosseln_ab_prozent:
        raise Ablehnung("eingabe", f"{regelwert('last_anhalten_ab_prozent').titel} ({wert_text('last_anhalten_ab_prozent', neu.last_anhalten_ab_prozent)}) "
                                   f"liegt unter {regelwert('last_drosseln_ab_prozent').titel} ({wert_text('last_drosseln_ab_prozent', neu.last_drosseln_ab_prozent)}).")
    return neu


async def aendern(b: Betrieb, a: RegelwerkAenderung, wer: str) -> RegelwerkSicht:
    """Prüfen, speichern, ins Prüfprotokoll (je Wert alt und neu), wirksam machen; eine Regel, die nicht mehr wirkt,
    nimmt ihren Zustand zurück (etwa einen gedrosselten Hintergrund)."""
    alt = b.verbund.regelwerk
    neu = _neu(alt, a)
    zeilen = [f"Regelwert {regelwert(f).titel} ({GRUPPEN[regelwert(f).gruppe].titel}): {wert_text(f, getattr(alt, f))} auf {wert_text(f, getattr(neu, f))}"
              for f in einstellbar() if getattr(alt, f) != getattr(neu, f)]
    zeilen += [f"Regel {WORT[x.value]}: {'an' if alt.szenarien_an[x] else 'aus'} auf {'an' if neu.szenarien_an[x] else 'aus'}"
               for x in Massnahmenart if alt.szenarien_an[x] != neu.szenarien_an[x]]
    if not zeilen:
        return sicht(alt)
    await b.ablage.einstellungen.regelwerk_speichern(neu)
    b.verbund.regelwerk = neu
    for z in zeilen:
        await b.ablage.pruefung.anhaengen(PruefEintrag(zeit_s=b.uhr.jetzt(), wer=wer, was=z, gegenstand="Regelwerk"))
        b.melden(z)
    for art in Massnahmenart:
        if alt.wirksam(art) and not neu.wirksam(art):
            for satz in zuruecknehmen(b.verbund, art, b):
                b.melden(satz)
    b.anstossen()
    return sicht(neu)
