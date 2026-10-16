// Leitstelle - gemeinsame Blöcke der Entwürfe (Kopf, Seitenleiste, Fußleiste)
// und EINE Beispielwelt, die alle Seiten teilen. Jede Seite hat dieselbe
// Schale und dieselben Zahlen - geändert wird nur hier, damit die Entwürfe
// nicht auseinanderlaufen.
//
// Beispielwelt (Stand des Entwurfs): zwei Macs, drei Pis, ein eigener Server,
// ein externer Anbieter. Zehn angemeldete Anwendungen, neun Aufträge in allen
// Zuständen. Die Lage ist "angespannt": der Speicher des großen Mac ist fast
// voll, ein Bildauftrag wartet deshalb auf Speicher.

export const APP = { name: 'Leitstelle', version: '0.1.0' };

// ── Knoten (Rechner) ────────────────────────────────────────────────────
// zone: heim (Heimnetz), fern (über VPN erreichbar), extern (fremder Anbieter)
export const KNOTEN = [
  { kennung: 'mac-128', name: 'Mac Studio', beschreibung: '128 GB, Apple Silicon', zone: 'heim', adresse: '192.168.1.20', zustand: 'aktiv',
    cpu: 34, gpu: 78, ram: 96, ram_gb: 128, platte: 61, temp: 71, netz_mbit: 410, dienste: ['laeufer', 'txt2voice', 'bildschmiede'], auftraege: 3 },
  { kennung: 'mac-32', name: 'MacBook', beschreibung: '32 GB, Apple Silicon', zone: 'heim', adresse: '192.168.1.31', zustand: 'aktiv',
    cpu: 12, gpu: 9, ram: 38, ram_gb: 32, platte: 44, temp: 48, netz_mbit: 120, dienste: ['whisper-32', 'acestep'], auftraege: 0 },
  { kennung: 'pi-archiv', name: 'Pi Archiv', beschreibung: 'Raspberry Pi 5, 8 GB, SSD', zone: 'heim', adresse: '192.168.1.49', zustand: 'aktiv',
    cpu: 22, gpu: 0, ram: 47, ram_gb: 8, platte: 73, temp: 58, netz_mbit: 36, dienste: ['piper-pi'], auftraege: 0 },
  { kennung: 'pi-stube', name: 'Pi Stube', beschreibung: 'Raspberry Pi 4, 4 GB', zone: 'heim', adresse: '192.168.1.26', zustand: 'aktiv',
    cpu: 6, gpu: 0, ram: 31, ram_gb: 4, platte: 28, temp: 49, netz_mbit: 4, dienste: [], auftraege: 0 },
  { kennung: 'pi-werkstatt', name: 'Pi Werkstatt', beschreibung: 'Raspberry Pi 4, 8 GB', zone: 'heim', adresse: '192.168.1.61', zustand: 'aus',
    cpu: 0, gpu: 0, ram: 0, ram_gb: 8, platte: 0, temp: 0, netz_mbit: 0, dienste: [], auftraege: 0, seit: 'seit 2 Tagen nicht erreichbar' },
  { kennung: 'server-fern', name: 'Server Helsinki', beschreibung: 'Mietserver, 4 Kerne, 8 GB', zone: 'fern', adresse: '10.66.0.1 über VPN', zustand: 'aktiv',
    cpu: 18, gpu: 0, ram: 52, ram_gb: 8, platte: 39, temp: 0, netz_mbit: 22, dienste: ['extern-anbieter'], auftraege: 0 },
];

// ── Dienste (Anbieter von Fähigkeiten) ──────────────────────────────────
// faehigkeiten: text, einbettung, uebersetzen, hoeren, bild, musik, stimme, werkzeug
export const DIENSTE = [
  { kennung: 'laeufer', name: 'Modell-Läufer', art: 'OpenAI-kompatibel', knoten: 'mac-128', adresse: 'http://192.168.1.20:1234', zustand: 'laeuft',
    faehigkeiten: ['text', 'einbettung', 'bild', 'uebersetzen'], modelle: ['qwen-80b', 'bge-m3', 'glm-vision', 'gemma-26b', 'qwen-vl-30b', 'qwen-coder'], auftraege: 2, hinweis: 'Modelle werden bei Bedarf geladen; Modell immer mitsenden.' },
  { kennung: 'txt2voice', name: 'txt2voice', art: 'Eigene Schnittstelle', knoten: 'mac-128', adresse: 'http://192.168.1.20:10031', zustand: 'laeuft',
    faehigkeiten: ['stimme', 'hoeren'], modelle: ['whisper-gross', 'xtts-klon'], auftraege: 1, hinweis: 'Lange Läufe ohne Lese-Zeitgrenze, nur Verbindungsgrenze.' },
  { kennung: 'bildschmiede', name: 'Bildschmiede', art: 'Bild-Werkbank', knoten: 'mac-128', adresse: 'http://192.168.1.20:8188', zustand: 'pausiert',
    faehigkeiten: ['bild'], modelle: ['flux-klein', 'freisteller'], auftraege: 1, hinweis: 'Grafikspeicher exklusiv; nie parallel zum großen Textmodell starten.' },
  { kennung: 'whisper-32', name: 'Hörer MacBook', art: 'Transkription', knoten: 'mac-32', adresse: 'http://192.168.1.31:8790', zustand: 'laeuft',
    faehigkeiten: ['hoeren'], modelle: ['whisper-mittel'], auftraege: 0 },
  { kennung: 'acestep', name: 'Klangschmiede', art: 'Musik', knoten: 'mac-32', adresse: 'http://192.168.1.31:8770', zustand: 'bereit',
    faehigkeiten: ['musik'], modelle: ['ace-step'], auftraege: 0 },
  { kennung: 'piper-pi', name: 'Sprecher Pi', art: 'Sprachsynthese klein', knoten: 'pi-archiv', adresse: 'http://192.168.1.49:8793', zustand: 'bereit',
    faehigkeiten: ['stimme'], modelle: ['piper-thorsten'], auftraege: 0 },
  { kennung: 'extern-anbieter', name: 'Externer Anbieter', art: 'OpenAI-kompatibel, extern', knoten: 'extern', adresse: 'https://inference.hetzner.com/api/v1', zustand: 'bereit', zone: 'extern',
    faehigkeiten: ['text', 'bild'], modelle: ['qwen-35b-extern', 'qwen-27b-extern'], auftraege: 0, kosten_heute: 0.42, kosten_grenze: 5, hinweis: '10 Anfragen je Minute; Schlüssel liegt nur in der Leitstelle.' },
];

