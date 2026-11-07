<script lang="ts">
  // Akku eines Rechners als Wert in der Zeile der Rechnerkarte (LS-11, Entwurf mockups/knoten.html): Symbol nach
  // Ladestand, Prozent, Lage (lädt, am Netzteil, Akku mit Restzeit), Stecker solange ein Netzteil hängt. Ohne Netzteil
  // unter KNAPP_PROZENT in Warnfarbe. Einzelheiten (Zustand, Ladezyklen) beim Überfahren.
  import type { Akku } from '../lib/typen.gen';
  import { komma } from '../lib/format';

  let { akku }: { akku: Akku } = $props();

  const KNAPP_PROZENT = 20;
  const dauer = (min: number) => `${Math.floor(min / 60)}:${String(min % 60).padStart(2, '0')}`;
  const symbol = (p: number) => p >= 90 ? 'full' : p >= 60 ? 'three-quarters' : p >= 35 ? 'half' : p >= 10 ? 'quarter' : 'empty';

  const knapp = $derived(!akku.netzteil && akku.prozent < KNAPP_PROZENT);
  const lage = $derived(akku.netzteil
    ? (akku.laedt ? `lädt${akku.rest_min ? `, voll in ${dauer(akku.rest_min)}` : ''}` : 'am Netzteil')
    : `Akku${akku.rest_min ? `, noch ${dauer(akku.rest_min)}` : ''}`);
  const titel = $derived(
    `Akku ${akku.prozent} %, ${akku.netzteil ? 'am Netzteil' : 'ohne Netzteil'}`
    + (akku.netzteil ? (akku.laedt ? ', lädt' : ', lädt nicht (voll, oder die Akku-Schonung von macOS hält ihn unter voll)') : '')
    + (akku.kapazitaet_prozent != null ? `. Zustand: ${komma(akku.kapazitaet_prozent, 0)} % der ursprünglichen Kapazität` : '')
    + (akku.zyklen != null ? `, ${akku.zyklen} Ladezyklen` : '')
    + '.' + (knapp ? ' Fast leer: der Rechner schläft bald ein.' : ''));
</script>

<span class="akkuwert" class:knapp title={titel}><i class="fa-solid fa-battery-{symbol(akku.prozent)}"></i><b>{akku.prozent} %</b> {lage}{#if akku.netzteil}<i class="fa-solid fa-plug stecker"></i>{/if}</span>

<style>
  .akkuwert.knapp, .akkuwert.knapp i, .akkuwert.knapp b { color: var(--warn); }
  .akkuwert i.stecker { margin: 0 0 0 6px; width: auto; }
</style>
