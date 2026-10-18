<script lang="ts">
  import { onMount } from 'svelte';
  import { fassungVerfolgen } from './lib/fassung.svelte';
  import { kanal } from './lib/kanal.svelte';
  import { telefonweicheStarten } from './lib/telefon';
  import { weg } from './lib/weg.svelte';
  import Anschluss from './seiten/Anschluss.svelte';
  import Anwendungen from './seiten/Anwendungen.svelte';
  import Auftraege from './seiten/Auftraege.svelte';
  import Dienste from './seiten/Dienste.svelte';
  import Knoten from './seiten/Knoten.svelte';
  import Mobil from './seiten/Mobil.svelte';
  import Modelle from './seiten/Modelle.svelte';
  import Protokoll from './seiten/Protokoll.svelte';
  import Uebersicht from './seiten/Uebersicht.svelte';
  import Fuss from './teile/Fuss.svelte';
  import Kopf from './teile/Kopf.svelte';
  import NeueFassung from './teile/NeueFassung.svelte';
  import Rueckmeldungen from './teile/Rueckmeldungen.svelte';
  import Seitenleiste from './teile/Seitenleiste.svelte';

  kanal.starten();
  // Neue Fassung des Kerns: von selbst neu laden, sobald es nichts unterbricht
  onMount(fassungVerfolgen);
  telefonweicheStarten();
</script>

{#if weg.seite === 'mobil'}
  <Mobil />
{:else}
  <div class="schale">
    <Kopf />
    <Seitenleiste />
    <main class="haupt rahmen" id="haupt">
      <NeueFassung />
      {#if !kanal.lagebild}
        <div class="verbinden"><div class="leer"><i class="fa-solid fa-satellite-dish"></i><h2>Verbinde mit der Leitstelle</h2>
          <p>Die Oberfläche wartet auf das erste Lagebild über den Live-Kanal.</p></div></div>
      {:else if weg.seite === 'uebersicht'}<Uebersicht bild={kanal.lagebild} />
      {:else if weg.seite === 'auftraege'}<Auftraege bild={kanal.lagebild} />
      {:else if weg.seite === 'modelle'}<Modelle bild={kanal.lagebild} />
      {:else if weg.seite === 'knoten'}<Knoten bild={kanal.lagebild} />
      {:else if weg.seite === 'dienste'}<Dienste bild={kanal.lagebild} />
      {:else if weg.seite === 'anschluss'}<Anschluss bild={kanal.lagebild} />
      {:else if weg.seite === 'anwendungen'}<Anwendungen bild={kanal.lagebild} />
      {:else if weg.seite === 'protokoll'}<Protokoll bild={kanal.lagebild} />
      {/if}
    </main>
    <Fuss />
  </div>
{/if}
<Rueckmeldungen />
