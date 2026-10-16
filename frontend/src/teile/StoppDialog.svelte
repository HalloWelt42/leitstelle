<script lang="ts">
  import { api } from '../lib/api';
  import { dauer } from '../lib/format';
  import { kanal } from '../lib/kanal.svelte';
  import { tun } from '../lib/meldung.svelte';
  import type { AuftragSicht } from '../lib/typen.gen';
  import Dialog from './Dialog.svelte';

  // Auftrag stoppen mit Wahl wie im Entwurf: Auslaufen (fertig rechnen, danach Anwendung sperren) oder sofort
  let { auftrag, schliessen }: { auftrag: AuftragSicht; schliessen: () => void } = $props();

  const app = $derived(kanal.lagebild?.anwendungen.find((a) => a.kennung === auftrag.anwendung)?.name ?? 'Die Anwendung');
  const laeuft = $derived(auftrag.zustand === 'laeuft');
  let modus = $state<'auslaufen' | 'sofort'>('auslaufen');
  let grund = $state('');

  async function stoppen(m: 'auslaufen' | 'sofort') {
    const ok = await tun(() => api.stoppen(auftrag.kennung, m, grund.trim()), m === 'sofort' ? 'Auftrag gestoppt' : `Auftrag läuft aus, danach ist ${app} gesperrt`);
    if (ok !== undefined) schliessen();
  }
</script>

<Dialog titel="Auftrag stoppen: {auftrag.titel}" symbol="fa-hand" {schliessen}>
  <p class="leise">
    {app} · {laeuft ? `läuft seit ${dauer(kanal.jetzt() - (auftrag.start_s ?? kanal.jetzt()))}` : `wartet seit ${dauer(kanal.jetzt() - auftrag.eingang_s)}`}
    {#if auftrag.modell} · {auftrag.modell}{/if}
  </p>
  <div class="wahl" style="margin-top: var(--ls-a3)">
    <label class:an={modus === 'auslaufen'} title="Der Auftrag rechnet zu Ende; danach nimmt die Leitstelle von {app} nichts Neues an, bis du freigibst">
      <input class="versteckt" type="radio" bind:group={modus} value="auslaufen" />
      <span class="kreis"></span>
      <div><b>Auslaufen lassen</b>
        <span>Der Auftrag rechnet fertig, {app} bekommt das Ergebnis normal. Danach ist {app} gesperrt, bis du sie unter Anwendungen freigibst.</span></div>
    </label>
    <label class:an={modus === 'sofort'} title="Die Rechnung bricht sofort ab; die Anwendung bekommt den bisherigen Text">
      <input class="versteckt" type="radio" bind:group={modus} value="sofort" />
      <span class="kreis"></span>
      <div><b>Sofort stoppen</b>
        <span>Die Rechnung bricht ab. {app} bekommt den bisherigen Text und als Abschluss <code>leitstelle_abbruch</code> mit Grund; Speicher und Platz sind sofort frei.</span></div>
    </label>
  </div>
  <div class="feld-l" style="margin-top: var(--ls-a4)">
    <span>Grund für die Anwendung und das Prüfprotokoll <small>optional</small></span>
    <textarea class="eingabe" rows="2" bind:value={grund} title="Wird bei Sofort der Anwendung mitgeschickt und steht im Prüfprotokoll"></textarea>
  </div>
  {#snippet knoepfe()}
    <button class="knopf ohne links" onclick={schliessen} title="Fenster schließen, der Auftrag läuft unverändert weiter">Abbrechen</button>
    <button class="knopf" class:haupt={modus === 'auslaufen'} onclick={() => stoppen('auslaufen')}><i class="fa-solid fa-person-walking-arrow-right"></i> Auslaufen lassen</button>
    <button class="knopf gefahr-voll" onclick={() => stoppen('sofort')}><i class="fa-solid fa-stop"></i> Sofort stoppen</button>
  {/snippet}
</Dialog>
