// Erzeugt aus den Pydantic-Modellen des Kerns (npm run typen). Nicht von Hand ändern.

/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Betriebsmodus".
 */
export type Betriebsmodus = 'normal' | 'auslaufen' | 'halt';
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Lage".
 */
export type Lage = 'ruhig' | 'angespannt' | 'engpass';
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Automatik".
 */
export type Automatik = 'aus' | 'vorschlagen' | 'selbst';
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Zone".
 */
export type Zone = 'heim' | 'fern' | 'extern';
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Dienstzustand".
 */
export type Dienstzustand = 'bereit' | 'aus' | 'startet' | 'pausiert' | 'nicht_erreichbar';
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Faehigkeit".
 */
export type Faehigkeit =
  'text' | 'einbettung' | 'uebersetzen' | 'hoeren' | 'bild_beschreiben' | 'bild_erzeugen' | 'stimme' | 'musik' | 'werkzeug';
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Modellzustand".
 */
export type Modellzustand = 'frei' | 'laedt' | 'geladen' | 'rechnet';
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Auftragszustand".
 */
export type Auftragszustand =
  'eingereiht' | 'wartet_speicher' | 'zugeteilt' | 'laeuft' | 'pausiert' | 'fertig' | 'abgebrochen' | 'fehlgeschlagen' | 'abgelehnt';
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Massnahmenart".
 */
export type Massnahmenart =
  | 'umleiten'
  | 'leerlauf_raeumen'
  | 'vorwaermen'
  | 'kette_ausweichen'
  | 'extern_ausweichen'
  | 'umverteilen'
  | 'verlagern'
  | 'doppel_aufloesen'
  | 'hintergrund_lage';
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Massnahmenzustand".
 */
export type Massnahmenzustand = 'geplant' | 'ausgefuehrt' | 'geprueft_ohne_aktion' | 'nicht_ausgeloest' | 'rueckgaengig' | 'gesperrt';
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Prioritaet".
 */
export type Prioritaet = 0 | 1 | 2 | 3;
/**
 * Wie die Leitstelle mit einem Dienst spricht. Neue Arten kommen mit neuen Adaptern dazu.
 *
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Adapterart".
 */
export type Adapterart = 'openai_kompatibel';
export type Zone1 = 'heim' | 'fern' | 'extern';
export type Zone2 = 'heim' | 'fern' | 'extern';
export type Prioritaet1 = 0 | 1 | 2 | 3;

