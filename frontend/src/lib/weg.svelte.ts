// Weg durch die Seiten: echte Pfade (/auftraege, /modelle ...), der Kern liefert für jeden Pfad index.html.

export type Seite = 'uebersicht' | 'auftraege' | 'modelle' | 'knoten' | 'dienste' | 'anschluss' | 'anwendungen' | 'protokoll' | 'mobil';

const PFADE: Record<Seite, string> = {
  uebersicht: '/', auftraege: '/auftraege', modelle: '/modelle', knoten: '/knoten', dienste: '/dienste', anschluss: '/anschluss',
  anwendungen: '/anwendungen', protokoll: '/protokoll', mobil: '/mobil',
};

function lesen(): { seite: Seite; teil: string | null } {
  const [, erster, zweiter] = location.pathname.split('/');
  const seite = (Object.entries(PFADE).find(([, p]) => p === `/${erster ?? ''}`)?.[0] ?? 'uebersicht') as Seite;
  return { seite, teil: zweiter ? decodeURIComponent(zweiter) : null };
}

class Weg {
  seite = $state<Seite>(lesen().seite);
  /** zweiter Pfadteil, zum Beispiel die Kennung eines gewählten Auftrags */
  teil = $state<string | null>(lesen().teil);

  constructor() {
    window.addEventListener('popstate', () => {
      const w = lesen();
      this.seite = w.seite;
      this.teil = w.teil;
    });
  }

  pfad(seite: Seite, teil?: string | null): string {
    return PFADE[seite] + (teil ? `/${encodeURIComponent(teil)}` : '');
  }

  gehe(seite: Seite, teil: string | null = null, ersetzen = false): void {
    const ziel = this.pfad(seite, teil);
    if (ziel !== location.pathname) (ersetzen ? history.replaceState : history.pushState).call(history, null, '', ziel);
    this.seite = seite;
    this.teil = teil;
  }

  /** Für <a href>: normale Klicks bleiben in der Anwendung, Mittelklick öffnet einen neuen Reiter */
  klick(e: MouseEvent, seite: Seite, teil: string | null = null): void {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    this.gehe(seite, teil);
  }
}

export const weg = new Weg();