// ── Modelle ─────────────────────────────────────────────────────────────
// zustand: geladen | rechnet | frei (nicht geladen) | laedt
export const MODELLE = [
  { kennung: 'qwen-80b', name: 'Qwen3 Next 80B', dienst: 'laeufer', faehigkeit: 'text', gb: 84.7, kontext: 262144, zustand: 'rechnet', geschuetzt: false, zuletzt: 'jetzt', auftraege: 1, parameter: '80B' },
  { kennung: 'bge-m3', name: 'bge-m3 Einbettung', dienst: 'laeufer', faehigkeit: 'einbettung', gb: 1.1, kontext: 8192, zustand: 'rechnet', geschuetzt: true, zuletzt: 'jetzt', auftraege: 1, parameter: '0,6B' },
  { kennung: 'glm-vision', name: 'GLM 4.6V Flash', dienst: 'laeufer', faehigkeit: 'bild', gb: 11.8, kontext: 65536, zustand: 'frei', geschuetzt: true, zuletzt: 'vor 3 Stunden', auftraege: 0, parameter: '9B', wartet: 1 },
  { kennung: 'gemma-26b', name: 'Gemma 4 26B', dienst: 'laeufer', faehigkeit: 'bild', gb: 16.2, kontext: 131072, zustand: 'frei', geschuetzt: false, zuletzt: 'gestern', auftraege: 0, parameter: '26B' },
  { kennung: 'qwen-vl-30b', name: 'Qwen3 VL 30B', dienst: 'laeufer', faehigkeit: 'bild', gb: 18.4, kontext: 131072, zustand: 'frei', geschuetzt: false, zuletzt: 'vor 6 Tagen', auftraege: 0, parameter: '30B' },
  { kennung: 'qwen-coder', name: 'Qwen3 Coder Next', dienst: 'laeufer', faehigkeit: 'text', gb: 46.3, kontext: 262144, zustand: 'frei', geschuetzt: false, zuletzt: 'vor 2 Tagen', auftraege: 0, parameter: '80B' },
  { kennung: 'whisper-gross', name: 'Whisper groß v3', dienst: 'txt2voice', faehigkeit: 'hoeren', gb: 3.1, zustand: 'rechnet', geschuetzt: true, zuletzt: 'jetzt', auftraege: 1, parameter: '1,5B' },
  { kennung: 'xtts-klon', name: 'Stimmklon', dienst: 'txt2voice', faehigkeit: 'stimme', gb: 1.9, zustand: 'geladen', geschuetzt: true, zuletzt: 'vor 12 Minuten', auftraege: 0, parameter: '0,5B' },
  { kennung: 'flux-klein', name: 'Flux klein', dienst: 'bildschmiede', faehigkeit: 'bild', gb: 12.0, zustand: 'frei', geschuetzt: false, zuletzt: 'vor 1 Stunde', auftraege: 0, parameter: '12B' },
  { kennung: 'freisteller', name: 'Freisteller', dienst: 'bildschmiede', faehigkeit: 'bild', gb: 0.9, zustand: 'frei', geschuetzt: true, zuletzt: 'gestern', auftraege: 0, parameter: '0,2B' },
  { kennung: 'whisper-mittel', name: 'Whisper mittel', dienst: 'whisper-32', faehigkeit: 'hoeren', gb: 1.5, zustand: 'geladen', geschuetzt: true, zuletzt: 'vor 40 Minuten', auftraege: 0, parameter: '0,8B' },
  { kennung: 'ace-step', name: 'ACE-Step', dienst: 'acestep', faehigkeit: 'musik', gb: 7.2, zustand: 'frei', geschuetzt: true, zuletzt: 'vor 3 Tagen', auftraege: 0, parameter: '3,5B' },
  { kennung: 'piper-thorsten', name: 'Piper Thorsten', dienst: 'piper-pi', faehigkeit: 'stimme', gb: 0.1, zustand: 'geladen', geschuetzt: true, zuletzt: 'vor 2 Stunden', auftraege: 0, parameter: '0,02B' },
  { kennung: 'qwen-35b-extern', name: 'Qwen3.6 35B (extern)', dienst: 'extern-anbieter', faehigkeit: 'text', gb: 0, zustand: 'extern', geschuetzt: false, zuletzt: 'vor 1 Stunde', auftraege: 0, parameter: '35B' },
  { kennung: 'qwen-27b-extern', name: 'Qwen3.8 27B (extern)', dienst: 'extern-anbieter', faehigkeit: 'bild', gb: 0, zustand: 'extern', geschuetzt: false, zuletzt: 'gestern', auftraege: 0, parameter: '27B' },
];

