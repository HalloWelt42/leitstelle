"""Mitgelieferte Regelgraphen (Vorlagen). Der Nutzer kopiert, ändert, schaltet ab.

Jede Vorlage entspricht einem Szenario der Selbststeuerung (ARCHITEKTUR 5.6) und einem
Eintrag im Szenarienkatalog (docs/SZENARIEN.md).
"""

from __future__ import annotations

from ..werte import Massnahmenart
from .auswerter import Kante, Knoten, Regelgraph

K = Knoten
E = Kante


def _graph(kennung: str, name: str, art: Massnahmenart, knoten: list[Knoten], kanten: list[Kante]) -> Regelgraph:
    return Regelgraph(kennung=kennung, name=name, art=art, knoten=knoten, kanten=kanten)


UMLEITEN = _graph("umleiten", "Umleiten bei Speichermangel", Massnahmenart.UMLEITEN, [
    K(id="a", art="ausloeser", baustein="auftrag_wartet_speicher", parameter={"mindestens_s": 5.0}),
    K(id="p1", art="pruefung", baustein="anderer_knoten_mit_platz", parameter={"reserve_gb": 2.0}),
    K(id="p2", art="pruefung", baustein="dienst_dort_laeuft"),
    K(id="p3", art="pruefung", baustein="dienst_installiert"),
    K(id="k1", art="aktion", baustein="dienst_starten"),
    K(id="p4", art="pruefung", baustein="gewinn_gegen_aufwand"),
    K(id="p5", art="pruefung", baustein="gewinn_gegen_aufwand"),
    K(id="k2", art="aktion", baustein="modell_laden"),
    K(id="k3", art="aktion", baustein="auftrag_umleiten"),
    K(id="k4", art="aktion", baustein="melden", parameter={"text": "Umgeleitet nach {knoten}: gespart etwa {gewinn}, Aufwand {aufwand}, Schwelle {faktor} erfüllt"}),
    K(id="e_ok", art="ende", titel="umgeleitet"),
    K(id="e_warten", art="ende", titel="weiter warten"),
    K(id="e_lohnt", art="ende", titel="warten lohnt mehr"),
], [
    E(von="a", nach="p1"), E(von="p1", nach="p2", port="ja"), E(von="p1", nach="e_warten", port="nein"),
    E(von="p2", nach="p4", port="ja"), E(von="p2", nach="p3", port="nein"),
    E(von="p3", nach="p5", port="ja"), E(von="p3", nach="e_warten", port="nein"),
    E(von="p5", nach="k1", port="ja"), E(von="p5", nach="e_lohnt", port="nein"),
    E(von="k1", nach="k2"),
    E(von="p4", nach="k2", port="ja"), E(von="p4", nach="e_lohnt", port="nein"),
    E(von="k2", nach="k3"), E(von="k3", nach="k4"), E(von="k4", nach="e_ok"),
])

LEERLAUF = _graph("leerlauf_raeumen", "Leerlauf räumen", Massnahmenart.LEERLAUF_RAEUMEN, [
    K(id="a", art="ausloeser", baustein="auftrag_wartet_speicher", parameter={"mindestens_s": 5.0}),
    K(id="p1", art="pruefung", baustein="leerlaufmodell_vorhanden"),
    K(id="p2", art="pruefung", baustein="gewinn_gegen_aufwand"),
    K(id="k1", art="aktion", baustein="modell_entladen"),
    K(id="k2", art="aktion", baustein="modell_laden"),
    K(id="k3", art="aktion", baustein="melden", parameter={"text": "Leerlauf geräumt auf {knoten}: {leerlauf}; gespart etwa {gewinn}"}),
    K(id="e_ok", art="ende", titel="geräumt"),
    K(id="e_nein", art="ende", titel="kein Leerlauf, der weichen darf"),
    K(id="e_lohnt", art="ende", titel="warten lohnt mehr"),
], [
    E(von="a", nach="p1"), E(von="p1", nach="p2", port="ja"), E(von="p1", nach="e_nein", port="nein"),
    E(von="p2", nach="k1", port="ja"), E(von="p2", nach="e_lohnt", port="nein"),
    E(von="k1", nach="k2"), E(von="k2", nach="k3"), E(von="k3", nach="e_ok"),
])

