// Bedeutung der Regelwerte und Maßnahmen (Wort, Erklärung, Einheit, Grenzen, Vorgabe) vom Kern (GET /api/regelwerk), einmal
// je Sitzung geladen. Die gültigen Werte stehen live im Lagebild (bild.regelwerk); geändert wird über PATCH /api/regelwerk.
import { api } from './api';
import type { Massnahmenart, Regelgruppe, RegelgruppeSicht, RegelwerkAenderung, RegelwerkSicht, RegelwertSicht, Regelwerk } from './typen.gen';

class Regelbeschreibung {
  sicht = $state<RegelwerkSicht | null>(null);
  #laedt: Promise<void> | null = null;

  /** Lädt die Beschreibung, falls noch nicht da (mehrfach aufrufbar). */
  laden(): Promise<void> {
    if (this.sicht) return Promise.resolve();
    this.#laedt ??= api.regelwerk().then((s) => { this.sicht = s; }).finally(() => { this.#laedt = null; });
    return this.#laedt;
  }

  gruppe(g: Regelgruppe): RegelgruppeSicht | undefined {
    return this.sicht?.gruppen.find((x) => x.gruppe === g);
  }

  /** Ändern; die Antwort ist die neue Beschreibung (die Werte kommen zugleich über das Lagebild). */
  async aendern(a: RegelwerkAenderung): Promise<RegelwerkSicht> {
    this.sicht = await api.regelwerkAendern(a);
    return this.sicht;
  }
}

export const regelbeschreibung = new Regelbeschreibung();

type Wert = RegelwertSicht['wert'];

/** Der gültige Wert eines Regelwerts aus dem Lagebild */
export const aktuell = (r: Regelwerk, feld: string): Wert => (r as unknown as Record<string, Wert>)[feld];

// Stunden ab einer, Minuten ab zwei, jeweils nur glatt (wie im Kern, fach/regelwerk.py wert_text)
const SEKUNDEN_JE = [[3600, 3600, 'h'], [60, 120, 'min']] as const;

/** Ein Regelwert für Menschen, mit Einheit (wie im Prüfprotokoll): 5 min, 18 GB, 92 %, an */
export function wertText(w: RegelwertSicht, wert: Wert): string {
  if (w.einheit === 'schalter') return wert ? 'an' : 'aus';
  if (w.einheit === 'wahl') return w.wahl.find((x) => x.wert === wert)?.wort ?? String(wert);
  if (w.einheit === 'mehrfach') return (wert as string[]).map((x) => w.wahl.find((y) => y.wert === x)?.wort ?? x).join(', ') || 'keine';
  const n = Number(wert);
  const zahl = (x: number) => x.toLocaleString('de-DE', { maximumFractionDigits: 2 });
  switch (w.einheit) {
    case 'sekunden': {
      const [teiler, , wort] = SEKUNDEN_JE.find(([t, ab]) => n >= ab && n % t === 0) ?? [1, 1, 's'];
      return `${zahl(n / teiler)} ${wort}`;
    }
    case 'gb': return `${zahl(n)} GB`;
    case 'milliarden': return `${zahl(n)} Milliarden`;
    case 'prozent': return `${zahl(n)} %`;
    case 'punkte': return `${zahl(n)} Punkte`;
    case 'prozent_kern': return `${zahl(n)} % eines Kerns`;
    case 'anteil': return `${zahl(Math.round(n * 10000) / 100)} %`;
    case 'faktor': return `${zahl(n)}-fach`;
    default: return zahl(n);
  }
}

/** Gleiche Werte (Listen der Mehrfachauswahl nach Inhalt) */
export const gleich = (a: Wert, b: Wert): boolean => (Array.isArray(a) && Array.isArray(b) ? a.length === b.length && a.every((x, i) => x === b[i]) : a === b);

/** Mehrfachauswahl: die Liste mit oder ohne `x`, in der Reihenfolge der Möglichkeiten (wie der Kern sie hält) */
export const umgeschaltet = (w: RegelwertSicht, liste: string[], x: string): string[] =>
  w.wahl.map((y) => String(y.wert)).filter((y) => (y === x ? !liste.includes(x) : liste.includes(y)));

/** Einheit neben dem Eingabefeld; Anteile werden als Prozent eingegeben */
export const EINHEIT: Record<string, string> = {
  sekunden: 's', gb: 'GB', milliarden: 'Milliarden', prozent: '%', punkte: 'Punkte', prozent_kern: '% eines Kerns', anteil: '%', faktor: 'fach', anzahl: '',
};

/** Wert im Eingabefeld (Anteil als Prozent) und zurück */
export const eingabeWert = (w: RegelwertSicht, wert: Wert): number => (w.einheit === 'anteil' ? Math.round(Number(wert) * 10000) / 100 : Number(wert));
export const ausEingabe = (w: RegelwertSicht, eingabe: number): number => (w.einheit === 'anteil' ? Math.round(eingabe * 100) / 10000 : eingabe);
export const grenzeEingabe = (w: RegelwertSicht, g: number | null | undefined): number | undefined => (g == null ? undefined : eingabeWert(w, g));

/** Schaltet eine Maßnahme */
export const schalten = (art: Massnahmenart, an: boolean): Promise<RegelwerkSicht> => regelbeschreibung.aendern({ szenarien_an: { [art]: an } as RegelwerkAenderung['szenarien_an'] });