// ── Anwendungen (angemeldete Verbraucher) ───────────────────────────────
// prioritaet: dringend | hoch | normal | hintergrund
// stufe (Umbau-Stand): 1 nur Fassade, 2 Anmeldung, 3 Signalkanal, 4 eigene Aufträge mit Fortschritt
export const ANWENDUNGEN = [
  { kennung: 'zusage', name: 'Zusage', knoten: 'mac-128', faehigkeiten: ['text'], prioritaet: 'hoch', heute: 9, token_heute: 412000, zustand: 'verbunden', signale: true, extern: false, stufe: 3 },
  { kennung: 'tubevault', name: 'TubeVault', knoten: 'pi-archiv', faehigkeiten: ['hoeren', 'stimme', 'text'], prioritaet: 'hintergrund', heute: 3, token_heute: 96000, zustand: 'verbunden', signale: true, extern: false, stufe: 4 },
  { kennung: 'fundus', name: 'Fundus', knoten: 'mac-128', faehigkeiten: ['text', 'einbettung', 'werkzeug'], prioritaet: 'normal', heute: 24, token_heute: 1830000, zustand: 'verbunden', signale: true, extern: true, stufe: 3 },
  { kennung: 'medienpool', name: 'Medienpool', knoten: 'mac-128', faehigkeiten: ['uebersetzen', 'stimme', 'bild'], prioritaet: 'normal', heute: 4, token_heute: 21000, zustand: 'verbunden', signale: false, extern: false, stufe: 2 },
  { kennung: 'kiste', name: 'Kiste', knoten: 'pi-archiv', faehigkeiten: ['bild', 'text'], prioritaet: 'normal', heute: 2, token_heute: 4200, zustand: 'verbunden', signale: false, extern: false, stufe: 2 },
  { kennung: 'codehilfe', name: 'Codehilfe', knoten: 'mac-32', faehigkeiten: ['text', 'werkzeug'], prioritaet: 'hoch', heute: 14, token_heute: 2240000, zustand: 'verbunden', signale: false, extern: true, nur_fassade: true, stufe: 1 },
  { kennung: 'rufzeichen', name: 'Rufzeichen', knoten: 'mac-32', faehigkeiten: ['hoeren', 'text', 'stimme'], prioritaet: 'dringend', heute: 11, token_heute: 18000, zustand: 'verbunden', signale: true, extern: false, stufe: 3 },
  { kennung: 'mitschrift', name: 'Mitschrift', knoten: 'mac-32', faehigkeiten: ['hoeren', 'text'], prioritaet: 'normal', heute: 2, token_heute: 31000, zustand: 'getrennt', signale: true, extern: false, stufe: 3 },
  { kennung: 'pinnwand', name: 'Pinnwand', knoten: 'mac-128', faehigkeiten: ['text'], prioritaet: 'normal', heute: 0, token_heute: 0, zustand: 'getrennt', signale: false, extern: false, stufe: 1 },
  { kennung: 'bildschmiede-app', name: 'Bildschmiede', knoten: 'mac-128', faehigkeiten: ['bild', 'uebersetzen'], prioritaet: 'hintergrund', heute: 4, token_heute: 6000, zustand: 'verbunden', signale: true, extern: false, stufe: 3 },
];

