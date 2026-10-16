<script lang="ts">
  import { prozent } from '../lib/format';
  import { kanal } from '../lib/kanal.svelte';

  const bild = $derived(kanal.lagebild);
  const laufend = $derived(bild?.auftraege.filter((a) => a.zustand === 'laeuft').length ?? 0);
  const wartend = $derived(bild ? bild.auftraege.length - laufend : 0);
  const vollster = $derived(bild?.knoten.filter((k) => k.erreichbar).sort((a, b) => b.belegt_anteil - a.belegt_anteil)[0]);
  const erreichbar = $derived(bild?.knoten.filter((k) => k.erreichbar).length ?? 0);
</script>

<footer class="fuss">
  <span><i class="fa-solid fa-circle-play"></i>&nbsp; <span class="zahl">{laufend}</span> Aufträge laufen · <span class="zahl">{wartend}</span> warten</span>
  {#if vollster}<span title="Belegter Speicher (Modelle und System) des vollsten Rechners"><i class="fa-solid fa-memory"></i>&nbsp; {vollster.name} <span class="zahl">{prozent(vollster.belegt_anteil)}</span> Speicher</span>{/if}
  <div class="rechts">
    {#if bild}<span title="Rechner, deren Dienste antworten"><span class="punkt" class:gefahr={erreichbar < bild.knoten.length}></span>{erreichbar} von {bild.knoten.length} Knoten</span>{/if}
    <span title="Verbindung dieser Oberfläche zur Leitstelle"><span class="punkt" class:lebt={kanal.verbunden} class:gefahr={!kanal.verbunden}></span>{kanal.verbunden ? 'Live' : 'Getrennt'}</span>
    {#if bild}<span class="schwach zahl">{bild.version}</span>{/if}
  </div>
</footer>
