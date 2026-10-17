<script lang="ts">
  import { api } from '../lib/api';
  import { arbeit } from '../lib/arbeit.svelte';
  import { kanal } from '../lib/kanal.svelte';
  import { tun } from '../lib/meldung.svelte';
  import type { Betriebsmodus } from '../lib/typen.gen';
  import { LAGE, MODUS } from '../lib/wort';

  const bild = $derived(kanal.lagebild);
  const modus = $derived(bild?.modus ?? 'normal');
  const laufend = $derived(bild?.auftraege.filter((a) => a.zustand === 'laeuft') ?? []);
  const wartend = $derived(bild?.auftraege.filter((a) => a.zustand !== 'laeuft') ?? []);

  let leiste = $state<Betriebsmodus | null>(null);
  let grund = $state('');
  arbeit.bearbeitung(() => leiste !== null);

  const lage = $derived.by(() => {
    if (!bild) return { klasse: 'aus', wort: 'Getrennt', satz: 'Keine Verbindung zur Leitstelle; verbinde neu.' };
    if (modus !== 'normal') return { klasse: modus, wort: MODUS[modus].lage, satz: MODUS[modus].satz };
    return { klasse: LAGE[bild.lage].klasse, wort: LAGE[bild.lage].wort, satz: bild.lage_grund };
  });

  async function stellen(neu: Betriebsmodus) {
    if (!bild) return;
    const r = await tun(() => api.hauptregler(neu, bild.hintergrund_erlaubt, grund.trim()));
    if (r) {
      leiste = null;
      grund = '';
    }
  }

  function waehlen(neu: Betriebsmodus) {
    if (neu === 'normal') stellen('normal');
    else leiste = neu;
  }

  function hintergrund() {
    if (bild) tun(() => api.hauptregler(bild.modus, !bild.hintergrund_erlaubt, ''));
  }
</script>

<header class="kopf">
  <div class="marke">
    <img class="marke-bild" src="/symbol-frei.svg" alt="" />
    <span class="marke-name">Leitstelle</span>
    {#if bild}<span class="zahl">{bild.version}</span>{/if}
  </div>
  <span class="rolle" title="Leitstelle verteilt Aufträge, Maschinenraum regelt KI, Stellwerk startet Anwendungen"><i class="fa-solid fa-tower-broadcast"></i>verteilt Aufträge</span>

  <div class="hauptregler" data-modus={modus} title="Hauptregler: wirkt sofort auf den ganzen Verbund">
    <span class="etikett">Betrieb</span>
    <span class="stufen">
      <button class="normal" class:an={modus === 'normal'} onclick={() => waehlen('normal')} disabled={!bild}
              title="Normalbetrieb: Aufträge werden angenommen und verteilt"><i class="fa-solid fa-play"></i><span>Normal</span></button>
      <button class="auslaufen" class:an={modus === 'auslaufen'} onclick={() => waehlen('auslaufen')} disabled={!bild}
              title="Sanft: laufende Aufträge rechnen zu Ende, Neues wird nicht gestartet, sondern wartet"><i class="fa-solid fa-person-walking-arrow-right"></i><span>Auslaufen</span></button>
      <button class="halt" class:an={modus === 'halt'} onclick={() => waehlen('halt')} disabled={!bild}
              title="Harter Schnitt: alles bricht sofort ab, die Anwendungen bekommen den bisherigen Stand; braucht eine Bestätigung"><i class="fa-solid fa-hand"></i><span>Halt</span></button>
    </span>
    <label class="hintergrund" title="Hintergrund-Aufträge (Stapelarbeit) anhalten oder laufen lassen; angehalten wird ohne Ausnahme, interaktive Aufträge sind nicht betroffen">
      <button class="schalter" class:an={bild?.hintergrund_erlaubt ?? true} onclick={hintergrund} disabled={!bild} aria-label="Hintergrund"></button>Hintergrund
    </label>
  </div>

  <div class="kopf-aktionen">
    <span class="lage {lage.klasse}" title={lage.satz}><span class="punkt" class:lebt={!!bild}></span>{lage.wort}</span>
  </div>
</header>

{#if leiste}
  <div class="hauptregler-leiste {leiste}">
    <i class="fa-solid {leiste === 'halt' ? 'fa-hand' : 'fa-person-walking-arrow-right'}"></i>
    <div class="folgen">
      {#if leiste === 'halt'}
        <b>Alles sofort stoppen?</b>
        <span><span class="zahl">{laufend.length}</span> laufende Aufträge brechen ab; die Anwendungen bekommen den bisherigen Text und den Grund Halt.</span>
        <span><span class="zahl">{wartend.length}</span> wartende Aufträge werden abgelehnt. Solange Halt steht, lehnt die Leitstelle jeden neuen Auftrag ab.</span>
      {:else}
        <b>Auslaufen lassen?</b>
        <span><span class="zahl">{laufend.length}</span> laufende Aufträge rechnen zu Ende; danach ist der Verbund frei.</span>
        <span>Neue und <span class="zahl">{wartend.length}</span> wartende Aufträge warten, bis der Hauptregler wieder auf Normal steht.</span>
      {/if}
    </div>
    <div class="rechts">
      <input class="eingabe" style="height:36px;width:300px" placeholder="Grund (steht im Prüfprotokoll)" bind:value={grund}
             title="Optional; steht im Prüfprotokoll und bei Halt in der Abbruchnachricht an die Anwendungen" />
      <button class="knopf klein ohne" onclick={() => (leiste = null)}>Abbrechen</button>
      <button class="knopf klein {leiste === 'halt' ? 'gefahr-voll' : 'warnung'}" onclick={() => leiste && stellen(leiste)}>
        <i class="fa-solid {leiste === 'halt' ? 'fa-hand' : 'fa-person-walking-arrow-right'}"></i>
        {leiste === 'halt' ? 'Ja, alles stoppen' : 'Ja, auslaufen lassen'}
      </button>
    </div>
  </div>
{/if}