// ── Aufträge ────────────────────────────────────────────────────────────
// zustand: laeuft | wartet | wartet_speicher | pausiert | auslaufend | fertig | fehler | abgebrochen
export const AUFTRAEGE = [
  { kennung: 'a-7f3c', titel: 'Anschreiben entwerfen', anwendung: 'zusage', faehigkeit: 'text', modell: 'qwen-80b', dienst: 'laeufer', knoten: 'mac-128',
    zustand: 'laeuft', fortschritt: 62, prioritaet: 'hoch', seit: '00:41', rest: '~25 s', token: 1240, token_s: 38, streamt: true, pausierbar: false,
    schritte: ['angenommen', 'eingereiht', 'modell bereit', 'rechnet', 'streamt', 'fertig'], schritt: 4 },
  { kennung: 'a-2b91', titel: 'Transkript: Einstieg in OpenTelemetry (3:21 h)', anwendung: 'tubevault', faehigkeit: 'hoeren', modell: 'whisper-gross', dienst: 'txt2voice', knoten: 'mac-128',
    zustand: 'laeuft', fortschritt: 41, prioritaet: 'hintergrund', seit: '14:12', rest: '~22 min', streamt: false, pausierbar: true, abschnitte: '58 von 141 Abschnitten',
    schritte: ['angenommen', 'eingereiht', 'modell bereit', 'rechnet', 'ergebnis', 'fertig'], schritt: 3 },
  { kennung: 'a-9d04', titel: 'Einbettung: 1.240 Abschnitte', anwendung: 'fundus', faehigkeit: 'einbettung', modell: 'bge-m3', dienst: 'laeufer', knoten: 'mac-128',
    zustand: 'laeuft', fortschritt: 88, prioritaet: 'normal', seit: '03:05', rest: '~30 s', streamt: false, pausierbar: true, abschnitte: '1.091 von 1.240',
    schritte: ['angenommen', 'eingereiht', 'modell bereit', 'rechnet', 'ergebnis', 'fertig'], schritt: 3 },
  { kennung: 'a-c150', titel: 'Prompt übersetzen (Deutsch nach Englisch)', anwendung: 'medienpool', faehigkeit: 'uebersetzen', modell: 'qwen-80b', dienst: 'laeufer', knoten: 'mac-128',
    zustand: 'wartet', fortschritt: 0, prioritaet: 'normal', seit: '00:12', rest: 'nach a-7f3c', streamt: false, pausierbar: true, grund: 'Modell ist mit einem Auftrag höherer Priorität belegt',
    schritte: ['angenommen', 'eingereiht', 'modell bereit', 'rechnet', 'ergebnis', 'fertig'], schritt: 1 },
  { kennung: 'a-e77a', titel: 'Foto beschreiben: Werkzeugkiste', anwendung: 'kiste', faehigkeit: 'bild', modell: 'glm-vision', dienst: 'laeufer', knoten: 'mac-128',
    zustand: 'wartet_speicher', fortschritt: 0, prioritaet: 'normal', seit: '02:48', rest: 'offen', streamt: false, pausierbar: true,
    grund: 'Bildmodell (11,8 GB) passt nicht neben das Textmodell (84,7 GB); 5,1 GB frei', vorschlag: 'Wartet, bis das Textmodell frei ist (etwa 25 s), dann wird es geladen.',
    schritte: ['angenommen', 'eingereiht', 'wartet auf Speicher', 'modell laden', 'rechnet', 'fertig'], schritt: 2 },
  { kennung: 'a-4a12', titel: '4 Bilder erzeugen: Planet Wüste', anwendung: 'bildschmiede-app', faehigkeit: 'bild', modell: 'flux-klein', dienst: 'bildschmiede', knoten: 'mac-128',
    zustand: 'pausiert', fortschritt: 25, prioritaet: 'hintergrund', seit: '18:30', rest: 'angehalten', streamt: false, pausierbar: true, grund: 'Von dir angehalten um 13:52, damit Zusage Vorrang hat',
    schritte: ['angenommen', 'eingereiht', 'modell bereit', 'rechnet', 'ergebnis', 'fertig'], schritt: 3 },
  { kennung: 'a-0b6e', titel: 'Besprechung 14:00 (48 min)', anwendung: 'mitschrift', faehigkeit: 'hoeren', modell: 'whisper-mittel', dienst: 'whisper-32', knoten: 'mac-32',
    zustand: 'fertig', fortschritt: 100, prioritaet: 'normal', seit: '06:12', rest: 'fertig 14:58', streamt: false, pausierbar: true,
    schritte: ['angenommen', 'eingereiht', 'modell bereit', 'rechnet', 'ergebnis', 'fertig'], schritt: 5 },
  { kennung: 'a-51f9', titel: 'Antwort sprechen: "Die Haustür ist zu."', anwendung: 'rufzeichen', faehigkeit: 'stimme', modell: 'xtts-klon', dienst: 'txt2voice', knoten: 'mac-128',
    zustand: 'fertig', fortschritt: 100, prioritaet: 'dringend', seit: '00:02', rest: 'fertig 14:55', streamt: true, pausierbar: false,
    schritte: ['angenommen', 'modell bereit', 'rechnet', 'streamt', 'fertig'], schritt: 4 },
  { kennung: 'a-88c3', titel: 'Code-Durchsicht: Zahlungsmodul', anwendung: 'codehilfe', faehigkeit: 'text', modell: 'qwen-coder', dienst: 'laeufer', knoten: 'mac-128',
    zustand: 'fehler', fortschritt: 0, prioritaet: 'hoch', seit: '00:09', rest: 'abgebrochen 14:41', streamt: true, pausierbar: false,
    grund: 'Modell Qwen3 Coder Next (46,3 GB) konnte nicht geladen werden: Speicher reicht nicht, solange das Textmodell rechnet', vorschlag: 'Erneut einreihen, sobald Speicher frei ist, oder extern rechnen lassen (Externer Anbieter, etwa 0,03 Euro).',
    schritte: ['angenommen', 'eingereiht', 'modell laden', 'fehler'], schritt: 3 },
];

