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
 * via the `definition` "Knotenzustand".
 */
export type Knotenzustand = 'erreichbar' | 'nicht_erreichbar' | 'schlaeft';
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Dienstzustand".
 */
export type Dienstzustand = 'bereit' | 'aus' | 'startet' | 'pausiert' | 'nicht_erreichbar' | 'ausfall' | 'schlaeft';
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Faehigkeit".
 */
export type Faehigkeit =
  | 'text'
  | 'einbettung'
  | 'uebersetzen'
  | 'hoeren'
  | 'bild_beschreiben'
  | 'bild_erzeugen'
  | 'stimme'
  | 'stimme_klonen'
  | 'sprecher_erkennen'
  | 'sprecher_trennen'
  | 'musik'
  | 'werkzeug'
  | 'ton';
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Modellzustand".
 */
export type Modellzustand = 'frei' | 'laedt' | 'geladen' | 'rechnet';
/**
 * Wofür ein Modell oder Dienst besonders taugt, über seine Fähigkeiten hinaus (Selbstauskunft, PROTOKOLL 4.8 der Leitstelle).
 *
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Eignung".
 */
export type Eignung = 'denken' | 'programmieren' | 'lange_texte' | 'schnell' | 'gruendlich';
export type Zone1 = 'heim' | 'fern' | 'extern';
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Quelle".
 */
export type Quelle = 'dienst' | 'hand' | 'gemessen' | 'abgeleitet';
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
  | 'hintergrund_lage'
  | 'weitere_instanz'
  | 'einbettung_verstaerken'
  | 'einbettung_zurueckbauen';
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
export type Adapterart = 'openai_kompatibel' | 'extern_openai' | 'agent';
export type Zone2 = 'heim' | 'fern' | 'extern';
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Richtung".
 */
export type Richtung = 'laden' | 'entladen';
export type Ausgang = 'ok' | 'abgelehnt' | 'gescheitert';
export type Zone3 = 'heim' | 'fern' | 'extern';
export type Prioritaet1 = 0 | 1 | 2 | 3;
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Ausgang".
 */
export type Ausgang1 = 'ok' | 'abgelehnt' | 'gescheitert';

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
  Bewegung?: Bewegung;
  KnotenDaten?: KnotenDaten;
  DienstDaten?: DienstDaten;
  DienstAenderung?: DienstAenderung;
  AnwendungDaten?: AnwendungDaten;
  SteckbriefEintrag?: SteckbriefEintrag;
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
  zustand: Knotenzustand;
  schlaeft_seit_s: number | null;
  budget_fest_gb: number | null;
  hintergrund_von: number | null;
  hintergrund_bis: number | null;
  agent: AgentSicht;
}
/**
 * Knoten-Agent: Schlüssel vergeben, verbunden, und was er zuletzt gemessen hat.
 *
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "AgentSicht".
 */
export interface AgentSicht {
  schluessel: boolean;
  verbunden: boolean;
  seit_s: number | null;
  betriebssystem: string | null;
  version: string | null;
  messwege: string[];
  messzeit_s: number | null;
  messwerte: Messwerte | null;
}
/**
 * `knoten.messwerte`: im Takt des Agenten.
 *
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "leitstelle__protokoll__knoten__Messwerte".
 */
