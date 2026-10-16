<script lang="ts">
  import { ansicht } from '../lib/ansicht.svelte';
  import { kanal } from '../lib/kanal.svelte';
  import { weg, type Seite } from '../lib/weg.svelte';

  // Pillen nur, wo etwas Bedeutsames passiert; nie Gesamtzahlen
  const bild = $derived(kanal.lagebild);
  const pillen = $derived.by(() => {
    const p: Partial<Record<Seite, { zahl: number; klasse: string; satz: string }>> = {};
    if (!bild) return p;
    const wartend = bild.auftraege.filter((a) => a.zustand === 'eingereiht' || a.zustand === 'wartet_speicher').length;
    if (wartend) p.auftraege = { zahl: wartend, klasse: 'warnung', satz: `${wartend} Aufträge warten` };
    const aus = bild.knoten.filter((k) => !k.erreichbar);
    if (aus.length) p.knoten = { zahl: aus.length, klasse: 'gefahr', satz: `Nicht erreichbar: ${aus.map((k) => k.name).join(', ')}` };
    const dienstAus = bild.dienste.filter((d) => d.zustand === 'nicht_erreichbar');
    if (dienstAus.length) p.dienste = { zahl: dienstAus.length, klasse: 'gefahr', satz: `Nicht erreichbar: ${dienstAus.map((d) => d.name).join(', ')}` };
    const jetzt = kanal.jetzt();
    const gesperrt = bild.modelle.filter((m) => m.ladesperre_bis_s && m.ladesperre_bis_s > jetzt);
    if (gesperrt.length) p.modelle = { zahl: gesperrt.length, klasse: 'warnung', satz: `Laden abgelehnt: ${gesperrt.map((m) => m.name).join(', ')}` };
    const apps = bild.anwendungen.filter((a) => a.gesperrt);
    if (apps.length) p.anwendungen = { zahl: apps.length, klasse: 'neutral', satz: `Gesperrt: ${apps.map((a) => a.name).join(', ')}` };
    return p;
  });

  const NAVI: [string, string, Seite][] = [
    ['Übersicht', 'fa-tower-observation', 'uebersicht'],
    ['Aufträge', 'fa-list-check', 'auftraege'],
    ['Knoten', 'fa-server', 'knoten'],
    ['Dienste', 'fa-plug', 'dienste'],
    ['Modelle', 'fa-brain', 'modelle'],
    ['Anwendungen', 'fa-cubes', 'anwendungen'],
  ];
  const SYSTEM: [string, string, Seite][] = [['Protokoll', 'fa-terminal', 'protokoll']];
  const aktiv = (s: Seite) => weg.seite === s || (s === 'dienste' && weg.seite === 'anschluss');
</script>

{#snippet eintrag(name: string, symbol: string, seite: Seite)}
  <a class="navi" class:aktiv={aktiv(seite)} href={weg.pfad(seite)} onclick={(e) => weg.klick(e, seite)} title={name}>
    <i class="fa-solid {symbol}"></i>{name}
    {#if pillen[seite]}<span class="zaehler pille {pillen[seite]?.klasse}" title={pillen[seite]?.satz}>{pillen[seite]?.zahl}</span>{/if}
  </a>
{/snippet}

<nav class="seite">
  {#each NAVI as [name, symbol, seite] (seite)}{@render eintrag(name, symbol, seite)}{/each}
  <div class="etikett">System</div>
  {#each SYSTEM as [name, symbol, seite] (seite)}{@render eintrag(name, symbol, seite)}{/each}

  <div class="ansicht">
    <div class="etikett">Ansicht</div>
    <span class="stufen" title="Thema dieser Oberfläche auf diesem Gerät">
      <button class:an={ansicht.thema === 'dunkel'} onclick={() => ansicht.setzeThema('dunkel')}>Dunkel</button>
      <button class:an={ansicht.thema === 'hell'} onclick={() => ansicht.setzeThema('hell')}>Hell</button>
    </span>
    <span class="stufen" title="Schriftgröße auf diesem Gerät">
      <button class:an={ansicht.schrift === 'normal'} onclick={() => ansicht.setzeSchrift('normal')}>Normal</button>
      <button class:an={ansicht.schrift === 'gross'} onclick={() => ansicht.setzeSchrift('gross')}>Groß</button>
      <button class:an={ansicht.schrift === 'sehr-gross'} onclick={() => ansicht.setzeSchrift('sehr-gross')}>Sehr groß</button>
    </span>
  </div>
</nav>