// ── Wörter zu Schlüsseln (nie Schlüssel drucken) ────────────────────────
export const WORT = {
  faehigkeit: { text: 'Text', einbettung: 'Einbettung', uebersetzen: 'Übersetzen', hoeren: 'Hören', bild: 'Bild', musik: 'Musik', stimme: 'Stimme', werkzeug: 'Werkzeuge' },
  faehigkeit_symbol: { text: 'fa-comment-dots', einbettung: 'fa-diagram-project', uebersetzen: 'fa-language', hoeren: 'fa-ear-listen', bild: 'fa-image', musik: 'fa-music', stimme: 'fa-microphone-lines', werkzeug: 'fa-screwdriver-wrench' },
  zustand: { laeuft: 'Läuft', wartet: 'Wartet', wartet_speicher: 'Wartet auf Speicher', pausiert: 'Pausiert', auslaufend: 'Läuft aus', fertig: 'Fertig', fehler: 'Fehler', abgebrochen: 'Abgebrochen',
             aktiv: 'Erreichbar', aus: 'Nicht erreichbar', wartung: 'Wartung', bereit: 'Bereit', geladen: 'Geladen', rechnet: 'Rechnet', frei: 'Nicht geladen', laedt: 'Lädt', extern: 'Extern', verbunden: 'Verbunden', getrennt: 'Getrennt' },
  zustand_klasse: { laeuft: 'laeuft', wartet: 'wartet', wartet_speicher: 'wartet', pausiert: 'pausiert', auslaufend: 'auslaufend', fertig: 'fertig', fehler: 'fehler', abgebrochen: 'aus',
                    aktiv: 'fertig', aus: 'aus', wartung: 'wartung', bereit: 'fertig', geladen: 'fertig', rechnet: 'laeuft', frei: 'aus', laedt: 'wartet', extern: 'wartung', verbunden: 'fertig', getrennt: 'aus' },
  zustand_symbol: { laeuft: 'fa-circle-play', wartet: 'fa-hourglass-half', wartet_speicher: 'fa-memory', pausiert: 'fa-circle-pause', auslaufend: 'fa-person-walking-arrow-right', fertig: 'fa-check',
                    fehler: 'fa-triangle-exclamation', abgebrochen: 'fa-ban', aktiv: 'fa-circle', aus: 'fa-circle-xmark', wartung: 'fa-screwdriver-wrench', bereit: 'fa-circle', geladen: 'fa-circle-check',
                    rechnet: 'fa-gear', frei: 'fa-circle', laedt: 'fa-rotate', extern: 'fa-cloud', verbunden: 'fa-link', getrennt: 'fa-link-slash' },
  prioritaet: { dringend: 'Dringend', hoch: 'Hoch', normal: 'Normal', hintergrund: 'Hintergrund' },
  zone: { heim: 'Heimnetz', fern: 'Über VPN', extern: 'Extern' },
  zone_symbol: { heim: 'fa-house', fern: 'fa-shield-halved', extern: 'fa-cloud' },
};

// Farben der Fähigkeiten für Flächen und Symbole (Marke und RGB-Marke)
export const FARBE = { text: ['var(--ls-himmel)', 'var(--ls-himmel-rgb)'], einbettung: ['var(--ls-petrol)', 'var(--ls-petrol-rgb)'], uebersetzen: ['var(--ls-tuerkis)', 'var(--ls-tuerkis-rgb)'],
                       hoeren: ['var(--ls-minze)', 'var(--ls-minze-rgb)'], bild: ['var(--ls-flieder)', 'var(--ls-flieder-rgb)'], musik: ['var(--ls-violett)', 'var(--ls-violett-rgb)'],
                       stimme: ['var(--ls-rose)', 'var(--ls-rose-rgb)'], werkzeug: ['var(--ls-sand)', 'var(--ls-sand-rgb)'] };
export const WORT_STUFE = { 1: 'Nur Fassade', 2: 'Angemeldet', 3: 'Signalkanal', 4: 'Eigene Aufträge' };

export const knoten = (k) => KNOTEN.find(x => x.kennung === k);
export const dienst = (k) => DIENSTE.find(x => x.kennung === k);
export const modell = (k) => MODELLE.find(x => x.kennung === k);
export const anwendung = (k) => ANWENDUNGEN.find(x => x.kennung === k);

// ── Formate ─────────────────────────────────────────────────────────────
export const zahl = (n) => new Intl.NumberFormat('de-DE').format(n);
export const gb = (n) => `${n.toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} GB`;
export const euro = (n) => `${n.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} Euro`;
export const kurz = (n) => zahl(n);   // keine Abkürzungen in sichtbaren Texten: volle Zahl mit Tausenderpunkten

// ── Bausteine als HTML ──────────────────────────────────────────────────
export const faehigkeit = (f) => `<span class="faehigkeit ${f}"><i class="fa-solid ${WORT.faehigkeit_symbol[f]}"></i>${WORT.faehigkeit[f]}</span>`;
export const zustand = (z, dreht = false) => `<span class="zustand ${WORT.zustand_klasse[z]}"><i class="fa-solid ${WORT.zustand_symbol[z]}${dreht && z === 'laeuft' ? ' dreht' : ''}"></i>${WORT.zustand[z]}</span>`;
export const zone = (z) => `<span class="zone ${z}"><i class="fa-solid ${WORT.zone_symbol[z]}"></i>${WORT.zone[z]}</span>`;
export const hilfepunkt = (thema, titel) => `<button class="hilfepunkt" title="${titel || 'Erklärung öffnen: ' + thema}" data-hilfe="${thema}">i</button>`;