export interface Messwerte {
  speicher_gesamt_gb: number;
  speicher_belegt_gb: number;
  swap_belegt_gb?: number | null;
  swap_gesamt_gb?: number | null;
  cpu_prozent?: number | null;
  last_1m?: number | null;
  platte_frei_gb?: number | null;
  grafik_prozent?: number | null;
  temperatur_c?: number | null;
  leistung_w?: number | null;
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
  anfragen_je_minute: number | null;
  anfragen_letzte_minute: number;
  frei_in_s: number;
  fehlschlaege: number;
  naechste_pruefung_s: number | null;
  einbettung_instanzen: number;
  einbettung_spielraum_gb: number;
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
  gb_jetzt: number | null;
  parameter_mrd: number;
  zustand: Modellzustand;
  geschuetzt: boolean;
  geladen_seit_s: number | null;
  letzte_nutzung_s: number | null;
  auftraege_aktiv: number;
  plaetze: number;
  gehalten_von: string | null;
  steckbrief: Steckbrief;
  instanzen_hoechstens: number;
  zusatz: boolean;
  ladesperre_bis_s: number | null;
  ladesperre_grund: string;
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Steckbrief".
 */
export interface Steckbrief {
  zweck?: string;
  eignung?: Eignung[];
  sprachen?: string[];
  faehigkeiten?: Faehigkeit[];
  kontext?: number | null;
  parameter_mrd?: number | null;
  quantisierung?: string | null;
  zone?: Zone1;
  anfragen_je_minute?: number | null;
  gemessen?: Messwerte1;
  herkunft?: {
    [k: string]: Quelle;
  };
}
/**
 * Aus den jüngsten fertigen Aufträgen des Modells (Mittelwerte als Median, Ladezeit als gleitender Mittelwert).
 *
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "leitstelle__protokoll__steckbrief__Messwerte".
 */
export interface Messwerte1 {
  auftraege?: number;
  rechenzeit_s?: number | null;
  erstes_stueck_s?: number | null;
  token_je_s?: number | null;
  ladezeit_s?: number | null;
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
  arbeit: string | null;
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
  gb_jetzt: number | null;
  schutz: boolean | null;
  aktiv: boolean;
  selbstauskunft: Selbstauskunft;
  familie: string | null;
  instanzen_hoechstens: number;
}
/**
 * Was ein Dienst über sich oder sein Modell sagt (PROTOKOLL 4.8): wofür er gemacht ist. Leer heißt: sagt nichts.
 *
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Selbstauskunft".
 */
export interface Selbstauskunft {
  zweck?: string;
  eignung?: Eignung[];
  sprachen?: string[];
  quantisierung?: string | null;
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
  zone: Zone2;
  speicher_gb: number;
  system_gb: number;
  budget_fest_gb: number | null;
  hintergrund_von: number | null;
  hintergrund_bis: number | null;
  agent_fingerabdruck: string | null;
  agent_geheim: string | null;
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
 * Ein Laden oder Entladen als Rohdatum, damit sich Fristen und Regeln aus dem Verlauf einstellen lassen
 * (ZUSAMMENSPIEL Z2). `zeit_s` ist der Beginn beim Dienst, `dauer_s` bis zur Antwort.
 *
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "Bewegung".
 */
export interface Bewegung {
  zeit_s: number;
  richtung: Richtung;
  familie: string;
  name: string;
  knoten: string | null;
  gb: number;
  dauer_s: number;
  ausgang: Ausgang;
  meldung: string;
}
/**
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "KnotenDaten".
 */
export interface KnotenDaten {
  name: string;
  adresse: string;
  speicher_gb: number;
  zone?: Zone3;
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
  anfragen_je_minute?: number | null;
  abgleich_s?: number | null;
  einbettung_instanzen?: number;
  einbettung_spielraum_gb?: number;
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
  anfragen_je_minute?: number | null;
  abgleich_s?: number | null;
  einbettung_instanzen?: number | null;
  einbettung_spielraum_gb?: number | null;
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
/**
 * Von Hand eingetragen, was ein Dienst nicht selbst über ein Modell sagt (PROTOKOLL 4.8); gilt je Modellfamilie
 * und geht der Auskunft des Dienstes vor. Leere Felder lassen die Auskunft des Dienstes stehen.
 *
 * This interface was referenced by `Leitstelle`'s JSON-Schema
 * via the `definition` "SteckbriefEintrag".
 */
export interface SteckbriefEintrag {
  familie: string;
  zweck?: string;
  eignung?: Eignung[];
  sprachen?: string[];
}
