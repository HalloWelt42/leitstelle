import type { KnotenSicht } from './typen.gen';

/** Der Anteil System eines Rechners, geteilt in die Apps des Stellwerks und den Rest (Betriebssystem und übrige
 *  Programme). System ist gemessen (belegt minus Modelle und Dienste); die Apps stecken darin, beides misst der
 *  Maschinenraum. Ohne gemessene Apps bleibt System ungeteilt; mehr als System sind die Apps nie. */
export function systemteile(k: KnotenSicht): { apps: number; rest: number } {
  const apps = k.last.apps?.gemessen ? Math.min(k.last.apps.gb, k.system_gb) : 0;
  return { apps, rest: k.system_gb - apps };
}
