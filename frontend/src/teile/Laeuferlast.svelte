<script lang="ts">
  // Last des Modell-Läufers und des Rechners (knoten.last, ZUSAMMENSPIEL Z6): je Prozess des Läufers Rolle, Modell, Kerne
  // und Speicher, daneben der Stand der Leitstelle (Aufträge auf dem Läufer, zuletzt einer); die Fremdlast des Rechners und
  // die Stufe seines Hintergrunds. Befunde und Stufe rechnet der Kern; hier wird nur gezeigt. Knapp (Übersicht): nur die
  // Arbeiter als Liste, ohne Knopf und ohne Regelwerte; dort trägt jeder Rechner seinen Namen als Titel. Beenden von Hand
  // mit Bestätigung in der Leiste, nie mit Browser-Dialog.
  import { api } from '../lib/api';
  import { dauer, gb, komma, vor } from '../lib/format';
  import { tun } from '../lib/meldung.svelte';
  import type { KnotenSicht, LaeuferprozessSicht, Regelwerk } from '../lib/typen.gen';
  import { HINTERGRUNDSTUFE, LAEUFERROLLE, REGELWERTE } from '../lib/wort';

  let { knoten, regelwerk, jetzt, knapp = false, titel = 'Läufer und Last' }:
    { knoten: KnotenSicht; regelwerk: Regelwerk; jetzt: number; knapp?: boolean; titel?: string } = $props();

  let bestaetigen = $state<LaeuferprozessSicht | null>(null);
  const last = $derived(knoten.last);
  const stufe = $derived(HINTERGRUNDSTUFE[last.stufe]);
  const gezeigt = $derived(last.laeufer.filter((p) => p.rolle !== 'sonstig'));
  const sonstige = $derived(last.laeufer.filter((p) => p.rolle === 'sonstig'));
  const summe = (liste: LaeuferprozessSicht[], f: (p: LaeuferprozessSicht) => number | null) => liste.reduce((s, p) => s + (f(p) ?? 0), 0);
  const kerne = (cpu: number | null) => (cpu == null ? '-' : komma(cpu / 100, 1));
  const datei = (pfad: string) => pfad.split('/').pop() || '-';
  const regelLaeufer = $derived(regelwerk.szenarien_an.laeufer_ohne_auftrag ?? false);
  const regelLast = $derived(regelwerk.szenarien_an.hintergrund_rechnerlast ?? true);

  async function beenden(p: LaeuferprozessSicht) {
    const r = await tun(() => api.laeuferBeenden(knoten.kennung, p.pid));
    if (r) bestaetigen = null;
  }
</script>

