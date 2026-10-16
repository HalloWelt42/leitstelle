<script lang="ts">
  import { kanal } from './lib/kanal.svelte';
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
  import Rueckmeldungen from './teile/Rueckmeldungen.svelte';
  import Seitenleiste from './teile/Seitenleiste.svelte';

  kanal.starten();
  // Telefone bekommen eine eigenständige, reduzierte Ansicht statt einer gequetschten Schreibtischfassung
  if (matchMedia('(max-width: 700px)').matches && weg.seite !== 'mobil') weg.gehe('mobil', null, true);
</script>

{#if weg.seite === 'mobil'}
  <Mobil />
{:else}
  <div class="schale">
    <Kopf />
    <Seitenleiste />
    <main class="haupt rahmen" id="haupt">
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