VORWAERMEN = _graph("vorwaermen", "Vorwärmen nach Warteschlange", Massnahmenart.VORWAERMEN, [
    K(id="a", art="ausloeser", baustein="auftrag_eingereiht_ohne_modell"),
    K(id="p1", art="pruefung", baustein="platz_ohne_entladen", parameter={"reserve_anteil": 0.05}),
    K(id="k1", art="aktion", baustein="modell_laden"),
    K(id="k2", art="aktion", baustein="melden", parameter={"text": "Vorgewärmt auf {knoten}: {platz}"}),
    K(id="e_ok", art="ende", titel="vorgewärmt"),
    K(id="e_nein", art="ende", titel="kein Platz ohne Entladen"),
], [
    E(von="a", nach="p1"), E(von="p1", nach="k1", port="ja"), E(von="p1", nach="e_nein", port="nein"),
    E(von="k1", nach="k2"), E(von="k2", nach="e_ok"),
])

KETTE = _graph("kette_ausweichen", "Kette ausweichen", Massnahmenart.KETTE_AUSWEICHEN, [
    K(id="a", art="ausloeser", baustein="auftrag_wartet", parameter={"mindestens_s": 5.0}),
    K(id="p1", art="pruefung", baustein="kette_hat_alternative"),
    K(id="p2", art="pruefung", baustein="gewinn_gegen_aufwand", parameter={"faktor": 1.0}),
    K(id="k1", art="aktion", baustein="auftrag_umleiten"),
    K(id="k2", art="aktion", baustein="melden", parameter={"text": "In der Kette ausgewichen auf {alternative}: gespart etwa {gewinn}"}),
    K(id="e_ok", art="ende", titel="ausgewichen"),
    K(id="e_nein", art="ende", titel="keine geladene Alternative"),
    K(id="e_lohnt", art="ende", titel="warten lohnt mehr"),
], [
    E(von="a", nach="p1"), E(von="p1", nach="p2", port="ja"), E(von="p1", nach="e_nein", port="nein"),
    E(von="p2", nach="k1", port="ja"), E(von="p2", nach="e_lohnt", port="nein"),
    E(von="k1", nach="k2"), E(von="k2", nach="e_ok"),
])

EXTERN = _graph("extern_ausweichen", "Extern ausweichen", Massnahmenart.EXTERN_AUSWEICHEN, [
    K(id="a", art="ausloeser", baustein="auftrag_wartet", parameter={"mindestens_s": 5.0}),
    K(id="p1", art="pruefung", baustein="anwendung_darf_extern"),
    K(id="p2", art="pruefung", baustein="wartezeit_ueber_schwelle"),
    K(id="p3", art="pruefung", baustein="extern_dienst_vorhanden"),
    K(id="k1", art="aktion", baustein="auftrag_extern"),
    K(id="k2", art="aktion", baustein="melden", parameter={"text": "Extern ausgewichen: erwartete Wartezeit {wartezeit} über der Schwelle"}),
    K(id="e_ok", art="ende", titel="extern"),
    K(id="e_nicht_erlaubt", art="ende", titel="Anwendung darf nicht extern"),
    K(id="e_unter", art="ende", titel="Wartezeit unter der Schwelle"),
    K(id="e_kein", art="ende", titel="kein externer Dienst"),
], [
    E(von="a", nach="p1"), E(von="p1", nach="p2", port="ja"), E(von="p1", nach="e_nicht_erlaubt", port="nein"),
    E(von="p2", nach="p3", port="ja"), E(von="p2", nach="e_unter", port="nein"),
    E(von="p3", nach="k1", port="ja"), E(von="p3", nach="e_kein", port="nein"),
    E(von="k1", nach="k2"), E(von="k2", nach="e_ok"),
])

UMVERTEILEN = _graph("umverteilen", "Umverteilen bei Ausfall", Massnahmenart.UMVERTEILEN, [
    K(id="a", art="ausloeser", baustein="knoten_ausgefallen"),
    K(id="k1", art="aktion", baustein="laufende_abbrechen_mit_teilergebnis"),
    K(id="k2", art="aktion", baustein="wartende_neu_einreihen"),
    K(id="k3", art="aktion", baustein="melden", parameter={"text": "Knoten nicht erreichbar: laufende Aufträge mit Teilergebnis gemeldet, wartende neu eingereiht"}),
    K(id="e", art="ende", titel="umverteilt"),
], [E(von="a", nach="k1"), E(von="k1", nach="k2"), E(von="k2", nach="k3"), E(von="k3", nach="e")])