<section class="laeuferlast">
  <div class="etikett">{titel}{#if last.laeufer.some((p) => p.ohne_auftrag_seit_s != null)}&nbsp;<span class="pille zaehler warnung"
       title="Arbeiter, die ohne Auftrag der Leitstelle rechnen">{last.laeufer.filter((p) => p.ohne_auftrag_seit_s != null).length}</span>{/if}</div>
  {#if !last.gemeldet}
    <div class="leise klein" title="Der Maschinenraum misst die Last des Läufers und des Rechners im Takt seiner Beobachtung (ab Fassung 0.15)">
      {knoten.agent.verbunden ? 'Keine Lastmessung: der Maschinenraum meldet sie nicht (Beobachtung aus oder ältere Fassung).' : 'Keine Lastmessung: kein Maschinenraum verbunden.'}</div>
  {:else}
    <div class="ll-werte">
      <span title="Last des Menschen und seiner übrigen Programme: alle Prozesse ohne Läufer und ohne Dienste des Maschinenraums, Anteil aller {last.kerne ?? ''} Kerne. Die Stufe richtet sich nach dem Mittel über {REGELWERTE.rechnerlast[0].wert(regelwerk)}.">
        <i class="fa-solid fa-gauge"></i>Fremdlast <b>{last.fremd_prozent != null ? `${komma(last.fremd_prozent, 0)} %` : '-'}</b>
        {#if last.fremd_mittel_prozent != null}<span class="leise">(Mittel {komma(last.fremd_mittel_prozent, 0)} %)</span>{/if}</span>
      <span class="zustand {stufe.klasse}" title="{stufe.satz}{last.stufe_grund ? `. ${last.stufe_grund}` : ''}"><i class="fa-solid {stufe.symbol}"></i>Hintergrund {stufe.wort.toLowerCase()}{#if last.stufe !== 'frei' && last.stufe_seit_s != null}&nbsp;seit {dauer(jetzt - last.stufe_seit_s)}{/if}</span>
      <span title="Aufträge der Leitstelle, die gerade auf dem Läufer dieses Rechners laufen oder ihm zugeteilt sind, und wann zuletzt einer dort lief">
        <i class="fa-solid fa-list-check"></i><b>{last.auftraege}</b> {last.auftraege === 1 ? 'Auftrag' : 'Aufträge'} der Leitstelle, zuletzt {vor(last.zuletzt_s, jetzt)}</span>
    </div>
    {#if !last.gemessen}
      <div class="leise klein">Läufer nicht gemessen: lsof fehlt auf dem Rechner oder im Maschinenraum ist kein Läufer eingetragen.</div>
    {:else if !last.laeufer.length}
      <div class="leise klein">Kein Prozess des Läufers gefunden: der Läufer läuft nicht.</div>
    {:else if knapp}
      <ul class="ll-knapp">
        {#each gezeigt.filter((p) => p.rolle === 'arbeiter') as p (p.pid)}
          <li class:auffaellig={p.ohne_auftrag_seit_s != null} title="{LAEUFERROLLE.arbeiter.wort}: {p.name}, Prozess {p.pid}{p.modelldatei ? `, ${p.modelldatei}` : ''}">
            <span class="umbruch">{datei(p.modelldatei)}</span><span class="zahl">{kerne(p.cpu_prozent)} Kerne</span><span class="zahl">{gb(p.gb)}</span>
            {#if p.beenden_s != null}<span class="leise">wird beendet</span>
            {:else if p.ohne_auftrag_seit_s != null}<span class="warnwort"><i class="fa-solid fa-triangle-exclamation"></i>ohne Auftrag seit {dauer(jetzt - p.ohne_auftrag_seit_s)}</span>{/if}
          </li>
        {:else}
          <li class="leise">Kein Modell geladen</li>
        {/each}
      </ul>
    {:else}
      <div class="tabellen-raum">
        <table class="tabelle karten">
          <thead><tr><th>Prozess</th><th>Rolle</th><th>Modell</th><th class="zahl">Kerne</th><th class="zahl">Speicher</th><th>Befund</th><th></th></tr></thead>
          <tbody>
            {#each gezeigt as p (p.pid)}
              <tr class:auffaellig={p.ohne_auftrag_seit_s != null}>
                <td><b class="umbruch">{p.name}</b> <span class="leise klein zahl">{p.pid}</span></td>
                <td data-titel="Rolle" title={LAEUFERROLLE[p.rolle].erklaerung}>{LAEUFERROLLE[p.rolle].wort}</td>
                <td data-titel="Modell" class="umbruch" title={p.modelldatei || undefined}>{p.modelldatei ? datei(p.modelldatei) : '-'}</td>
                <td data-titel="Kerne" class="zahl" title="Rechenzeit seit der letzten Messung je Wandzeit; 1,0 ist ein ganzer Kern">{kerne(p.cpu_prozent)}</td>
                <td data-titel="Speicher" class="zahl">{gb(p.gb)}</td>
                <td data-titel="Befund">
                  {#if p.beenden_s != null}<span class="zustand wartet"><i class="fa-solid fa-rotate dreht"></i>wird beendet</span>
                  {:else if p.ohne_auftrag_seit_s != null}<span class="warnwort" title="Rechnet seit der Frist über der Schwelle, ohne dass ein Auftrag der Leitstelle auf dem Läufer lief">
                    <i class="fa-solid fa-triangle-exclamation"></i>arbeitet ohne Auftrag seit {dauer(jetzt - p.ohne_auftrag_seit_s)}</span>
                    {#if last.umgehungen.length}<div class="klein leise">am Läufer hängt {last.umgehungen.join(', ')}</div>{/if}
                  {:else}<span class="leise">-</span>{/if}
                </td>
                <td class="knopfzelle">{#if p.rolle === 'arbeiter' && p.ohne_auftrag_seit_s != null && p.beenden_s == null}
                  <button class="knopf klein ohne gefahr" onclick={() => (bestaetigen = p)}
                          title="Den Arbeiter vom Maschinenraum beenden lassen; der Läufer lädt das Modell bei Bedarf neu"><i class="fa-solid fa-power-off"></i> Prozess beenden</button>{/if}</td>
              </tr>
            {/each}
            {#if sonstige.length}
              <tr class="leise">
                <td>Sonstige <span class="klein zahl">{sonstige.length}</span></td>
                <td data-titel="Rolle" title={LAEUFERROLLE.sonstig.erklaerung}>{LAEUFERROLLE.sonstig.wort}</td>
                <td data-titel="Modell">-</td>
                <td data-titel="Kerne" class="zahl">{kerne(summe(sonstige, (p) => p.cpu_prozent))}</td>
                <td data-titel="Speicher" class="zahl">{gb(summe(sonstige, (p) => p.gb))}</td>
                <td data-titel="Befund">-</td>
                <td></td>
              </tr>
            {/if}
          </tbody>
        </table>
      </div>
    {/if}
    {#if bestaetigen}
      <div class="bestaetigen"><i class="fa-solid fa-triangle-exclamation"></i>
        <span>{bestaetigen.name} (Prozess {bestaetigen.pid}) mit {datei(bestaetigen.modelldatei)} beenden? Der Läufer lädt das Modell bei Bedarf neu.
          {#if last.umgehungen.length}Am Läufer hängt {last.umgehungen.join(', ')}; der Arbeiter rechnet vermutlich dafür.{/if}</span>
        <div class="rechts"><button class="knopf klein ohne" onclick={() => (bestaetigen = null)}>Abbrechen</button>
          <button class="knopf klein gefahr-voll" onclick={() => bestaetigen && beenden(bestaetigen)}>Ja, beenden</button></div></div>
    {/if}
    {#if !knapp}
      <div class="ll-regeln klein">
        <div><b>Regel "Läufer arbeitet ohne Auftrag"</b> <span class="zustand {regelLaeufer ? 'fertig' : 'aus'}">{regelLaeufer ? 'an' : 'aus'}</span>
          <span class="leise">{regelLaeufer ? 'beendet solche Arbeiter selbst, außer ein Programm hängt am Leitstand vorbei am Läufer' : 'meldet nur; beenden von Hand'}</span>
          {#each REGELWERTE.laeufer as w (w.wort)}<span class="wert" title={w.erklaerung}>{w.wort} <b>{w.wert(regelwerk)}</b></span>{/each}</div>
        <div><b>Regel "Hintergrund bei Rechnerlast"</b> <span class="zustand {regelLast ? 'fertig' : 'aus'}">{regelLast ? 'an' : 'aus'}</span>
          {#each REGELWERTE.rechnerlast as w (w.wort)}<span class="wert" title={w.erklaerung}>{w.wort} <b>{w.wert(regelwerk)}</b></span>{/each}</div>
      </div>
    {/if}
  {/if}
</section>

<style>
  .laeuferlast { display: flex; flex-direction: column; gap: var(--a2); min-width: 0; }
  .laeuferlast .etikett { display: flex; align-items: center; }
  .ll-werte { display: flex; gap: var(--a2) var(--a4); flex-wrap: wrap; align-items: center; font-size: var(--klein); color: var(--text-2); }
  .ll-werte i { color: var(--text-3); margin-right: 6px; }
  .ll-werte .zustand i { color: inherit; }
  .ll-werte b { font-family: var(--schrift-zahl); font-weight: 600; color: var(--text); }
  .laeuferlast .umbruch { overflow-wrap: anywhere; }
  .laeuferlast tr.auffaellig { background: color-mix(in srgb, var(--warn) 8%, transparent); }
  .laeuferlast tr.auffaellig td { background: none; }
  .laeuferlast .warnwort { color: var(--warn); font-weight: 600; }
  .laeuferlast .warnwort i { margin-right: 6px; }
  .laeuferlast .knopfzelle { text-align: right; }
  .ll-knapp { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--a1); font-size: var(--klein); }
  .ll-knapp li { display: flex; flex-wrap: wrap; gap: 2px var(--a3); padding: 6px 8px; border-radius: var(--r2); }
  .ll-knapp li .umbruch { flex: 1 1 10em; min-width: 0; }
  .ll-knapp li .zahl { font-family: var(--schrift-zahl); white-space: nowrap; }
  .ll-knapp li.auffaellig { background: color-mix(in srgb, var(--warn) 8%, transparent); }
  .ll-regeln { display: flex; flex-direction: column; gap: var(--a1); color: var(--text-2); }
  .ll-regeln > div { display: flex; flex-wrap: wrap; align-items: center; gap: var(--a1) var(--a3); }
  .ll-regeln .wert { cursor: help; }
  .ll-regeln .wert b { font-family: var(--schrift-zahl); font-weight: 600; color: var(--text); }
</style>