// Kleiner Verlauf (Sparkline) als SVG; werte 0..100
export function verlauf(werte, farbe = 'var(--ls-himmel)', breite = 160, hoehe = 40) {
  const max = Math.max(1, ...werte);
  const pt = werte.map((w, i) => [i * (breite / (werte.length - 1)), hoehe - (w / max) * (hoehe - 4) - 2]);
  const linie = pt.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  const [lx, ly] = pt[pt.length - 1];
  return `<svg class="verlauf" viewBox="0 0 ${breite} ${hoehe}" preserveAspectRatio="none" style="--v-farbe:${farbe}">
    <path class="flaeche" d="${linie} L${breite},${hoehe} L0,${hoehe} Z"></path>
    <path class="linie" d="${linie}"></path>
    <circle class="jetzt" cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="3"></circle>
  </svg>`;
}

// Auslastungs-Ring mit Wort darunter
export function ring(wert, name, klasse = '') {
  const stufe = klasse || (wert >= 90 ? 'gefahr' : wert >= 75 ? 'warnung' : '');
  return `<div><div class="ring ${stufe}" style="--wert:${wert}" title="${name}: ${wert} Prozent"><b class="zahl">${wert}%</b></div>${name}</div>`;
}

// Zufällige, aber stabile Verlaufswerte je Schlüssel (damit Seiten gleich aussehen)
export function reihe(schluessel, n = 24, grund = 40, spanne = 40) {
  let h = 11; for (const c of schluessel) h = (h * 31 + c.charCodeAt(0)) % 9973;
  const aus = []; let w = grund;
  for (let i = 0; i < n; i++) { h = (h * 48271) % 2147483647; w = Math.max(2, Math.min(100, w + ((h % 2001) / 1000 - 1) * spanne * 0.35)); aus.push(Math.round(w)); }
  return aus;
}

// ── Schale ──────────────────────────────────────────────────────────────
const SEITEN = { uebersicht: 'uebersicht.html', auftraege: 'auftraege.html', knoten: 'knoten.html', dienste: 'dienste.html', modelle: 'modelle.html',
                 anwendungen: 'anwendungen.html', regeln: 'regeln.html', nachrichten: 'nachrichten.html', verlauf: 'verlauf.html', sicherheit: 'sicherheit.html',
                 protokoll: 'protokoll.html', einstellungen: 'einstellungen.html', hilfe: 'hilfe.html' };

// Pillen in der Seitenleiste zeigen nur, wo etwas Bedeutsames passiert (nie Gesamtzahlen):
// [Name, Symbol, Schlüssel, Pille, Symbolfarbe, Pillenklasse, Erklärung der Pille]
const NAVI = [
  ['Übersicht', 'fa-tower-observation', 'uebersicht', null],
  ['Aufträge', 'fa-list-check', 'auftraege', '3', '#ffb52e', 'akzent', '3 Aufträge laufen, 2 warten'],
  ['Knoten', 'fa-server', 'knoten', '1', null, 'gefahr', '1 Knoten nicht erreichbar: Pi Werkstatt'],
  ['Dienste', 'fa-plug', 'dienste', '1', null, 'warnung', '1 Dienst pausiert: Bildschmiede'],
  ['Modelle', 'fa-brain', 'modelle', '1', null, 'info', '1 Auftrag wartet auf ein Modell, das nicht in den Speicher passt'],
  ['Anwendungen', 'fa-cubes', 'anwendungen', '2', null, 'neutral', '2 Anwendungen getrennt: Mitschrift, Pinnwand'],
  ['Regeln', 'fa-scale-balanced', 'regeln', null],
  ['Nachrichtenverkehr', 'fa-right-left', 'nachrichten', null],
  ['Verlauf', 'fa-chart-line', 'verlauf', null],
  ['Sicherheit', 'fa-shield-halved', 'sicherheit', null],
];
const SYSTEM = [
  ['Protokoll', 'fa-terminal', 'protokoll', '1', null, 'gefahr', '1 Fehler heute: Codehilfe, Modell konnte nicht geladen werden'],
  ['Einstellungen', 'fa-gear', 'einstellungen', null],
  ['Hilfe', 'fa-circle-question', 'hilfe', null],
];

const LAGE = { ruhig: ['ruhig', 'Lage ruhig', 'Alle Knoten erreichbar, keine Wartezeiten.'],
               angespannt: ['angespannt', 'Lage angespannt', 'Speicher auf Mac Studio zu 96 Prozent belegt; ein Auftrag wartet auf Speicher.'],
               engpass: ['engpass', 'Engpass', 'Mehrere Aufträge warten auf Speicher; ein Knoten ist nicht erreichbar.'],
               auslaufen: ['auslaufen', 'Läuft aus', 'Hauptregler auf Auslaufen: laufende Aufträge enden, nichts Neues wird angenommen.'],
               halt: ['halt', 'Gestoppt', 'Hauptregler auf Halt: alle Aufträge gestoppt, nichts wird angenommen.'] };

