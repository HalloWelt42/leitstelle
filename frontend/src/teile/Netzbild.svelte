<script lang="ts">
  // Netzbild wie im Entwurf (mockups/netzbild.js), aber aus dem Lagebild: Anwendungen links, Leitstelle in der
  // Mitte, Rechner und Dienste rechts. Laufende Aufträge als laufende Linie mit Paket, wartende als leise Linie.
  import { prozent } from '../lib/format';
  import type { AuftragSicht, Lagebild } from '../lib/typen.gen';
  import { AUFTRAGSZUSTAND, FAEHIGKEIT, KNOTENZUSTAND } from '../lib/wort';

  // kuerzlich: Anwendungen mit einer Auftragsbewegung in den letzten Sekunden (aus dem Kanal). Kurze Aufträge
  // sind fertig, bevor ein Lagebild sie als laufend zeigt; sie leuchten so trotzdem sichtbar nach.
  type Bewegung = { knoten: string | null; extern: boolean; faehigkeit: string };
  let { bild, kuerzlich = {} }: { bild: Lagebild; kuerzlich?: Record<string, Bewegung> } = $props();

  // Was eine Linie braucht: ein offener Auftrag oder eine kürzliche Bewegung
  type Fluss = Pick<AuftragSicht, 'kennung' | 'anwendung' | 'faehigkeit' | 'prioritaet' | 'zustand' | 'knoten' | 'extern'>;

  const B = 900, LINKS_X = 16, LINKS_B = 178, MITTE_X = 330, MITTE_B = 236, RECHTS_X = 668, RECHTS_B = 216;
  const H_APP = 50, ABSTAND_APP = 12, ABSTAND_KN = 14;
  const bogen = (x1: number, y1: number, x2: number, y2: number) => { const m = (x1 + x2) / 2; return `M${x1},${y1} C${m},${y1} ${m},${y2} ${x2},${y2}`; };
  const tempo = (a: { prioritaet: number }) => (a.prioritaet >= 2 ? '1.0s' : a.prioritaet === 0 ? '2.6s' : '1.6s');

  interface Spalte { kennung: string; name: string; zeile: string; extern: boolean; erreichbar: boolean; belegt: number | null; dienste: string[] }

  const plan = $derived.by(() => {
    const offen = bild.auftraege;
    const mitAuftrag = new Set(offen.map((a) => a.anwendung));
    const apps = [...bild.anwendungen].sort((x, y) => Number(mitAuftrag.has(y.kennung)) - Number(mitAuftrag.has(x.kennung)) || x.name.localeCompare(y.name, 'de')).slice(0, 8);
    const rechts: Spalte[] = bild.knoten.map((k) => ({
      kennung: k.kennung, name: k.name, zeile: k.erreichbar ? `${prozent(k.belegt_anteil)} Speicher belegt` : KNOTENZUSTAND[k.zustand].satz, extern: false, erreichbar: k.erreichbar,
      belegt: k.belegt_anteil, dienste: bild.dienste.filter((d) => d.knoten === k.kennung).map((d) => d.name),
    }));
    const extern = bild.dienste.filter((d) => d.extern);
    if (extern.length) rechts.push({ kennung: 'extern', name: 'Extern', zeile: 'Anbieter im Internet', extern: true, erreichbar: true, belegt: null, dienste: extern.map((d) => d.name) });
    const hKn = (s: Spalte) => 58 + s.dienste.length * 23 + (s.belegt != null ? 18 : 0);
    const hLinks = apps.length * H_APP + Math.max(0, apps.length - 1) * ABSTAND_APP;
    const hRechts = rechts.reduce((s, k) => s + hKn(k), 0) + Math.max(0, rechts.length - 1) * ABSTAND_KN;
    const H = Math.max(hLinks, hRechts, 300) + 60;
    const mitteY = H / 2;
    let y = (H - hLinks) / 2;
    const posApp = new Map<string, number>();
    for (const a of apps) { posApp.set(a.kennung, y); y += H_APP + ABSTAND_APP; }
    y = (H - hRechts) / 2;
    const posKn = new Map<string, { y: number; h: number }>();
    for (const k of rechts) { const h = hKn(k); posKn.set(k.kennung, { y, h }); y += h + ABSTAND_KN; }
    const ort = (a: Fluss) => (a.extern ? 'extern' : a.knoten);
    // je Anwendung der wichtigste offene Auftrag (laufend vor wartend), sonst die kürzliche Bewegung
    const fluesse: Fluss[] = [...offen];
    for (const [anwendung, b] of Object.entries(kuerzlich)) {
      if (!offen.some((a) => a.anwendung === anwendung)) {
        fluesse.push({ kennung: `nach-${anwendung}`, anwendung, faehigkeit: b.faehigkeit as Fluss['faehigkeit'], prioritaet: 1, zustand: 'laeuft', knoten: b.knoten, extern: b.extern });
      }
    }
    const jeApp = new Map<string, Fluss>();
    for (const a of fluesse) { const bisher = jeApp.get(a.anwendung); if (!bisher || (a.zustand === 'laeuft' && bisher.zustand !== 'laeuft')) jeApp.set(a.anwendung, a); }
    const jeKnoten = new Map<string, Fluss[]>();
    for (const a of fluesse) { const o = ort(a); if (a.zustand === 'laeuft' && o) jeKnoten.set(o, [...(jeKnoten.get(o) ?? []), a]); }
    return { apps, rechts, H, mitteY, posApp, posKn, jeApp, jeKnoten };
  });

  const laufend = $derived(bild.auftraege.filter((a) => a.zustand === 'laeuft'));
  const wartend = $derived(bild.auftraege.filter((a) => a.zustand !== 'laeuft'));
  const lastKlasse = (b: number) => (b >= 0.92 ? ' gefahr' : b >= 0.8 ? ' warnung' : '');