VERLAGERN = _graph("verlagern", "Verlagern im Zeitfenster", Massnahmenart.VERLAGERN, [
    K(id="a", art="ausloeser", baustein="zeitfenster_beginnt"),
    K(id="k1", art="aktion", baustein="bevorzugten_knoten_setzen"),
    K(id="k2", art="aktion", baustein="melden", parameter={"text": "Zeitfenster: Hintergrundarbeit bevorzugt auf {knoten}"}),
    K(id="e", art="ende", titel="verlagert"),
], [E(von="a", nach="k1"), E(von="k1", nach="k2"), E(von="k2", nach="e")])

DOPPEL = _graph("doppel_aufloesen", "Doppel auflösen", Massnahmenart.DOPPEL_AUFLOESEN, [
    K(id="a", art="ausloeser", baustein="modell_doppelt_geladen"),
    K(id="p1", art="pruefung", baustein="eine_kopie_ungenutzt"),
    K(id="p2", art="pruefung", baustein="bedarf_anderswo"),
    K(id="k1", art="aktion", baustein="modell_entladen"),
    K(id="k2", art="aktion", baustein="melden", parameter={"text": "Doppel aufgelöst: ungenutzte Kopie entladen, Bedarf von {bedarf}"}),
    K(id="e_ok", art="ende", titel="aufgelöst"),
    K(id="e_nein", art="ende", titel="beide Kopien in Gebrauch oder geschützt"),
    K(id="e_kein_bedarf", art="ende", titel="kein Bedarf, Kopie bleibt"),
], [
    E(von="a", nach="p1"), E(von="p1", nach="p2", port="ja"), E(von="p1", nach="e_nein", port="nein"),
    E(von="p2", nach="k1", port="ja"), E(von="p2", nach="e_kein_bedarf", port="nein"),
    E(von="k1", nach="k2"), E(von="k2", nach="e_ok"),
])

HINTERGRUND = _graph("hintergrund_lage", "Hintergrund bei Lage anhalten", Massnahmenart.HINTERGRUND_LAGE, [
    K(id="a", art="ausloeser", baustein="lage_wechsel"),
    K(id="p1", art="pruefung", baustein="lage_ist", parameter={"lage": "ruhig"}),
    K(id="p2", art="pruefung", baustein="hintergrund_angehalten"),
    K(id="p3", art="pruefung", baustein="hintergrund_angehalten"),
    K(id="k1", art="aktion", baustein="hintergrund_fortsetzen"),
    K(id="k2", art="aktion", baustein="hintergrund_anhalten"),
    K(id="e_fort", art="ende", titel="fortgesetzt"),
    K(id="e_halt", art="ende", titel="angehalten"),
    K(id="e_nichts", art="ende", titel="nichts zu tun"),
], [
    E(von="a", nach="p1"), E(von="p1", nach="p2", port="ja"), E(von="p1", nach="p3", port="nein"),
    E(von="p2", nach="k1", port="ja"), E(von="p2", nach="e_nichts", port="nein"),
    E(von="p3", nach="e_nichts", port="ja"), E(von="p3", nach="k2", port="nein"),
    E(von="k1", nach="e_fort"), E(von="k2", nach="e_halt"),
])

INSTANZ = _graph("weitere_instanz", "Weitere Instanz", Massnahmenart.WEITERE_INSTANZ, [
    K(id="a", art="ausloeser", baustein="auftrag_wartet_auf_platz", parameter={"mindestens_s": 20.0}),
    K(id="p1", art="pruefung", baustein="weitere_instanz_moeglich"),
    K(id="p2", art="pruefung", baustein="gewinn_gegen_aufwand"),
    K(id="k1", art="aktion", baustein="instanz_starten"),
    K(id="k2", art="aktion", baustein="melden", parameter={"text": "Weitere Instanz auf {knoten}: {instanz}; gespart etwa {gewinn}"}),
    K(id="e_ok", art="ende", titel="gestartet"),
    K(id="e_nein", art="ende", titel="keine weitere Instanz möglich"),
    K(id="e_lohnt", art="ende", titel="warten lohnt mehr"),
], [
    E(von="a", nach="p1"), E(von="p1", nach="p2", port="ja"), E(von="p1", nach="e_nein", port="nein"),
    E(von="p2", nach="k1", port="ja"), E(von="p2", nach="e_lohnt", port="nein"),
    E(von="k1", nach="k2"), E(von="k2", nach="e_ok"),
])

