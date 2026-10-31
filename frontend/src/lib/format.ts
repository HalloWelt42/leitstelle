// Deutsche Zahlen- und Zeitformate. Keine Abkürzungen außer Maßeinheiten (s, GB).

const ganz = new Intl.NumberFormat('de-DE');
const eins = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/** Modellname mit Aufgabe als Text, wo nur Text geht (Auswahllisten, Hinweise): "Whisper Large V3 · Spracherkennung" */
export const modellText = (m: { name: string; aufgabe?: string }): string => (m.aufgabe ? `${m.name} · ${m.aufgabe}` : m.name);
export const zahl = (n: number | null | undefined): string => (n == null ? '-' : ganz.format(n));
export const gb = (n: number | null | undefined): string => (n == null ? '-' : `${eins.format(n)} GB`);
export const prozent = (anteil: number): string => `${ganz.format(Math.round(anteil * 100))} %`;
/** Große Mengen lesbar, ohne Abkürzung: 4000000 -> 4 Millionen, 100000 -> 100.000 */
export const menge = (n: number | null | undefined): string =>
  n == null ? '-' : n >= 1_000_000 ? `${(n / 1_000_000).toLocaleString('de-DE', { maximumFractionDigits: 2 })} ${n === 1_000_000 ? 'Million' : 'Millionen'}` : ganz.format(n);
/** Zahl mit fester Zahl an Nachkommastellen, deutsches Komma */
export const komma = (n: number, stellen = 1): string => n.toLocaleString('de-DE', { minimumFractionDigits: stellen, maximumFractionDigits: stellen });
/** Prozent eines Kerns als Kerne mit Komma (98 wird 1,0); ohne Wert ein Strich */
export const kerne = (cpu_prozent: number | null | undefined): string => (cpu_prozent == null ? '-' : komma(cpu_prozent / 100, 1));

/** Dauer in Worten: 4 s, 2 Minuten 10 s, 3 Stunden 5 Minuten */
export function dauer(s: number | null | undefined): string {
  if (s == null || !isFinite(s)) return '-';
  if (s < 10) return `${eins.format(Math.max(0, s))} s`;
  if (s < 90) return `${Math.round(s)} s`;
  const min = Math.floor(s / 60);
  if (min < 60) return `${min} ${min === 1 ? 'Minute' : 'Minuten'}${s % 60 >= 1 && min < 10 ? ` ${Math.round(s % 60)} s` : ''}`;
  const std = Math.floor(min / 60);
  return `${std} ${std === 1 ? 'Stunde' : 'Stunden'}${min % 60 ? ` ${min % 60} ${min % 60 === 1 ? 'Minute' : 'Minuten'}` : ''}`;
}

/** Uhrzeit zu Sekunden seit 1970; älter als heute mit Tag */
export function uhrzeit(zeit_s: number | null | undefined, mitSekunden = false): string {
  if (zeit_s == null) return '-';
  const d = new Date(zeit_s * 1000);
  const heute = new Date();
  const zeit = d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', ...(mitSekunden ? { second: '2-digit' } : {}) });
  if (d.toDateString() === heute.toDateString()) return zeit;
  return `${d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })} ${zeit}`;
}

/** vor 3 Minuten, vor 2 Stunden */
export function vor(zeit_s: number | null | undefined, jetzt_s: number): string {
  if (zeit_s == null) return 'nie';
  const s = Math.max(0, jetzt_s - zeit_s);
  return s < 5 ? 'gerade eben' : `vor ${dauer(s)}`;
}