</script>

<svg class="netz" viewBox="0 0 {B} {plan.H}" role="img" aria-label="Netzbild: Anwendungen, Leitstelle, Knoten">
  {#each plan.apps as a (a.kennung)}
    {@const y = plan.posApp.get(a.kennung) ?? 0}
    <path class="leitung" d={bogen(LINKS_X + LINKS_B, y + H_APP / 2, MITTE_X, plan.mitteY)}></path>
  {/each}
  {#each plan.rechts as k (k.kennung)}
    {@const p = plan.posKn.get(k.kennung)!}
    <path class="leitung" d={bogen(MITTE_X + MITTE_B, plan.mitteY, RECHTS_X, p.y + p.h / 2)} stroke-dasharray={k.erreichbar ? undefined : '3 6'} opacity={k.erreichbar ? undefined : 0.5}></path>
  {/each}

  {#each [...plan.jeApp] as [app, a], n (app)}
    {@const y = plan.posApp.get(app)}
    {#if y !== undefined}
      <path class="fluss" class:leise={a.zustand !== 'laeuft'} id="nf{n}" d={bogen(LINKS_X + LINKS_B, y + H_APP / 2, MITTE_X, plan.mitteY)}
            style="--fluss-farbe:{FAEHIGKEIT[a.faehigkeit].farbe};--tempo:{tempo(a)}"></path>
      {#if a.zustand === 'laeuft'}
        <circle class="paket" r="5" style="--fluss-farbe:{FAEHIGKEIT[a.faehigkeit].farbe}">
          <animateMotion dur="{(2.4 + n * 0.4).toFixed(1)}s" repeatCount="indefinite" begin="{(n * 0.7).toFixed(1)}s"><mpath href="#nf{n}" /></animateMotion>
        </circle>
      {/if}
    {/if}
  {/each}
  {#each [...plan.jeKnoten] as [kn, liste] (kn)}
    {@const p = plan.posKn.get(kn)}
    {#if p}
      {#each liste as a, i (a.kennung)}
        {@const dy = (i - (liste.length - 1) / 2) * 10}
        <path class="fluss" id="nk{a.kennung}" d={bogen(MITTE_X + MITTE_B, plan.mitteY + dy, RECHTS_X, p.y + p.h / 2 + dy)}
              style="--fluss-farbe:{FAEHIGKEIT[a.faehigkeit].farbe};--tempo:{a.prioritaet === 0 ? '2.6s' : '1.3s'}"></path>
        <circle class="paket" r="5" style="--fluss-farbe:{FAEHIGKEIT[a.faehigkeit].farbe}">
          <animateMotion dur="{(2.2 + i * 0.5).toFixed(1)}s" repeatCount="indefinite" begin="{(i * 0.9).toFixed(1)}s"><mpath href="#nk{a.kennung}" /></animateMotion>
        </circle>
      {/each}
    {/if}
  {/each}

  {#each plan.apps as a (a.kennung)}
    {@const y = plan.posApp.get(a.kennung) ?? 0}
    {@const auftrag = plan.jeApp.get(a.kennung)}
    <g class="knoten" class:aktiv={auftrag?.zustand === 'laeuft'} class:aus={a.gesperrt} transform="translate({LINKS_X},{y})">
      <title>{a.name}: {a.gesperrt ? 'gesperrt' : auftrag ? (auftrag.kennung.startsWith('nach-') ? 'hat gerade gearbeitet' : AUFTRAGSZUSTAND[auftrag.zustand].wort) : 'bereit'}</title>
      <rect width={LINKS_B} height={H_APP} rx="3"></rect>
      <text x="14" y="22" style="font-weight:600">{a.name}</text>
      <text x="14" y="41" class="klein">{a.gesperrt ? 'Gesperrt' : auftrag ? (auftrag.kennung.startsWith('nach-') ? 'Arbeitet' : AUFTRAGSZUSTAND[auftrag.zustand].wort) : 'Bereit'}</text>
      {#if auftrag}<circle cx={LINKS_B - 16} cy="25" r="5" fill={FAEHIGKEIT[auftrag.faehigkeit].farbe}></circle>{/if}
    </g>
  {/each}

  <g class="knoten aktiv" transform="translate({MITTE_X},{plan.mitteY - 103})">
    <rect width={MITTE_B} height="206" rx="3"></rect>
    <text x="18" y="32" style="font-weight:700;font-size:20px">Leitstelle</text>
    <text x="18" y="55" class="klein">Vermittlung und Warteschlange</text>
    <text x="18" y="92" class="klein">Laufen</text><text x={MITTE_B - 18} y="92" class="zahl" text-anchor="end" style="font-weight:700">{laufend.length}</text>
    <text x="18" y="118" class="klein">Warten</text><text x={MITTE_B - 18} y="118" class="zahl" text-anchor="end" style="font-weight:700">{wartend.length}</text>
    <text x="18" y="144" class="klein">Maßnahmen</text><text x={MITTE_B - 18} y="144" class="zahl" text-anchor="end" style="font-weight:700">{bild.massnahmen.filter((m) => m.zustand === 'ausgefuehrt').length}</text>
    <rect class="last-grund" x="18" y="164" width={MITTE_B - 36} height="9" rx="1"></rect>
    {#each wartend.slice(0, 13) as a, i (a.kennung)}
      <rect x={18 + i * 15} y="164" width="11" height="9" rx="1" fill={FAEHIGKEIT[a.faehigkeit].farbe}><title>{a.titel}: {a.begruendung}</title></rect>
    {/each}
    <text x="18" y="192" class="klein" style="font-size:15px">Warteschlange</text>
  </g>

  {#each plan.rechts as k (k.kennung)}
    {@const p = plan.posKn.get(k.kennung)!}
    {@const rechnet = (plan.jeKnoten.get(k.kennung) ?? []).length > 0}
    <g class="knoten" class:aus={!k.erreichbar} class:aktiv={rechnet} transform="translate({RECHTS_X},{p.y})">
      <title>{k.name}: {k.zeile}</title>
      <rect width={RECHTS_B} height={p.h} rx="3"></rect>
      <text x="14" y="23" style="font-weight:600">{k.name}</text>
      <text x="14" y="42" class="klein">{k.zeile}</text>
      {#if rechnet}<circle class="herz" cx={RECHTS_B - 18} cy="19" r="5"></circle>{/if}
      {#each k.dienste as d, i (d + i)}
        <text x="22" y={66 + i * 23} class="klein" style="font-size:15px">• {d.length > 24 ? d.slice(0, 22) + '...' : d}</text>
      {/each}
      {#if k.belegt != null}
        {@const yy = 60 + k.dienste.length * 23}
        <rect class="last-grund" x="14" y={yy + 8} width={RECHTS_B - 28} height="7" rx="1"></rect>
        <rect class="last{lastKlasse(k.belegt)}" x="14" y={yy + 8} width={((RECHTS_B - 28) * Math.min(1, k.belegt)).toFixed(1)} height="7" rx="1"></rect>
      {/if}
    </g>
  {/each}

  <text x={LINKS_X} y="22" class="klein" style="font-size:15px;letter-spacing:.08em;text-transform:uppercase;font-weight:700">Anwendungen</text>
  <text x={RECHTS_X} y="22" class="klein" style="font-size:15px;letter-spacing:.08em;text-transform:uppercase;font-weight:700">Knoten und Dienste</text>
</svg>
