<script lang="ts">
  // Eigenständige Telefonansicht (Entwurf mockups/mobil.html): nur Lage, Hauptregler, Aufträge stoppen, Knoten,
  // Meldungen. Alles mit Folgen nur mit Drücken und Halten. Regeln, Einrichtung und Diagnose bleiben am Rechner.
  import { api } from '../lib/api';
  import { dauer, gb, prozent, uhrzeit } from '../lib/format';
  import { kanal } from '../lib/kanal.svelte';
  import { tun } from '../lib/meldung.svelte';
  import type { Betriebsmodus } from '../lib/typen.gen';
  import { FAEHIGKEIT, KNOTENZUSTAND, LAGE, MODUS, knotenzustand } from '../lib/wort';
  import Halteknopf from '../teile/Halteknopf.svelte';
  import NeueFassung from '../teile/NeueFassung.svelte';
  import Speicherbalken from '../teile/Speicherbalken.svelte';

  type Blatt = 'lage' | 'auftraege' | 'knoten' | 'meldungen';
  let blatt = $state<Blatt>('lage');
  let wahl = $state<string | null>(null);
  let jetzt = $state(kanal.jetzt());
  $effect(() => {
    const t = setInterval(() => (jetzt = kanal.jetzt()), 1000);
    return () => clearInterval(t);
  });

  const bild = $derived(kanal.lagebild);
  const laufend = $derived(bild?.auftraege.filter((a) => a.zustand === 'laeuft') ?? []);
  const wartend = $derived(bild?.auftraege.filter((a) => a.zustand !== 'laeuft') ?? []);
  const lage = $derived(!bild ? { klasse: 'aus', wort: 'Getrennt' } : bild.modus !== 'normal' ? { klasse: bild.modus, wort: MODUS[bild.modus].lage } : LAGE[bild.lage]);
  const anwendung = (k: string) => bild?.anwendungen.find((a) => a.kennung === k)?.name ?? '';

  const stellen = (m: Betriebsmodus) => bild && tun(() => api.hauptregler(m, bild.hintergrund_erlaubt), `Hauptregler: ${MODUS[m].wort}`);
  const stoppen = (k: string, m: 'sofort' | 'auslaufen') => tun(() => api.stoppen(k, m, 'vom Telefon'), m === 'sofort' ? 'Gestoppt' : 'Läuft aus').then(() => (wahl = null));
</script>