# Einbettung verstärken (ZUSAMMENSPIEL Z5): eine Instanz des Modell-Läufers rechnet Einbettungen nacheinander; mehrere
# Instanzen rechnen nebeneinander (gemessen 23.10.2026: 4 Instanzen 2,0-fach, 8 Instanzen 2,4-fach). Bei Andrang so viele
# weitere, wie Aufträge warten, bis zur Höchstzahl des Dienstes und bis kurz vor die Speichergrenze; bei Ruhe zurück.
EINBETTUNG_VERSTAERKEN = _graph("einbettung_verstaerken", "Einbettung verstärken", Massnahmenart.EINBETTUNG_VERSTAERKEN, [
    K(id="a", art="ausloeser", baustein="einbettung_andrang"),
    K(id="p1", art="pruefung", baustein="einbettungsinstanzen_moeglich"),
    K(id="p2", art="pruefung", baustein="muss_entladen"),
    K(id="k0", art="aktion", baustein="modell_entladen"),
    K(id="k1", art="aktion", baustein="instanz_starten"),
    K(id="k2", art="aktion", baustein="melden", parameter={"text": "Einbettung verstärkt: {modell} auf {knoten}, {instanz}; {platz}"}),
    K(id="e_ok", art="ende", titel="verstärkt"),
    K(id="e_nein", art="ende", titel="keine weitere Instanz möglich"),
], [
    E(von="a", nach="p1"), E(von="p1", nach="p2", port="ja"), E(von="p1", nach="e_nein", port="nein"),
    E(von="p2", nach="k0", port="ja"), E(von="p2", nach="k1", port="nein"),
    E(von="k0", nach="k1"), E(von="k1", nach="k2"), E(von="k2", nach="e_ok"),
])

EINBETTUNG_ZURUECKBAUEN = _graph("einbettung_zurueckbauen", "Einbettung zurückbauen", Massnahmenart.EINBETTUNG_ZURUECKBAUEN, [
    K(id="a", art="ausloeser", baustein="einbettung_ruhe"),
    K(id="k1", art="aktion", baustein="modell_entladen"),
    K(id="k2", art="aktion", baustein="melden", parameter={"text": "Einbettung zurückgebaut: {anzahl} weitere Instanzen von {familie} auf {knoten}, {anlass}"}),
    K(id="e_ok", art="ende", titel="zurückgebaut"),
], [
    E(von="a", nach="k1"), E(von="k1", nach="k2"), E(von="k2", nach="e_ok"),
])

