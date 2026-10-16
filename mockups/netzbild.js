// Leitstelle - Netzbild: Anwendungen links, Leitstelle in der Mitte, Knoten rechts.
// Lebendig durch laufende Strichlinien (Richtung der Arbeit, Tempo nach Last),
// wandernde Pakete (Aufträge unterwegs) und atmende Herzpunkte an rechnenden Knoten.
// Reine SVG-Erzeugung aus Daten, damit Übersicht, Engpass und Knotenseiten
// dasselbe Bild in anderen Zuständen zeigen.
import { KNOTEN, ANWENDUNGEN, AUFTRAEGE, WORT, knoten as knotenVon } from './gemeinsam.js';

const FARBE = { text: 'var(--ls-himmel)', einbettung: 'var(--ls-petrol)', uebersetzen: 'var(--ls-tuerkis)', hoeren: 'var(--ls-minze)',
                bild: 'var(--ls-flieder)', musik: 'var(--ls-violett)', stimme: 'var(--ls-rose)', werkzeug: 'var(--ls-sand)' };

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');

// Weiche Verbindung von links nach rechts
const bogen = (x1, y1, x2, y2) => { const m = (x1 + x2) / 2; return `M${x1},${y1} C${m},${y1} ${m},${y2} ${x2},${y2}`; };

/**
 * optionen: { anwendungen: [kennungen], knoten: [kennungen], auftraege: [...], breite, leer }
 */