<div class="seite-mobil telefonansicht">
  <header class="m-kopf">
    <img src="/symbol-frei.svg" alt="" /><b>Leitstelle</b>
    <span class="lage {lage.klasse}"><span class="punkt" class:lebt={kanal.verbunden}></span>{lage.wort}</span>
  </header>

  <div class="m-inhalt">
    <NeueFassung telefon />
    {#if !bild}
      <div class="m-karte"><p>Verbinde mit der Leitstelle ...</p></div>
    {:else if blatt === 'lage'}
      <div class="m-titel">Lage</div>
      <div class="m-karte">
        <h3><i class="fa-solid fa-sliders"></i>Hauptregler</h3>
        <div class="m-regler">
          <button class="normal" class:an={bild.modus === 'normal'} onclick={() => stellen('normal')}><i class="fa-solid fa-play"></i>Normal</button>
          <Halteknopf klasse="auslaufen{bild.modus === 'auslaufen' ? ' an' : ''}" tun={() => stellen('auslaufen')} titel="Halten: laufende Aufträge rechnen zu Ende, Neues wartet">
            <i class="fa-solid fa-person-walking-arrow-right"></i>Auslaufen<span class="halten">halten</span></Halteknopf>
          <Halteknopf klasse="halt{bild.modus === 'halt' ? ' an' : ''}" tun={() => stellen('halt')} titel="Halten: alles bricht sofort ab">
            <i class="fa-solid fa-hand"></i>Halt<span class="halten">halten</span></Halteknopf>
        </div>
        <div class="m-hint">{bild.modus === 'normal' ? bild.lage_grund : MODUS[bild.modus].satz}</div>
        <label class="m-schalter"><span>Hintergrund</span>
          <button class="schalter" class:an={bild.hintergrund_erlaubt} onclick={() => tun(() => api.hauptregler(bild.modus, !bild.hintergrund_erlaubt))} aria-label="Hintergrund"></button></label>
      </div>
      <div class="m-kenn">
        <div class="kennzahl laeuft"><b>{laufend.length}</b><span>Läuft</span></div>
        <div class="kennzahl wartet"><b>{wartend.length}</b><span>Wartet</span></div>
        <div class="kennzahl"><b>{bild.knoten.filter((k) => k.erreichbar).length}/{bild.knoten.length}</b><span>Knoten</span></div>
        <div class="kennzahl"><b>{bild.massnahmen.filter((m) => m.zustand === 'ausgefuehrt').length}</b><span>Maßnahmen</span></div>
      </div>
    {:else if blatt === 'auftraege'}
      <div class="m-titel">Aufträge</div>
      <div class="m-karte">
        {#each [...laufend, ...wartend] as a (a.kennung)}
          {@const f = FAEHIGKEIT[a.faehigkeit]}
          <div class="m-auftrag" style="--f:{f.farbe};--f-rgb:{f.rgb}">
            <div class="symbol"><i class="fa-solid {f.symbol}"></i></div>
            <div style="min-width:0"><div class="t">{a.titel}</div>
              <div class="z"><span>{anwendung(a.anwendung)}</span><span>{a.zustand === 'laeuft' ? `seit ${dauer(jetzt - (a.start_s ?? jetzt))}` : 'wartet'}</span></div>
              {#if a.zustand === 'laeuft'}<div class="balken lebt unbestimmt"><b></b></div>{/if}</div>
            <button class="stopp" onclick={() => (wahl = wahl === a.kennung ? null : a.kennung)} aria-label="Stoppen"><i class="fa-solid fa-stop"></i></button>
            {#if wahl === a.kennung}
              <div class="m-wahl">
                <Halteknopf tun={() => stoppen(a.kennung, 'auslaufen')} titel="Halten: fertig rechnen, danach Anwendung sperren">Halten: auslaufen lassen</Halteknopf>
                <Halteknopf klasse="gefahr" tun={() => stoppen(a.kennung, 'sofort')} titel="Halten: sofort abbrechen">Halten: sofort stoppen</Halteknopf>
              </div>
            {/if}
          </div>
        {:else}<p class="m-hint">Nichts offen.</p>{/each}
      </div>
    {:else if blatt === 'knoten'}
      <div class="m-titel">Knoten</div>
      {#each bild.knoten as k (k.kennung)}
        <div class="m-karte">
          <h3><i class="fa-solid fa-server"></i>{k.name}<span class="rechts">{k.erreichbar ? prozent(k.belegt_anteil) : KNOTENZUSTAND[knotenzustand(k)].satz}</span></h3>
          <Speicherbalken knoten={k} modelle={bild.modelle} />
          <div class="m-hint">{gb(k.geladen_gb)} Modelle, {gb(Math.max(0, k.frei_gb))} frei</div>
        </div>
      {/each}
    {:else}
      <div class="m-titel">Meldungen</div>
      <div class="m-karte">
        {#each bild.meldungen.slice(0, 30) as m, i (i)}<div class="m-meldung"><span class="zahl">{uhrzeit(m.zeit_s)}</span><span>{m.text}</span></div>{/each}
      </div>
    {/if}
  </div>

  <nav class="m-fuss">
    <a href="#lage" class:aktiv={blatt === 'lage'} onclick={(e) => { e.preventDefault(); blatt = 'lage'; }}><i class="fa-solid fa-tower-observation"></i>Lage</a>
    <a href="#auftraege" class:aktiv={blatt === 'auftraege'} onclick={(e) => { e.preventDefault(); blatt = 'auftraege'; }}><i class="fa-solid fa-list-check"></i>Aufträge
      {#if wartend.length}<span class="pille zaehler warnung">{wartend.length}</span>{/if}</a>
    <a href="#knoten" class:aktiv={blatt === 'knoten'} onclick={(e) => { e.preventDefault(); blatt = 'knoten'; }}><i class="fa-solid fa-server"></i>Knoten</a>
    <a href="#meldungen" class:aktiv={blatt === 'meldungen'} onclick={(e) => { e.preventDefault(); blatt = 'meldungen'; }}><i class="fa-solid fa-bell"></i>Meldungen</a>
  </nav>
</div>

<style>
  .telefonansicht { height: 100dvh; display: flex; flex-direction: column; background: var(--ls-grund);
                    padding: env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left); }
  :global(.seite-mobil .m-kopf) { padding-top: 14px; }
  :global(.seite-mobil .m-fuss) { padding-bottom: max(14px, env(safe-area-inset-bottom)); }
  .m-schalter { display: flex; align-items: center; justify-content: space-between; margin-top: 14px; font-weight: 600; min-height: 44px; }
  .m-meldung { display: grid; grid-template-columns: 56px minmax(0, 1fr); gap: 8px; padding: 8px 0; border-top: 1px solid var(--ls-rand); font-size: 16px; }
  .m-meldung:first-child { border-top: 0; }
  .m-meldung .zahl { color: var(--ls-text-3); }
</style>
