// Wörter, Symbole und Farben zu den Schlüsseln des Kerns. Gedruckt wird nie ein Schlüssel.
import type { Auftragszustand, Betriebsmodus, Dienstzustand, Faehigkeit, Lage, Massnahmenart, Massnahmenzustand, Modellzustand, Zone } from './typen.gen';

export const FAEHIGKEIT: Record<Faehigkeit, { wort: string; symbol: string; farbe: string; rgb: string; klasse: string }> = {
  text: { wort: 'Text', symbol: 'fa-comment-dots', farbe: 'var(--ls-himmel)', rgb: 'var(--ls-himmel-rgb)', klasse: 'text' },
  einbettung: { wort: 'Einbettung', symbol: 'fa-diagram-project', farbe: 'var(--ls-petrol)', rgb: 'var(--ls-petrol-rgb)', klasse: 'einbettung' },
  uebersetzen: { wort: 'Übersetzen', symbol: 'fa-language', farbe: 'var(--ls-tuerkis)', rgb: 'var(--ls-tuerkis-rgb)', klasse: 'uebersetzen' },
  hoeren: { wort: 'Hören', symbol: 'fa-ear-listen', farbe: 'var(--ls-minze)', rgb: 'var(--ls-minze-rgb)', klasse: 'hoeren' },
  bild_beschreiben: { wort: 'Bild beschreiben', symbol: 'fa-image', farbe: 'var(--ls-flieder)', rgb: 'var(--ls-flieder-rgb)', klasse: 'bild' },
  bild_erzeugen: { wort: 'Bild erzeugen', symbol: 'fa-palette', farbe: 'var(--ls-flieder)', rgb: 'var(--ls-flieder-rgb)', klasse: 'bild' },
  stimme: { wort: 'Stimme', symbol: 'fa-microphone-lines', farbe: 'var(--ls-rose)', rgb: 'var(--ls-rose-rgb)', klasse: 'stimme' },
  stimme_klonen: { wort: 'Stimmklon', symbol: 'fa-clone', farbe: 'var(--ls-rose)', rgb: 'var(--ls-rose-rgb)', klasse: 'stimme' },
  sprecher_erkennen: { wort: 'Sprecher erkennen', symbol: 'fa-fingerprint', farbe: 'var(--ls-minze)', rgb: 'var(--ls-minze-rgb)', klasse: 'hoeren' },
  sprecher_trennen: { wort: 'Sprecher trennen', symbol: 'fa-people-arrows', farbe: 'var(--ls-minze)', rgb: 'var(--ls-minze-rgb)', klasse: 'hoeren' },
  musik: { wort: 'Musik', symbol: 'fa-music', farbe: 'var(--ls-violett)', rgb: 'var(--ls-violett-rgb)', klasse: 'musik' },
  werkzeug: { wort: 'Werkzeuge', symbol: 'fa-screwdriver-wrench', farbe: 'var(--ls-sand)', rgb: 'var(--ls-sand-rgb)', klasse: 'werkzeug' },
  ton: { wort: 'Ton bearbeiten', symbol: 'fa-wave-square', farbe: 'var(--ls-minze)', rgb: 'var(--ls-minze-rgb)', klasse: 'hoeren' },
};

/** Hauptfähigkeit eines Modells für Farbe und Symbol: Bild vor Einbettung vor Text */
export function hauptfaehigkeit(f: Faehigkeit[]): Faehigkeit {
  for (const k of ['bild_beschreiben', 'einbettung', 'hoeren', 'stimme', 'musik', 'text'] as Faehigkeit[]) if (f.includes(k)) return k;
  return f[0] ?? 'text';
}

type Zustandsbild = { wort: string; symbol: string; klasse: string };

export const AUFTRAGSZUSTAND: Record<Auftragszustand, Zustandsbild> = {
  eingereiht: { wort: 'Wartet', symbol: 'fa-hourglass-half', klasse: 'wartet' },
  wartet_speicher: { wort: 'Wartet auf Speicher', symbol: 'fa-memory', klasse: 'wartet' },
  zugeteilt: { wort: 'Zugeteilt', symbol: 'fa-arrow-right-to-bracket', klasse: 'wartet' },
  laeuft: { wort: 'Läuft', symbol: 'fa-circle-play', klasse: 'laeuft' },
  pausiert: { wort: 'Pausiert', symbol: 'fa-circle-pause', klasse: 'pausiert' },
  fertig: { wort: 'Fertig', symbol: 'fa-check', klasse: 'fertig' },
  abgebrochen: { wort: 'Abgebrochen', symbol: 'fa-ban', klasse: 'aus' },
  fehlgeschlagen: { wort: 'Fehler', symbol: 'fa-triangle-exclamation', klasse: 'fehler' },
  abgelehnt: { wort: 'Abgelehnt', symbol: 'fa-circle-xmark', klasse: 'fehler' },
};