// Hauptregler im Kopf: Normal, Auslaufen (sanft), Halt (harter Schnitt) und Hintergrund an oder aus
function hauptregler(optionen) {
  const modus = optionen.modus || 'normal';
  const hg = optionen.hintergrund !== false;
  const stufe = (wert, symbol, wort, titel) => `<button class="${wert}${modus === wert ? ' an' : ''}" data-modus="${wert}" title="${titel}"><i class="fa-solid ${symbol}"></i><span>${wort}</span></button>`;
  return `<div class="hauptregler" data-modus="${modus}" title="Hauptregler: wirkt sofort auf den ganzen Verbund">
      <span class="etikett">Betrieb</span>
      <span class="stufen">
        ${stufe('normal', 'fa-play', 'Normal', 'Normalbetrieb: Aufträge werden angenommen und verteilt')}
        ${stufe('auslaufen', 'fa-person-walking-arrow-right', 'Auslaufen', 'Sanft: laufende Aufträge rechnen zu Ende, neue werden nicht mehr angenommen; Anwendungen bekommen das Signal gesperrt')}
        ${stufe('halt', 'fa-hand', 'Halt', 'Harter Schnitt: alle laufenden Aufträge stoppen sofort, Anwendungen bekommen den bisherigen Stand; braucht eine Bestätigung')}
      </span>
      <label class="hintergrund" title="Hintergrund-Aufträge (Stapelarbeit) anhalten oder laufen lassen; interaktive Aufträge sind nicht betroffen">
        <button class="schalter${hg ? ' an' : ''}" data-hintergrund></button>Hintergrund
      </label>
    </div>`;
}

const LEISTE_TEXT = {
  halt: ['fa-hand', 'Alles sofort stoppen?', ['3 laufende Aufträge brechen ab; die Anwendungen bekommen den bisherigen Stand (Zusage 1.240 Token Text, TubeVault 58 von 141 Abschnitten, Fundus 1.091 von 1.240 Einbettungen).', 'Wartende und pausierte Aufträge bleiben in der Warteschlange. Zurück zu Normal nimmt sie wieder auf.'], 'Ja, alles stoppen', 'gefahr-voll'],
  auslaufen: ['fa-person-walking-arrow-right', 'Auslaufen lassen?', ['3 laufende Aufträge rechnen zu Ende (längster: TubeVault, etwa 22 Minuten); danach ist der Verbund frei.', 'Neue Aufträge werden abgelehnt, die Anwendungen bekommen das Signal gesperrt mit Grund.'], 'Ja, auslaufen lassen', 'warnung'],
};
function hauptreglerLeiste(art) {
  const [symbol, frage, folgen, knopf, klasse] = LEISTE_TEXT[art];
  return `<div class="hauptregler-leiste ${art}" data-leiste>
      <i class="fa-solid ${symbol}"></i>
      <div class="folgen"><b>${frage}</b>${folgen.map(f => `<span>${f}</span>`).join('')}</div>
      <div class="rechts">
        <input class="eingabe" style="height:36px;width:340px" placeholder="Grund für die Anwendungen" title="Optional; steht im Signal an die Anwendungen im Feld grund">
        <button class="knopf klein ohne" data-leiste-abbruch>Abbrechen</button>
        <button class="knopf klein ${klasse}" data-leiste-ja><i class="fa-solid ${symbol}"></i> ${knopf}</button>
      </div>
    </div>`;
}

function schale(aktiv, optionen = {}) {
  const lage = LAGE[optionen.modus === 'halt' ? 'halt' : optionen.modus === 'auslaufen' ? 'auslaufen' : (optionen.lage || 'angespannt')];
  const navi = ([name, symbol, schluessel, z, farbe, klasse, erklaerung]) =>
    `<a class="navi${schluessel === aktiv ? ' aktiv' : ''}" href="${SEITEN[schluessel] || '#'}">
      <i class="fa-solid ${symbol}"${farbe ? ` style="--symbolfarbe: ${farbe}"` : ''}></i>${name}${z ? `<span class="zaehler pille ${klasse || ''}" title="${erklaerung || ''}">${z}</span>` : ''}</a>`;
  const kopf = document.querySelector('[data-block="kopf"]');
  if (kopf) kopf.outerHTML = `
    <header class="kopf">
      <div class="marke"><img class="marke-bild" src="symbol-frei.svg" alt=""><span class="marke-name">${APP.name}</span><span class="zahl">${APP.version}</span></div>
      <label class="suche"><i class="fa-solid fa-magnifying-glass"></i><input placeholder="Aufträge, Knoten, Modelle durchsuchen"></label>
      ${hauptregler(optionen)}
      <div class="kopf-aktionen">
        <span class="lage ${lage[0]}" title="${lage[2]}"><span class="punkt lebt"></span>${lage[1]}</span>
        <button class="knopf ohne symbol" title="Protokoll als schwebendes Fenster öffnen"><i class="fa-solid fa-terminal"></i></button>
        <button class="knopf ohne symbol" title="Hilfe als schwebendes Fenster öffnen"><i class="fa-solid fa-circle-question"></i></button>
      </div>
    </header>`;
  const seite = document.querySelector('[data-block="seite"]');
  if (seite) seite.outerHTML = `
    <nav class="seite">
      ${NAVI.map(navi).join('')}
      <div class="etikett">System</div>
      ${SYSTEM.map(navi).join('')}
    </nav>`;
  const fuss = document.querySelector('[data-block="fuss"]');
  if (fuss) fuss.outerHTML = `
    <footer class="fuss">
      <span><i class="fa-solid fa-circle-play"></i>&nbsp; <span class="zahl">3</span> Aufträge laufen · <span class="zahl">2</span> warten</span>
      <span><i class="fa-solid fa-memory"></i>&nbsp; Mac Studio <span class="zahl">96 %</span> Speicher</span>
      <span><i class="fa-solid fa-cloud"></i>&nbsp; Extern heute <span class="zahl">0,42 Euro</span></span>
      <div class="rechts">
        <span title="Knoten-Agenten, die sich in den letzten 15 Sekunden gemeldet haben"><span class="punkt"></span>5 von 6 Knoten</span>
        <span title="Verbindung dieser Oberfläche zur Leitstelle"><span class="punkt lebt"></span>Live</span>
        <span class="schwach zahl">${APP.version}</span>
      </div>
    </footer>`;
}