export function netzbild(ziel, optionen = {}) {
  const apps = (optionen.anwendungen || ANWENDUNGEN.filter(a => a.zustand === 'verbunden').map(a => a.kennung).slice(0, 8)).map(k => ANWENDUNGEN.find(a => a.kennung === k));
  const kn = (optionen.knoten || KNOTEN.map(k => k.kennung)).map(k => knotenVon(k));
  const auftraege = optionen.auftraege || AUFTRAEGE;
  const B = 900, LINKS_X = 16, LINKS_B = 178, MITTE_X = 330, MITTE_B = 236, RECHTS_X = 668, RECHTS_B = 216;

  // Höhen: links 46 je Anwendung, rechts je Knoten nach Diensten
  const hApp = 50, gapApp = 12;
  const hoeheKnoten = (k) => 58 + Math.max(0, k.dienste.length) * 23 + (k.ram_gb ? 18 : 0);
  const gapKn = 14;
  const hLinks = apps.length * hApp + (apps.length - 1) * gapApp;
  const hRechts = kn.reduce((s, k) => s + hoeheKnoten(k), 0) + (kn.length - 1) * gapKn;
  const H = Math.max(hLinks, hRechts, 300) + 60;
  const mitteY = H / 2;

  // Positionen
  let y = (H - hLinks) / 2;
  const posApp = new Map();
  for (const a of apps) { posApp.set(a.kennung, { x: LINKS_X, y, h: hApp }); y += hApp + gapApp; }
  y = (H - hRechts) / 2;
  const posKn = new Map();
  for (const k of kn) { const h = hoeheKnoten(k); posKn.set(k.kennung, { x: RECHTS_X, y, h }); y += h + gapKn; }

  // Flüsse aus den Aufträgen
  const laufend = auftraege.filter(a => a.zustand === 'laeuft');
  const wartend = auftraege.filter(a => a.zustand === 'wartet' || a.zustand === 'wartet_speicher');
  const flussApp = new Map(); const flussKn = new Map();
  for (const a of laufend) { flussApp.set(a.anwendung, a); flussKn.set(a.knoten, [...(flussKn.get(a.knoten) || []), a]); }
  for (const a of wartend) if (!flussApp.has(a.anwendung)) flussApp.set(a.anwendung, a);

  const teile = [];
  // Leitungen (ruhig) zu allen verbundenen Anwendungen und erreichbaren Knoten
  for (const a of apps) { const p = posApp.get(a.kennung); teile.push(`<path class="leitung" d="${bogen(p.x + LINKS_B, p.y + p.h / 2, MITTE_X, mitteY)}"></path>`); }
  for (const k of kn) { const p = posKn.get(k.kennung); teile.push(`<path class="leitung" d="${bogen(MITTE_X + MITTE_B, mitteY, p.x, p.y + p.h / 2)}"${k.zustand === 'aus' ? ' stroke-dasharray="3 6" opacity="0.5"' : ''}></path>`); }
  // Flüsse mit Paketen
  let n = 0;
  for (const [app, a] of flussApp) {
    const p = posApp.get(app); if (!p) continue;
    const d = bogen(p.x + LINKS_B, p.y + p.h / 2, MITTE_X, mitteY);
    const tempo = a.prioritaet === 'dringend' || a.prioritaet === 'hoch' ? '1.0s' : a.prioritaet === 'hintergrund' ? '2.6s' : '1.6s';
    const leise = a.zustand !== 'laeuft';
    teile.push(`<path class="fluss${leise ? ' leise' : ''}" id="f${n}" d="${d}" style="--fluss-farbe:${FARBE[a.faehigkeit]};--tempo:${tempo}"></path>`);
    if (!leise) teile.push(`<circle class="paket" r="5" style="--fluss-farbe:${FARBE[a.faehigkeit]}"><animateMotion dur="${(2.4 + n * 0.4).toFixed(1)}s" repeatCount="indefinite" begin="${(n * 0.7).toFixed(1)}s"><mpath href="#f${n}"/></animateMotion></circle>`);
    n++;
  }
  for (const [kz, liste] of flussKn) {
    const p = posKn.get(kz); if (!p) continue;
    liste.forEach((a, i) => {
      const dy = (i - (liste.length - 1) / 2) * 10;
      const d = bogen(MITTE_X + MITTE_B, mitteY + dy, p.x, p.y + p.h / 2 + dy);
      teile.push(`<path class="fluss" id="g${n}" d="${d}" style="--fluss-farbe:${FARBE[a.faehigkeit]};--tempo:${a.prioritaet === 'hintergrund' ? '2.6s' : '1.3s'}"></path>`);
      teile.push(`<circle class="paket" r="5" style="--fluss-farbe:${FARBE[a.faehigkeit]}"><animateMotion dur="${(2.2 + i * 0.5).toFixed(1)}s" repeatCount="indefinite" begin="${(i * 0.9).toFixed(1)}s"><mpath href="#g${n}"/></animateMotion></circle>`);
      n++;
    });
  }

  // Anwendungen
  for (const a of apps) {
    const p = posApp.get(a.kennung); const job = flussApp.get(a.kennung);
    const z = job ? (job.zustand === 'laeuft' ? WORT.zustand[job.zustand] : WORT.zustand[job.zustand]) : 'bereit';
    teile.push(`<g class="knoten${job && job.zustand === 'laeuft' ? ' aktiv' : ''}" transform="translate(${p.x},${p.y})">
      <title>${esc(a.name)}: ${esc(z)}${job ? ' - ' + esc(job.titel) : ''}</title>
      <rect width="${LINKS_B}" height="${p.h}" rx="3"></rect>
      <text x="14" y="22" style="font-weight:600">${esc(a.name)}</text>
      <text x="14" y="41" class="klein">${esc(z)}</text>
      ${job ? `<circle cx="${LINKS_B - 16}" cy="25" r="5" fill="${FARBE[job.faehigkeit]}"></circle>` : ''}
    </g>`);
  }

  // Leitstelle in der Mitte
  const mh = 206, my = mitteY - mh / 2;
  teile.push(`<g class="knoten aktiv" transform="translate(${MITTE_X},${my})">
    <rect width="${MITTE_B}" height="${mh}" rx="3"></rect>
    <text x="18" y="32" style="font-weight:700;font-size:20px">Leitstelle</text>
    <text x="18" y="55" class="klein">Vermittlung und Warteschlange</text>
    <text x="18" y="92" class="klein">Laufen</text><text x="${MITTE_B - 18}" y="92" class="zahl" text-anchor="end" style="font-weight:700">${laufend.length}</text>
    <text x="18" y="118" class="klein">Warten</text><text x="${MITTE_B - 18}" y="118" class="zahl" text-anchor="end" style="font-weight:700">${wartend.length}</text>
    <text x="18" y="144" class="klein">Pausiert</text><text x="${MITTE_B - 18}" y="144" class="zahl" text-anchor="end" style="font-weight:700">${auftraege.filter(a => a.zustand === 'pausiert').length}</text>
    <rect class="last-grund" x="18" y="164" width="${MITTE_B - 36}" height="9" rx="1"></rect>
    ${wartend.map((a, i) => `<rect x="${18 + i * 15}" y="164" width="11" height="9" rx="1" fill="${FARBE[a.faehigkeit]}"><title>${esc(a.titel)} wartet</title></rect>`).join('')}
    <text x="18" y="192" class="klein" style="font-size:14px">Plätze in der Warteschlange</text>
  </g>`);

  // Knoten rechts
  for (const k of kn) {
    const p = posKn.get(k.kennung);
    const rechnet = (flussKn.get(k.kennung) || []).length > 0;
    const klasse = k.zustand === 'aus' ? ' aus' : k.zustand === 'wartung' ? ' wartung' : rechnet ? ' aktiv' : '';
    const ramKlasse = k.ram >= 92 ? ' gefahr' : k.ram >= 80 ? ' warnung' : '';
    let inner = `<rect width="${RECHTS_B}" height="${p.h}" rx="3"></rect>
      <text x="14" y="23" style="font-weight:600">${esc(k.name)}</text>
      <text x="14" y="42" class="klein">${esc(k.zustand === 'aus' ? (k.seit || 'nicht erreichbar') : k.beschreibung)}</text>
      ${rechnet ? `<circle class="herz" cx="${RECHTS_B - 18}" cy="19" r="5"></circle>` : ''}
      ${k.zone === 'fern' ? `<text x="${RECHTS_B - (rechnet ? 32 : 14)}" y="23" class="klein" text-anchor="end" style="font-size:14px">über VPN</text>` : ''}`;
    let yy = 60;
    for (const dk of k.dienste) {
      inner += `<text x="22" y="${yy + 6}" class="klein" style="font-size:15px">• ${esc(dienstName(dk))}</text>`;
      yy += 23;
    }
    if (k.ram_gb) {
      inner += `<text x="${RECHTS_B - 14}" y="${yy + 2}" class="klein zahl" text-anchor="end" style="font-size:14px">${k.ram} % Speicher</text>
        <rect class="last-grund" x="14" y="${yy + 8}" width="${RECHTS_B - 28}" height="7" rx="1"></rect>
        <rect class="last${ramKlasse}" x="14" y="${yy + 8}" width="${((RECHTS_B - 28) * k.ram / 100).toFixed(1)}" height="7" rx="1"><title>Speicher ${k.ram} Prozent von ${k.ram_gb} GB</title></rect>`;
    }
    teile.push(`<g class="knoten${klasse}" transform="translate(${p.x},${p.y})"><title>${esc(k.name)} (${esc(k.adresse)}): ${esc(WORT.zustand[k.zustand])}</title>${inner}</g>`);
  }

  // Spaltentitel
  teile.push(`<text x="${LINKS_X}" y="22" class="klein" style="font-size:14px;letter-spacing:.08em;text-transform:uppercase;font-weight:700">Anwendungen</text>`);
  teile.push(`<text x="${RECHTS_X}" y="22" class="klein" style="font-size:14px;letter-spacing:.08em;text-transform:uppercase;font-weight:700">Knoten und Dienste</text>`);

  ziel.innerHTML = `<svg class="netz" viewBox="0 0 ${B} ${H}" role="img" aria-label="Netzbild: Anwendungen, Leitstelle, Knoten">${teile.join('')}</svg>`;
}

const DIENST_NAMEN = { laeufer: 'Modell-Läufer', 'laeufer-32': 'Modell-Läufer (neu gestartet)', txt2voice: 'txt2voice', bildschmiede: 'Bildschmiede', 'whisper-32': 'Hörer', acestep: 'Klangschmiede', 'piper-pi': 'Sprecher', 'extern-anbieter': 'Externer Anbieter' };
const dienstName = (k) => DIENST_NAMEN[k] || k;