export const MODELLZUSTAND: Record<Modellzustand, Zustandsbild> = {
  frei: { wort: 'Nicht geladen', symbol: 'fa-circle', klasse: 'aus' },
  laedt: { wort: 'Lädt', symbol: 'fa-rotate', klasse: 'wartet' },
  geladen: { wort: 'Geladen', symbol: 'fa-circle-check', klasse: 'fertig' },
  rechnet: { wort: 'Rechnet', symbol: 'fa-gear', klasse: 'laeuft' },
};

export const DIENSTZUSTAND: Record<Dienstzustand, Zustandsbild> = {
  bereit: { wort: 'Bereit', symbol: 'fa-circle', klasse: 'fertig' },
  aus: { wort: 'Aus', symbol: 'fa-power-off', klasse: 'aus' },
  startet: { wort: 'Startet', symbol: 'fa-rotate', klasse: 'wartet' },
  pausiert: { wort: 'Pausiert', symbol: 'fa-circle-pause', klasse: 'pausiert' },
  nicht_erreichbar: { wort: 'Nicht erreichbar', symbol: 'fa-circle-xmark', klasse: 'fehler' },
};

export const ZONE: Record<Zone, { wort: string; symbol: string }> = {
  heim: { wort: 'Heimnetz', symbol: 'fa-house' },
  fern: { wort: 'Über VPN', symbol: 'fa-shield-halved' },
  extern: { wort: 'Extern', symbol: 'fa-cloud' },
};

export const PRIORITAET: Record<number, { wort: string; klasse: string }> = {
  0: { wort: 'Hintergrund', klasse: 'hintergrund' },
  1: { wort: 'Normal', klasse: 'normal' },
  2: { wort: 'Hoch', klasse: 'hoch' },
  3: { wort: 'Dringend', klasse: 'dringend' },
};

export const LAGE: Record<Lage, { wort: string; klasse: string }> = {
  ruhig: { wort: 'Lage ruhig', klasse: 'ruhig' },
  angespannt: { wort: 'Lage angespannt', klasse: 'angespannt' },
  engpass: { wort: 'Engpass', klasse: 'engpass' },
};

export const MODUS: Record<Betriebsmodus, { wort: string; lage: string; satz: string }> = {
  normal: { wort: 'Normal', lage: '', satz: '' },
  auslaufen: { wort: 'Auslaufen', lage: 'Läuft aus', satz: 'Hauptregler auf Auslaufen: laufende Aufträge enden, nichts Neues wird gestartet.' },
  halt: { wort: 'Halt', lage: 'Gestoppt', satz: 'Hauptregler auf Halt: nichts wird gerechnet, neue Aufträge werden abgelehnt.' },
};

export const MASSNAHME: Record<Massnahmenart, { wort: string; symbol: string }> = {
  umleiten: { wort: 'Umgeleitet', symbol: 'fa-route' },
  leerlauf_raeumen: { wort: 'Leerlauf geräumt', symbol: 'fa-broom' },
  vorwaermen: { wort: 'Vorgewärmt', symbol: 'fa-fire' },
  kette_ausweichen: { wort: 'In der Kette ausgewichen', symbol: 'fa-shuffle' },
  extern_ausweichen: { wort: 'Extern ausgewichen', symbol: 'fa-cloud' },
  umverteilen: { wort: 'Umverteilt', symbol: 'fa-people-arrows' },
  verlagern: { wort: 'Verlagert', symbol: 'fa-moon' },
  doppel_aufloesen: { wort: 'Doppel aufgelöst', symbol: 'fa-clone' },
  hintergrund_lage: { wort: 'Hintergrund nach Lage', symbol: 'fa-layer-group' },
};

export const MASSNAHMENZUSTAND: Record<Massnahmenzustand, string> = {
  geplant: 'Vorschlag', ausgefuehrt: 'Ausgeführt', geprueft_ohne_aktion: 'Geprüft', nicht_ausgeloest: 'Nicht ausgelöst', rueckgaengig: 'Rückgängig', gesperrt: 'Gesperrt',
};

/** Gründe aus PROTOKOLL.md Abschnitt 7 */
export const GRUND: Record<string, string> = {
  nutzer: 'von Hand gestoppt', anwendung: 'Anwendung hat getrennt', halt: 'Hauptregler Halt', neustart: 'Neustart der Leitstelle',
  dienst_fehler: 'Fehler des Dienstes', dienst_nicht_erreichbar: 'Dienst nicht erreichbar', modell_passt_nicht: 'Modell passt nicht in den Speicher',
  kein_modell: 'Modell unbekannt', kein_dienst: 'kein passender Dienst', faehigkeit_nicht_erlaubt: 'Fähigkeit nicht erlaubt',
  zone_nicht_erlaubt: 'Zone nicht erlaubt', gesperrt: 'Anwendung gesperrt', kontingent: 'Kontingent erreicht', wartung: 'Wartung',
};
