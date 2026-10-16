// Zugriff auf die eigene Schnittstelle /api/*. Jede Ablehnung kommt mit Grundwort und Satz zurück.
import type {
  AnwendungDaten, AuftragEintrag, Betriebsmodus, DienstAenderung, DienstDaten, Erkennung, Freigabe, Kennzahlen, KnotenDaten, KnotenEintrag,
  Lagebild, Massnahme, PruefEintrag,
} from './typen.gen';

export class ApiFehler extends Error {
  constructor(public grund: string, public begruendung: string, public status: number) {
    super(begruendung);
  }
}

async function rufen<T>(pfad: string, methode = 'GET', daten?: unknown): Promise<T> {
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

export const api = {
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

  knotenAnlegen: (d: KnotenDaten) => rufen<KnotenEintrag>('/knoten', 'POST', d),
  knotenAendern: (kennung: string, d: KnotenDaten) => rufen<KnotenEintrag>(`/knoten/${kennung}`, 'PUT', d),
  knotenLoeschen: (kennung: string) => rufen(`/knoten/${kennung}`, 'DELETE'),

  dienstErkennen: (adresse: string, zugang: string | null, extern: boolean) => rufen<Erkennung>('/dienste/erkennen', 'POST', { adresse, zugang, extern }),
  dienstAnlegen: (d: DienstDaten) => rufen<{ kennung: string; name: string }>('/dienste', 'POST', d),
  dienstAendern: (kennung: string, d: DienstAenderung) => rufen(`/dienste/${kennung}`, 'PATCH', d),
  dienstLoeschen: (kennung: string) => rufen(`/dienste/${kennung}`, 'DELETE'),
  dienstZugang: (kennung: string) => rufen<{ zugang: string | null }>(`/dienste/${kennung}/zugang`, 'POST'),

  anwendungAnlegen: (d: AnwendungDaten) => rufen<{ kennung: string; name: string; schluessel: string }>('/anwendungen', 'POST', d),
  anwendungAendern: (kennung: string, d: AnwendungDaten) => rufen(`/anwendungen/${kennung}`, 'PUT', d),
  anwendungLoeschen: (kennung: string) => rufen(`/anwendungen/${kennung}`, 'DELETE'),
  schluesselZeigen: (kennung: string) => rufen<{ schluessel: string }>(`/anwendungen/${kennung}/schluessel`, 'POST'),
  schluesselNeu: (kennung: string) => rufen<{ schluessel: string }>(`/anwendungen/${kennung}/schluessel/neu`, 'POST'),
  sperren: (kennung: string, grund: string) => rufen(`/anwendungen/${kennung}/sperren`, 'POST', { grund }),
  freigeben: (kennung: string) => rufen(`/anwendungen/${kennung}/freigeben`, 'POST'),
};
