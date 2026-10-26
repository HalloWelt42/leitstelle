<script lang="ts">
  // Zugriffe am Leitstand vorbei auf die Modelle eines Rechners, wie sein Maschinenraum sie im Takt der Messung meldet
  // (knoten.fremde): Verbindungen zum Läufer, die nicht über die Leitstelle gehen, und Programme mit viel Speicher
  // außerhalb von Diensten und Läufer. Die Deutung und die Zahl der echten Umgehungen kommen vom Kern.
  import { gb } from '../lib/format';
  import type { FremdeSicht, FremdzugriffSicht } from '../lib/typen.gen';
  import { FREMDART, FREMDDEUTUNG } from '../lib/wort';

  let { fremde, verbunden }: { fremde: FremdeSicht; verbunden: boolean } = $props();

  // Verbindungen zum Läufer zählen, Speicher in GB; als Karte (schmal) trägt jede Zeile ihr eigenes Etikett
  const menge = (z: FremdzugriffSicht) => (z.art === 'speicher' ? (z.gb != null ? gb(z.gb) : '-') : String(z.verbindungen));
  const mengenwort = (z: FremdzugriffSicht) => (z.art === 'speicher' ? 'Speicher' : 'Verbindungen');
</script>

<section class="vorbei">
  <div class="etikett">Am Leitstand vorbei{#if fremde.umgehungen}&nbsp;<span class="pille zaehler warnung">{fremde.umgehungen}</span>{/if}</div>
  {#if !fremde.beobachtet}
    <div class="leise klein" title="Der Maschinenraum meldet, was auf diesem Rechner an der Leitstelle vorbei auf Modelle zugreift, sofern seine Beobachtung an ist und der Rechner sie messen kann">
      {verbunden ? 'Nicht beobachtet: der Maschinenraum meldet es nicht (Beobachtung aus, hier nicht messbar oder ältere Fassung).' : 'Nicht beobachtet: kein Maschinenraum verbunden.'}</div>
  {:else if !fremde.zugriffe.length}
    <div class="leise klein"><i class="fa-solid fa-check"></i> Nichts gefunden</div>
  {:else}
    <div class="tabellen-raum">
      <table class="tabelle karten">
        <thead><tr><th>Wer</th><th>Art</th><th>Prozess</th><th>Arbeitsordner</th><th class="zahl">Verbindungen bzw. GB</th></tr></thead>
        <tbody>
          {#each fremde.zugriffe as z (`${z.art}:${z.wer}:${z.pid}`)}
            <tr class:leise={z.deutung === 'leitstelle_direkt'}>
              <td><b class="zahl-umbruch">{z.wer}</b>{#if z.deutung !== 'umgehung'}<div class="klein leise">{FREMDDEUTUNG[z.deutung]}</div>{/if}</td>
              <td data-titel="Art"><i class="fa-solid {FREMDART[z.art].symbol}"></i> {FREMDART[z.art].wort}</td>
              <td data-titel="Prozess" class="zahl-links" title={z.befehl || undefined}>{z.pid ?? '-'}</td>
              <td data-titel="Arbeitsordner" class="ordner">{z.ordner || '-'}</td>
              <td data-titel={mengenwort(z)} class="zahl" title={mengenwort(z)}>{menge(z)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</section>

<style>
  .vorbei { display: flex; flex-direction: column; gap: var(--a2); min-width: 0; }
  .vorbei .etikett { display: flex; align-items: center; }
  .vorbei .ordner, .vorbei .zahl-umbruch { overflow-wrap: anywhere; }
  .vorbei .zahl-links { font-family: var(--schrift-zahl); }
  .vorbei tr.leise td { color: var(--text-3); }
</style>