export interface Leitstelle {
  Lagebild?: Lagebild;
  AuftragEintrag?: AuftragEintrag;
  Massnahme?: Massnahme;
  Erkennung?: Erkennung;
  Freigabe?: Freigabe;
  KnotenEintrag?: KnotenEintrag;
  PruefEintrag?: PruefEintrag;
  Kennzahlen?: Kennzahlen;
  Umschlag?: Umschlag;
  KnotenDaten?: KnotenDaten;
  DienstDaten?: DienstDaten;
  DienstAenderung?: DienstAenderung;
  AnwendungDaten?: AnwendungDaten;
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Lagebild".
 */
export interface Lagebild {
  version: string;
  zeit_s: number;
  modus: Betriebsmodus;
  hintergrund_erlaubt: boolean;
  hintergrund_an: boolean;
  lage: Lage;
  lage_grund: string;
  automatik: Automatik;
  knoten: KnotenSicht[];
  dienste: DienstSicht[];
  modelle: ModellSicht[];
  auftraege: AuftragSicht[];
  anwendungen: AnwendungSicht[];
  massnahmen: Massnahme[];
  meldungen: Meldung[];
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "KnotenSicht".
 */
export interface KnotenSicht {
  kennung: string;
  name: string;
  adresse: string;
  zone: Zone;
  speicher_gb: number;
  system_gb: number;
  budget_gb: number;
  geladen_gb: number;
  frei_gb: number;
  belegt_anteil: number;
  erreichbar: boolean;
  budget_fest_gb: number | null;
  hintergrund_von: number | null;
  hintergrund_bis: number | null;
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "DienstSicht".
 */
export interface DienstSicht {
  kennung: string;
  name: string;
  art: string;
  adresse: string;
  knoten: string | null;
  extern: boolean;
  zustand: Dienstzustand;
  steuerbar: boolean;
  meldung: string;
  plaetze: number;
  zugang: boolean;
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "ModellSicht".
 */
export interface ModellSicht {
  kennung: string;
  name: string;
  familie: string;
  dienst: string;
  knoten: string | null;
  faehigkeiten: Faehigkeit[];
  gb: number;
  parameter_mrd: number;
  zustand: Modellzustand;
  geschuetzt: boolean;
  geladen_seit_s: number | null;
  letzte_nutzung_s: number | null;
  auftraege_aktiv: number;
  ladesperre_bis_s: number | null;
  ladesperre_grund: string;
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "AuftragSicht".
 */
export interface AuftragSicht {
  kennung: string;
  anwendung: string;
  faehigkeit: Faehigkeit;
  prioritaet: number;
  titel: string;
  zustand: Auftragszustand;
  begruendung: string;
  modell: string | null;
  familie_wunsch: string | null;
  dienst: string | null;
  knoten: string | null;
  extern: boolean;
  eingang_s: number;
  start_s: number | null;
  voraussichtlich_s: number | null;
  umgeleitet: number;
  auslaufend: boolean;
  schritte: Schritt[];
}
/**
 * Ein Eintrag der Zeitleiste eines Auftrags: Zustand und Begründung, wie die Leitstelle sie sah.
 *
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Schritt".
 */
export interface Schritt {
  zeit_s: number;
  zustand: Auftragszustand;
  text: string;
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "AnwendungSicht".
 */
export interface AnwendungSicht {
  kennung: string;
  name: string;
  prioritaet: number;
  faehigkeiten: Faehigkeit[];
  zonen: Zone[];
  extern_erlaubt: boolean;
  gleichzeitig: number;
  ketten: {
    [k: string]: string[];
  };
  gesperrt: boolean;
  sperrgrund: string;
  angelegt_s: number;
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Massnahme".
 */
export interface Massnahme {
  kennung: string;
  art: Massnahmenart;
  zustand: Massnahmenzustand;
  regel: string;
  zeit_s: number;
  grund: string;
  gewinn_s: number;
  aufwand_s: number;
  schritte: string[];
  auftraege: string[];
  knoten: string | null;
  modell: string | null;
  richtung: string | null;
  bewegungen: string[];
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Meldung".
 */
export interface Meldung {
  zeit_s: number;
  text: string;
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "AuftragEintrag".
 */
export interface AuftragEintrag {
  kennung: string;
  anwendung: string;
  faehigkeit: Faehigkeit;
  prioritaet: Prioritaet;
  titel: string;
  zustand: Auftragszustand;
  grund: string | null;
  begruendung: string;
  festes_modell: string | null;
  familie: string | null;
  modell_name: string | null;
  dienst: string | null;
  knoten: string | null;
  extern: boolean;
  umgeleitet: number;
  eingang_s: number;
  start_s: number | null;
  ende_s: number | null;
  erstes_stueck_s: number | null;
  token_ein: number | null;
  token_aus: number | null;
  teilergebnis_zeichen: number;
  weg: string;
  schritte: Schritt[];
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Erkennung".
 */
export interface Erkennung {
  erreichbar: boolean;
  steuerbar: boolean;
  meldung: string;
  art: Adapterart;
  adresse: string;
  rechnername: string | null;
  knoten_vorschlag: string | null;
  name_vorschlag: string;
  modelle: ModellBericht[];
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "ModellBericht".
 */
export interface ModellBericht {
  schluessel: string;
  name: string;
  faehigkeiten: Faehigkeit[];
  gb: number;
  parameter_mrd: number | null;
  geladen: boolean;
  instanzen: string[];
  plaetze: number | null;
  kontext: number | null;
  einbettung: boolean;
}
/**
 * Eine Zeile der Vorschau "Speicher freigeben".
 *
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Freigabe".
 */
export interface Freigabe {
  modell: string;
  name: string;
  gb: number;
  darf: boolean;
  grund: string;
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "KnotenEintrag".
 */
export interface KnotenEintrag {
  kennung: string;
  name: string;
  adresse: string;
  zone: Zone1;
  speicher_gb: number;
  system_gb: number;
  budget_fest_gb: number | null;
  hintergrund_von: number | null;
  hintergrund_bis: number | null;
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "PruefEintrag".
 */
export interface PruefEintrag {
  zeit_s: number;
  wer: string;
  was: string;
  gegenstand: string;
}
/**
 * Abgeschlossene Aufträge in einem Zeitraum (Übersicht: heute).
 *
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Kennzahlen".
 */
export interface Kennzahlen {
  ab_s: number;
  fertig: number;
  fehler: number;
  abgebrochen: number;
  abgelehnt: number;
  wartezeit_mittel_s: number | null;
  erstes_stueck_mittel_s: number | null;
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Umschlag".
 */
export interface Umschlag {
  protokoll: string;
  art: string;
  id: string;
  zeit: string;
  von: string;
  an: string;
  bezug: string | null;
  nutzlast: {
    [k: string]: unknown;
  };
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "KnotenDaten".
 */
export interface KnotenDaten {
  name: string;
  adresse: string;
  speicher_gb: number;
  zone?: Zone2;
  system_gb?: number;
  budget_fest_gb?: number | null;
  hintergrund_von?: number | null;
  hintergrund_bis?: number | null;
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "DienstDaten".
 */
export interface DienstDaten {
  adresse: string;
  name?: string | null;
  zugang?: string | null;
  knoten?: string | null;
  neuer_knoten?: KnotenDaten | null;
  extern?: boolean;
  plaetze?: number;
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "DienstAenderung".
 */
export interface DienstAenderung {
  name?: string | null;
  adresse?: string | null;
  zugang?: string | null;
  plaetze?: number | null;
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "AnwendungDaten".
 */
export interface AnwendungDaten {
  name: string;
  prioritaet?: Prioritaet1;
  faehigkeiten?: Faehigkeit[];
  zonen?: Zone[];
  extern_erlaubt?: boolean;
  gleichzeitig?: number;
  ketten?: {
    [k: string]: string[];
  };
}