# Hintergrund bei Rechnerlast (ZUSAMMENSPIEL Z6): zwei Maße eines Rechners im gleitenden Mittel setzen die Stufe seines
# Hintergrunds, das höhere gilt: die Fremdlast (ohne Läufer, Dienste des Maschinenraums, Apps des Stellwerks und
# Container, also der Mensch und seine Programme) und die Docker-Last (Container ohne die von Anwendungen mit
# Hintergrundarbeit). Ab der Grenze gedrosselt (nur die Grundinstanz), ab der höheren angehalten; zurück erst unter
# Grenze minus Abstand. Vorgabe an.
HINTERGRUND_RECHNERLAST = _graph("hintergrund_rechnerlast", "Hintergrund bei Rechnerlast", Massnahmenart.HINTERGRUND_RECHNERLAST, [
    K(id="a", art="ausloeser", baustein="rechnerlast"),
    K(id="p1", art="pruefung", baustein="last_ueber_grenze", parameter={"grenze": "anhalten"}),
    K(id="p2", art="pruefung", baustein="stufe_ist", parameter={"stufe": "angehalten"}),
    K(id="p3", art="pruefung", baustein="last_ueber_grenze", parameter={"grenze": "drosseln"}),
    K(id="p4", art="pruefung", baustein="stufe_ist", parameter={"stufe": "gedrosselt"}),
    K(id="p5", art="pruefung", baustein="stufe_ist", parameter={"stufe": "frei"}),
    K(id="k1", art="aktion", baustein="hintergrund_auf_knoten_anhalten"),
    K(id="k2", art="aktion", baustein="melden", parameter={"text": "Hintergrund auf {knoten} angehalten (vorher {vorher}): {mass} im Mittel {last}, anhalten ab {grenze_anhalten}"}),
    K(id="k3", art="aktion", baustein="hintergrund_drosseln"),
    K(id="k4", art="aktion", baustein="melden", parameter={"text": "Hintergrund auf {knoten} gedrosselt (vorher {vorher}): {mass} im Mittel {last}, drosseln ab {grenze_drosseln}"}),
    K(id="k5", art="aktion", baustein="hintergrund_auf_knoten_freigeben"),
    K(id="k6", art="aktion", baustein="melden", parameter={"text": "Hintergrund auf {knoten} freigegeben (vorher {vorher}): {frei}"}),
    K(id="e_halt", art="ende", titel="angehalten"),
    K(id="e_drossel", art="ende", titel="gedrosselt"),
    K(id="e_frei", art="ende", titel="freigegeben"),
    K(id="e_bleibt", art="ende", titel="Stufe bleibt"),
], [
    E(von="a", nach="p1"), E(von="p1", nach="p2", port="ja"), E(von="p1", nach="p3", port="nein"),
    E(von="p2", nach="e_bleibt", port="ja"), E(von="p2", nach="k1", port="nein"), E(von="k1", nach="k2"), E(von="k2", nach="e_halt"),
    E(von="p3", nach="p4", port="ja"), E(von="p3", nach="p5", port="nein"),
    E(von="p4", nach="e_bleibt", port="ja"), E(von="p4", nach="k3", port="nein"), E(von="k3", nach="k4"), E(von="k4", nach="e_drossel"),
    E(von="p5", nach="e_bleibt", port="ja"), E(von="p5", nach="k5", port="nein"), E(von="k5", nach="k6"), E(von="k6", nach="e_frei"),
])

# Läufer arbeitet ohne Auftrag (Z6): ein Arbeiter des Läufers rechnet seit der Frist über der Schwelle, ohne dass die
# Leitstelle dort etwas rechnen lässt. Hängt zugleich ein Programm am Leitstand vorbei am Läufer, rechnet er vermutlich für
# diesen Kunden: nicht beenden (der Befund steht im Verlauf). Sonst beendet ihn der Maschinenraum. Vorgabe aus.
LAEUFER_OHNE_AUFTRAG = _graph("laeufer_ohne_auftrag", "Läufer arbeitet ohne Auftrag", Massnahmenart.LAEUFER_OHNE_AUFTRAG, [
    K(id="a", art="ausloeser", baustein="laeufer_arbeitet_ohne_auftrag"),
    K(id="p1", art="pruefung", baustein="umgehung_am_laeufer"),
    K(id="k1", art="aktion", baustein="laeufer_prozess_beenden"),
    K(id="k2", art="aktion", baustein="melden", parameter={"text": "Läufer auf {knoten}: {prozess} mit {modelldatei} rechnete {dauer} ohne Auftrag mit {kerne} Kernen; wird beendet"}),
    K(id="e_ok", art="ende", titel="beendet"),
    K(id="e_kunde", art="ende", titel="rechnet für ein Programm am Leitstand vorbei, nicht beendet"),
], [
    E(von="a", nach="p1"), E(von="p1", nach="e_kunde", port="ja"), E(von="p1", nach="k1", port="nein"),
    E(von="k1", nach="k2"), E(von="k2", nach="e_ok"),
])

VORLAGEN: list[Regelgraph] = [UMLEITEN, LEERLAUF, VORWAERMEN, KETTE, EXTERN, UMVERTEILEN, VERLAGERN, DOPPEL, HINTERGRUND, HINTERGRUND_RECHNERLAST,
                              LAEUFER_OHNE_AUFTRAG, INSTANZ, EINBETTUNG_VERSTAERKEN, EINBETTUNG_ZURUECKBAUEN]


def vorlagen() -> list[Regelgraph]:
    """Frische Kopien der Vorlagen (damit Tests und Nutzer sie verändern dürfen)."""
    return [g.model_copy(deep=True) for g in VORLAGEN]
