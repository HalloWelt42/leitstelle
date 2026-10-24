<script lang="ts">
  import { untrack } from 'svelte';
  import { api } from '../lib/api';
  import { uhrzeit, zahl } from '../lib/format';
  import { kanal } from '../lib/kanal.svelte';
  import type { Lagebild, Massnahme, PruefEintrag } from '../lib/typen.gen';
  import { MASSNAHME, MASSNAHMENZUSTAND } from '../lib/wort';

  let { bild }: { bild: Lagebild } = $props();

  let reiter = $state<'meldungen' | 'massnahmen' | 'pruefung'>('meldungen');
  let massnahmen = $state<Massnahme[]>([]);
  let gesamt = $state(0);
  let pruefung = $state<PruefEintrag[]>([]);

  $effect(() => {
    const r = reiter;
    kanal.verlaufStand;
    bild.massnahmen.length;
    untrack(() => {
      if (r === 'massnahmen') api.massnahmen(0, 200).then((s) => { massnahmen = s.eintraege; gesamt = s.gesamt; }).catch(() => {});
      if (r === 'pruefung') api.pruefprotokoll(300).then((s) => (pruefung = s.eintraege)).catch(() => {});
    });
  });
</script>

<div class="seiteninhalt seite-protokoll">
  <div class="rahmen-kopf">
    <div class="seitenkopf"><h1>Protokoll</h1></div>
    <div class="reiter">
      <button class:aktiv={reiter === 'meldungen'} onclick={() => (reiter = 'meldungen')}><i class="fa-solid fa-bell"></i> Meldungen</button>
      <button class:aktiv={reiter === 'massnahmen'} onclick={() => (reiter = 'massnahmen')} title="Was die Selbststeuerung getan, vorgeschlagen oder gesperrt hat"><i class="fa-solid fa-wand-magic-sparkles"></i> Maßnahmen</button>
      <button class:aktiv={reiter === 'pruefung'} onclick={() => (reiter = 'pruefung')} title="Wer wann was geändert oder aufgedeckt hat; nur anhängen, nie löschen"><i class="fa-solid fa-shield-halved"></i> Prüfprotokoll</button>
    </div>
  </div>
  <div class="rollfeld">
    {#if reiter === 'meldungen'}
      {#each bild.meldungen as m, i (i)}
        <div class="zeile-log"><span class="zeit zahl">{uhrzeit(m.zeit_s, true)}</span><span class="leise">Leitstelle</span><i class="fa-solid fa-circle-dot leise"></i><span>{m.text}</span></div>
      {:else}<div class="leer"><i class="fa-solid fa-bell"></i><h2>Noch keine Meldungen</h2></div>{/each}
    {:else if reiter === 'massnahmen'}
      <p class="leise klein">{zahl(gesamt)} Maßnahmen gespeichert, die neuesten zuerst.</p>
      {#each massnahmen as m (m.kennung)}
        <div class="zeile-log" title={m.schritte.join(' > ')}><span class="zeit zahl">{uhrzeit(m.zeit_s, true)}</span><span class="leise">{MASSNAHMENZUSTAND[m.zustand]}</span>
          <i class="fa-solid {MASSNAHME[m.art].symbol}"></i><span><b>{MASSNAHME[m.art].wort}</b>: {m.grund}{m.gewinn_s ? ` (Gewinn ${Math.round(m.gewinn_s)} s, Aufwand ${Math.round(m.aufwand_s)} s)` : ''}</span></div>
      {:else}<div class="leer"><i class="fa-solid fa-wand-magic-sparkles"></i><h2>Noch keine Maßnahme</h2></div>{/each}
    {:else}
      {#each pruefung as e, i (i)}
        <div class="zeile-log"><span class="zeit zahl">{uhrzeit(e.zeit_s, true)}</span><span class="leise">{e.wer}</span><i class="fa-solid fa-pen leise"></i><span>{e.was}{e.gegenstand ? `: ${e.gegenstand}` : ''}</span></div>
      {:else}<div class="leer"><i class="fa-solid fa-shield-halved"></i><h2>Noch keine Einträge</h2></div>{/each}
    {/if}
  </div>
</div>

<style>
  :global(.seite-protokoll .zeile-log) { grid-template-columns: 110px 200px 24px minmax(0, 1fr); border-top: 1px solid var(--rand); }
</style>
