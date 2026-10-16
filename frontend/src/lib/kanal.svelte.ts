// Live-Kanal zur Leitstelle (/api/kanal): Lagebild und Ereignisse als Umschläge des Protokolls.
// Verbindet sich nach Abbrüchen mit wachsender Pause neu; der nächste Lagebild-Umschlag ersetzt Verpasstes.
import type { Lagebild, Umschlag } from './typen.gen';

class Kanal {
  lagebild = $state<Lagebild | null>(null);
  verbunden = $state(false);
  ereignisse = $state<Umschlag[]>([]);
  /** zählt abgeschlossene Aufträge; Ansichten mit Verlauf laden neu, wenn er sich ändert */
  verlaufStand = $state(0);
  /** letzte Auftragsbewegung je Anwendung (Browserzeit in ms, Knoten, Fähigkeit): kurze Aufträge sind fertig,
   *  bevor ein Lagebild sie als laufend zeigt; das Netzbild lässt sie damit kurz nachleuchten */
  aktivitaet = $state<Record<string, { zeit: number; knoten: string | null; extern: boolean; faehigkeit: string }>>({});
  /** Zeitversatz Leitstelle minus Browser in Sekunden, damit Dauern stimmen */
  versatz = $state(0);

  private ws: WebSocket | null = null;
  private pause = 1000;

  starten(): void {
    const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/kanal`);
    this.ws = ws;
    ws.onopen = () => {
      this.verbunden = true;
      this.pause = 1000;
    };
    ws.onmessage = (e) => this.empfangen(JSON.parse(e.data) as Umschlag);
    ws.onclose = () => {
      this.verbunden = false;
      setTimeout(() => this.starten(), this.pause);
      this.pause = Math.min(this.pause * 2, 30000);
    };
  }

  private empfangen(u: Umschlag): void {
    if (u.art === 'leitstelle.lagebild') {
      const bild = u.nutzlast as unknown as Lagebild;
      this.versatz = bild.zeit_s - Date.now() / 1000;
      this.lagebild = bild;
      return;
    }
    this.ereignisse = [u, ...this.ereignisse].slice(0, 200);
    const n = u.nutzlast as { anwendung?: string; knoten?: string | null; extern?: boolean; faehigkeit?: string };
    if (u.art.startsWith('auftrag.') && n.anwendung) {
      const bisher = this.aktivitaet[n.anwendung];
      this.aktivitaet = { ...this.aktivitaet, [n.anwendung]: { zeit: Date.now(), knoten: n.knoten ?? bisher?.knoten ?? null,
        extern: n.extern ?? bisher?.extern ?? false, faehigkeit: n.faehigkeit ?? bisher?.faehigkeit ?? 'text' } };
    }
    if (u.art === 'auftrag.ergebnis' || u.art === 'auftrag.abgebrochen' || u.art === 'auftrag.fehler') this.verlaufStand += 1;
  }

  /** Jetzt in der Zeit der Leitstelle (Sekunden seit 1970) */
  jetzt(): number {
    return Date.now() / 1000 + this.versatz;
  }
}

export const kanal = new Kanal();
