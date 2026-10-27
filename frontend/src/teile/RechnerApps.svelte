<script lang="ts">
  // Apps des Rechners (knoten.last.apps): je laufendem nativem Teil einer App des Stellwerks Kerne und Speicher. Vom
  // Stellwerk gestartet, kein KI-Dienst: zählt weder als Speicher am Leitstand vorbei noch zur Fremdlast. Teile im
  // Docker-Rechner stehen dort. Gemessen hat der Maschinenraum; hier wird nur gezeigt.
  import { gb, kerne } from '../lib/format';
  import type { KnotenSicht } from '../lib/typen.gen';

  let { knoten }: { knoten: KnotenSicht } = $props();
  const apps = $derived(knoten.last.apps);
</script>

<section class="lastblock">
  <div class="etikett">Apps des Rechners</div>
  <p class="leise klein">Vom Stellwerk gestartet, kein KI-Dienst: zählt weder als Speicher am Leitstand vorbei noch zur Fremdlast.</p>
  {#if !apps}
    <div class="leise klein">Keine Angabe: im Maschinenraum ist kein Stellwerk eingetragen, oder er meldet die Apps nicht (ältere Fassung).</div>
  {:else if !apps.gemessen}
    <div class="leise klein">Nicht zugeordnet: {apps.meldung}</div>
  {:else if !apps.teile.length}
    <div class="leise klein">Keine App läuft nativ auf diesem Rechner.</div>
  {:else}
    <div class="tabellen-raum">
      <table class="tabelle karten">
        <thead><tr><th>App</th><th>Teil</th><th class="zahl">Kerne</th><th class="zahl">Speicher</th></tr></thead>
        <tbody>
          {#each apps.teile as t (`${t.app}.${t.teil}`)}
            <tr>
              <td><b class="umbruch">{t.app_name}</b></td>
              <td data-titel="Teil" class="umbruch" title="Prozesse {t.pids.join(', ')}">{t.name}</td>
              <td data-titel="Kerne" class="zahl" title="Rechenzeit seiner Prozesse seit der letzten Messung je Wandzeit; 1,0 ist ein ganzer Kern">{kerne(t.cpu_prozent)}</td>
              <td data-titel="Speicher" class="zahl">{gb(t.gb)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <div class="leise klein">Zusammen <span class="zahl">{gb(apps.gb)}</span>; im Speicherbalken ein Teil von System.</div>
  {/if}
</section>
