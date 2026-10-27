<script lang="ts">
  // Docker-Rechner eines Rechners (knoten.last.docker): Kerne, Speicher und die Container mit Last, die größte zuerst;
  // je Container die Anwendung, deren Docker-Projekte ihn nennen. Daraus die Docker-Last, das zweite Maß der Regel
  // "Hintergrund bei Rechnerlast": ohne die Container von Anwendungen, die gerade Hintergrundarbeit haben. Ruhende
  // Container stehen zusammen in einer Zeile. Gemessen hat der Maschinenraum, gerechnet der Kern; hier wird nur gezeigt.
  import { dauer, gb, kerne, komma } from '../lib/format';
  import type { ContainerSicht, KnotenSicht, Regelwerk } from '../lib/typen.gen';

  let { knoten, regelwerk }: { knoten: KnotenSicht; regelwerk: Regelwerk } = $props();
  const docker = $derived(knoten.last.docker);
  // mit Last: mindestens ein Hundertstel eines Kerns; was darunter liegt, ruht
  const RUHE_PROZENT = 1;
  const mitLast = $derived(docker?.container.filter((c) => (c.cpu_prozent ?? 0) >= RUHE_PROZENT) ?? []);
  const ruhend = $derived(docker?.container.filter((c) => (c.cpu_prozent ?? 0) < RUHE_PROZENT) ?? []);
  const summe = (liste: ContainerSicht[]) => liste.reduce((s, c) => s + (c.gb ?? 0), 0);
</script>

<section class="lastblock">
  <div class="etikett">Docker-Rechner</div>
  {#if !docker}
    <div class="leise klein">Keine Angabe: der Maschinenraum misst den Docker-Rechner nicht (abgeschaltet oder ältere Fassung).</div>
  {:else if !docker.gemessen}
    <div class="leise klein">Nicht gemessen: Docker läuft nicht oder antwortet nicht rechtzeitig.</div>
  {:else}
    <div class="ll-werte">
      <span title="Kerne und Speicher der virtuellen Maschine, in der die Container laufen"><i class="fa-brands fa-docker"></i><b>{docker.kerne ?? '-'}</b> Kerne,
        <b>{gb(docker.speicher_gb)}</b></span>
      <span title="Container ohne die von Anwendungen mit Hintergrundarbeit, Anteil aller Kerne des Docker-Rechners. Zweites Maß der Regel &quot;Hintergrund bei Rechnerlast&quot; (Mittel über {dauer(regelwerk.last_frist_s)}); die Container zählen nicht zur Fremdlast.">
        <i class="fa-solid fa-gauge"></i>Docker-Last <b>{docker.last_prozent != null ? `${komma(docker.last_prozent, 0)} %` : '-'}</b>
        {#if docker.last_mittel_prozent != null}<span class="leise">(Mittel {komma(docker.last_mittel_prozent, 0)} %)</span>{/if}</span>
    </div>
    {#if !docker.container.length}
      <div class="leise klein">Kein Container läuft.</div>
    {:else}
      <div class="tabellen-raum">
        <table class="tabelle karten">
          <thead><tr><th>Container</th><th>Anwendung</th><th class="zahl">Kerne</th><th class="zahl">Speicher</th></tr></thead>
          <tbody>
            {#each mitLast as c (c.name)}
              <tr class:leise={c.hintergrund}>
                <td><b class="umbruch">{c.name}</b>{#if c.projekt}&nbsp;<span class="leise klein">{c.projekt}</span>{/if}</td>
                <td data-titel="Anwendung" title={c.anwendung ? undefined : 'Keine Anwendung nennt sein Compose-Projekt oder seinen Namen unter Docker-Projekte'}>
                  {c.anwendung ?? '-'}{#if c.hintergrund}<div class="klein">Hintergrundarbeit: zählt nicht</div>{/if}</td>
                <td data-titel="Kerne" class="zahl" title="Kerne des Docker-Rechners, wie Docker sie misst; 1,0 ist ein ganzer Kern">{kerne(c.cpu_prozent)}</td>
                <td data-titel="Speicher" class="zahl">{gb(c.gb)}</td>
              </tr>
            {/each}
            {#if ruhend.length}
              <tr class="leise">
                <td>Ruhend <span class="klein zahl">{ruhend.length}</span></td>
                <td data-titel="Anwendung" class="umbruch">{[...new Set(ruhend.map((c) => c.anwendung).filter(Boolean))].join(', ') || '-'}</td>
                <td data-titel="Kerne" class="zahl">0,0</td>
                <td data-titel="Speicher" class="zahl">{gb(summe(ruhend))}</td>
              </tr>
            {/if}
          </tbody>
        </table>
      </div>
    {/if}
  {/if}
</section>