// Umschalter zum Vergleichen: Thema und Schriftstufe, gemerkt über alle Entwürfe
function entwurfSchalter() {
  const merken = (k, v) => { try { localStorage.setItem('ls-entwurf-' + k, v); } catch {} };
  const lesen = (k, s) => { try { return localStorage.getItem('ls-entwurf-' + k) || s; } catch { return s; } };
  const gruppen = {
    theme: [['dunkel', 'Dunkel'], ['hell', 'Hell']],
    schrift: [['klein', 'Klein'], ['mittel', 'Mittel'], ['gross', 'Groß']],
    palette: [['sanft', 'Sanft'], ['kraeftig', 'Kräftig'], ['leuchtend', 'Leuchtend']],
    flaechen: [['blaugrau', 'Blaugrau'], ['tiefblau', 'Tiefblau']],
    blau: [['himmel', 'Himmel'], ['koenig', 'Königsblau'], ['azur', 'Azur'], ['kornblume', 'Kornblume']],
  };
  const namen = { theme: 'Thema', schrift: 'Schrift', palette: 'Farben', flaechen: 'Flächen', blau: 'Blau' };
  const standard = { theme: 'dunkel', schrift: 'gross', palette: 'kraeftig', flaechen: 'blaugrau', blau: 'koenig' };
  const abfrage = new URLSearchParams(location.search);
  const box = document.createElement('div');
  box.className = 'entwurf-schalter';
  for (const [gruppe, werte] of Object.entries(gruppen)) {
    const zeile = document.createElement('div');
    zeile.innerHTML = `<span>${namen[gruppe]}</span>`;
    for (const [wert, name] of werte) {
      const b = document.createElement('button');
      b.textContent = name;
      b.onclick = () => { setze(gruppe, wert); merken(gruppe, wert); };
      b.dataset.gruppe = gruppe; b.dataset.wert = wert;
      zeile.append(b);
    }
    box.append(zeile);
  }
  function setze(gruppe, wert) {
    document.documentElement.dataset[gruppe] = wert;
    box.querySelectorAll(`[data-gruppe="${gruppe}"]`).forEach(b => b.classList.toggle('an', b.dataset.wert === wert));
  }
  document.body.append(box);
  for (const gruppe of Object.keys(gruppen)) setze(gruppe, abfrage.get(gruppe) || lesen(gruppe, standard[gruppe]));
  if (abfrage.has('ohne-schalter')) box.remove();
}

function hauptreglerVerhalten(optionen) {
  const regler = document.querySelector('.hauptregler'); if (!regler) return;
  const zeigeLeiste = (art) => { document.querySelector('[data-leiste]')?.remove(); document.body.insertAdjacentHTML('beforeend', hauptreglerLeiste(art));
    const l = document.querySelector('[data-leiste]');
    l.querySelector('[data-leiste-abbruch]').onclick = () => l.remove();
    l.querySelector('[data-leiste-ja]').onclick = () => { setze(art); l.remove(); }; };
  const setze = (modus) => { regler.dataset.modus = modus; regler.querySelectorAll('.stufen button').forEach(b => b.classList.toggle('an', b.dataset.modus === modus));
    const lage = document.querySelector('.lage'); if (lage) { const l = LAGE[modus === 'normal' ? (optionen.lage || 'angespannt') : modus]; lage.className = `lage ${l[0]}`; lage.title = l[2]; lage.innerHTML = `<span class="punkt lebt"></span>${l[1]}`; } };
  regler.querySelectorAll('.stufen button').forEach(b => b.onclick = () => { const m = b.dataset.modus; if (m === 'normal') setze('normal'); else zeigeLeiste(m); });
  regler.querySelector('[data-hintergrund]').onclick = (e) => e.currentTarget.classList.toggle('an');
  if (optionen.leiste) zeigeLeiste(optionen.leiste);
}

export function seite(aktiv, optionen = {}) {
  schale(aktiv, optionen);
  hauptreglerVerhalten(optionen);
  entwurfSchalter();
}
