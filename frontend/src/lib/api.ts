// Zugriff auf die eigene Schnittstelle /api/*. Jede Ablehnung kommt mit Grundwort und Satz zurück.
// Schreibende Aufrufe zählen als laufende Arbeit, solange ihre Antwort aussteht (kein Neuladen mittendrin).
import { arbeit } from './arbeit.svelte';
import type {
  AnwendungDaten, AuftragEintrag, Betriebsmodus, DienstAenderung, DienstDaten, Erkennung, Freigabe, Kennzahlen, KnotenDaten, KnotenEintrag,
  Lagebild, Massnahme, PruefEintrag, SteckbriefEintrag,
} from './typen.gen';

export class ApiFehler extends Error {
  constructor(public grund: string, public begruendung: string, public status: number) {
    super(begruendung);
  }
}

function rufen<T>(pfad: string, methode = 'GET', daten?: unknown): Promise<T> {
  return methode === 'GET' ? senden<T>(pfad, methode, daten) : arbeit.rahmen(() => senden<T>(pfad, methode, daten));
}

async function senden<T>(pfad: string, methode: string, daten?: unknown): Promise<T> {
  const antwort = await fetch(`/api${pfad}`, {
    method: methode,
    headers: daten === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: daten === undefined ? undefined : JSON.stringify(daten),
  });
  const text = await antwort.text();
  const inhalt = text ? JSON.parse(text) : null;
  if (!antwort.ok) {
    if (inhalt && typeof inhalt === 'object' && 'grund' in inhalt) throw new ApiFehler(inhalt.grund, inhalt.begruendung, antwort.status);
    if (inhalt && Array.isArray(inhalt.detail)) {
      const erstes = inhalt.detail[0];
      throw new ApiFehler('eingabe', `Eingabe prüfen: ${erstes?.loc?.slice(1).join(' ') ?? ''} ${erstes?.msg ?? ''}`.trim(), antwort.status);
    }
    throw new ApiFehler('fehler', `Die Leitstelle antwortet mit ${antwort.status}.`, antwort.status);
  }
  return inhalt as T;
}

export interface Seite<T> { eintraege: T[]; gesamt: number; ab: number; anzahl: number }
export interface FreigabePlan { vorschau: boolean; plan: Freigabe[]; frei_gb: number }
/** Rechner, wie die Verwaltung ihn zurückgibt: ohne Schlüsselfelder, nur ob ein Agent-Schlüssel vergeben ist */
export type Rechner = Omit<KnotenEintrag, 'agent_geheim' | 'agent_fingerabdruck'> & { agent_schluessel: boolean };

export const api = {
  version: () => rufen<{ version: string }>('/version'),
  lage: () => rufen<Lagebild>('/lage'),
  kennzahlen: () => rufen<Kennzahlen>('/kennzahlen'),
  hauptregler: (modus: Betriebsmodus, hintergrund: boolean, grund = '') =>
    rufen<{ betroffene_auftraege: number }>('/hauptregler', 'POST', { modus, hintergrund, grund }),

  auftraege: (ab: number, anzahl: number, filter: { anwendung?: string; zustand?: string } = {}) => {
    const q = new URLSearchParams({ ab: String(ab), anzahl: String(anzahl) });
    if (filter.anwendung) q.set('anwendung', filter.anwendung);
    if (filter.zustand) q.set('zustand', filter.zustand);
    return rufen<Seite<AuftragEintrag>>(`/auftraege?${q}`);
  },
  auftrag: (kennung: string) => rufen<AuftragEintrag>(`/auftraege/${kennung}`),
  stoppen: (kennung: string, modus: 'sofort' | 'auslaufen', grund: string) => rufen(`/auftraege/${kennung}/stoppen`, 'POST', { modus, grund }),
  massnahmen: (ab = 0, anzahl = 50) => rufen<Seite<Massnahme>>(`/massnahmen?ab=${ab}&anzahl=${anzahl}`),
  pruefprotokoll: (anzahl = 200) => rufen<{ eintraege: PruefEintrag[] }>(`/pruefprotokoll?anzahl=${anzahl}`),

  modellLaden: (kennung: string) => rufen(`/modelle/${kennung}/laden`, 'POST'),
  modellEntladen: (kennung: string) => rufen(`/modelle/${kennung}/entladen`, 'POST'),
  speicherFreigeben: (knoten: string, vorschau: boolean) => rufen<FreigabePlan>(`/knoten/${knoten}/speicher_freigeben`, 'POST', { vorschau }),

  knotenAnlegen: (d: KnotenDaten) => rufen<Rechner>('/knoten', 'POST', d),
  knotenAendern: (kennung: string, d: KnotenDaten) => rufen<Rechner>(`/knoten/${kennung}`, 'PUT', d),
  agentSchluessel: (kennung: string) => rufen<{ schluessel: string }>(`/knoten/${kennung}/agent/schluessel`, 'POST'),
  agentSchluesselNeu: (kennung: string) => rufen<{ schluessel: string }>(`/knoten/${kennung}/agent/schluessel/neu`, 'POST'),
  knotenLoeschen: (kennung: string) => rufen(`/knoten/${kennung}`, 'DELETE'),

  dienstErkennen: (adresse: string, zugang: string | null, extern: boolean) => rufen<Erkennung>('/dienste/erkennen', 'POST', { adresse, zugang, extern }),
  dienstAnlegen: (d: DienstDaten) => rufen<{ kennung: string; name: string }>('/dienste', 'POST', d),
  dienstAendern: (kennung: string, d: DienstAenderung) => rufen(`/dienste/${kennung}`, 'PATCH', d),
  dienstLoeschen: (kennung: string) => rufen(`/dienste/${kennung}`, 'DELETE'),
  dienstZugang: (kennung: string) => rufen<{ zugang: string | null }>(`/dienste/${kennung}/zugang`, 'POST'),
  dienstPruefen: (kennung: string) => rufen<{ dienst: string; zustand: string }>(`/dienste/${kennung}/pruefen`, 'POST'),
  steckbriefSetzen: (e: SteckbriefEintrag) => rufen<SteckbriefEintrag>('/steckbriefe', 'PUT', e),

  anwendungAnlegen: (d: AnwendungDaten) => rufen<{ kennung: string; name: string; schluessel: string }>('/anwendungen', 'POST', d),
  anwendungAendern: (kennung: string, d: AnwendungDaten) => rufen(`/anwendungen/${kennung}`, 'PUT', d),
  anwendungLoeschen: (kennung: string) => rufen(`/anwendungen/${kennung}`, 'DELETE'),
  schluesselZeigen: (kennung: string) => rufen<{ schluessel: string }>(`/anwendungen/${kennung}/schluessel`, 'POST'),
  schluesselNeu: (kennung: string) => rufen<{ schluessel: string }>(`/anwendungen/${kennung}/schluessel/neu`, 'POST'),
  sperren: (kennung: string, grund: string) => rufen(`/anwendungen/${kennung}/sperren`, 'POST', { grund }),
  freigeben: (kennung: string) => rufen(`/anwendungen/${kennung}/freigeben`, 'POST'),
};
