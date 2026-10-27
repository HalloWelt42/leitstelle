<script lang="ts">
  // Modelle eines externen Anbieters einzeln: Name, Art (schnell oder gründlich im Vergleich), Kontext, Parameter, Fähigkeiten
  // mit Probe, belegte Plätze und Nutzung im gleitenden Fenster; darüber die Grenzen des Schlüssels, die alle Modelle teilen.
  // Beim Anbieter wird nichts geladen: "beim Anbieter bereit", keine Speichergröße. Knapp (Übersicht): ohne Fähigkeiten.
  import { menge, uhrzeit, zahl } from '../lib/format';
  import type { DienstSicht, ModellSicht, Nutzung } from '../lib/typen.gen';
  import { FAEHIGKEIT, art, parameterText } from '../lib/wort';
  import Faehigkeit from './Faehigkeit.svelte';

  let { dienst, modelle, jetzt, knapp = false }: { dienst: DienstSicht; modelle: ModellSicht[]; jetzt: number; knapp?: boolean } = $props();

  const gesperrt = $derived(dienst.gesperrt_bis_s != null && dienst.gesperrt_bis_s > jetzt);
  const grenzen = $derived([
    { wort: 'Anfragen', n: dienst.nutzung.anfragen, grenze: dienst.anfragen_je_minute },
    { wort: 'Token hinein', n: dienst.nutzung.token_ein, grenze: dienst.token_ein_je_minute },
    { wort: 'Token heraus', n: dienst.nutzung.token_aus, grenze: dienst.token_aus_je_minute },
  ]);
  const nutzungText = (n: Nutzung) =>
    `${zahl(n.anfragen)} ${n.anfragen === 1 ? 'Anfrage' : 'Anfragen'}, ${menge(n.token_ein)} Token hinein, ${menge(n.token_aus)} heraus`;
  const zustand = (m: ModellSicht) => (gesperrt ? `gesperrt bis ${uhrzeit(dienst.gesperrt_bis_s, true)}` : m.zustand === 'rechnet' ? 'rechnet beim Anbieter' : 'beim Anbieter bereit');
  const probe = (m: ModellSicht, f: string) => m.steckbrief.geprueft?.find((p) => p.faehigkeit === f);
  // Fähigkeiten mit Probe: belegte stehen in den Fähigkeiten, nicht belegte daneben durchgestrichen
  const widerlegt = (m: ModellSicht) => (m.steckbrief.geprueft ?? []).filter((p) => !p.belegt);
</script>

<div class="anbieter" class:knapp>
  <div class="am-schluessel klein" title="Die Grenzen gelten je Schlüssel für alle Modelle zusammen, gleitend über 60 Sekunden; die Leitstelle hält sie ein. Token offener Anfragen sind geschätzt, nach der Antwort zählt der echte Verbrauch.">
    <span class="leise">Schlüssel, letzte 60 s:</span>
    {#each grenzen as g (g.wort)}
      <span class:akzent={g.grenze != null && g.n >= g.grenze}><b class="zahl">{menge(g.n)}</b>{#if g.grenze != null}&nbsp;von <span class="zahl">{menge(g.grenze)}</span>{/if} {g.wort}</span>
    {/each}
    {#if dienst.nutzung.geschaetzt}<span class="leise">(teils geschätzt)</span>{/if}
    {#if gesperrt}<span class="zustand wartet"><i class="fa-solid fa-hand"></i>gesperrt bis {uhrzeit(dienst.gesperrt_bis_s, true)}</span>
    {:else if dienst.frei_in_s > 0}<span class="zustand wartet" title={dienst.frei_grund}><i class="fa-solid fa-hourglass-half"></i>{dienst.frei_grund}</span>{/if}
  </div>
  <ul>
    {#each modelle as m (m.kennung)}
      {@const a = art(m.steckbrief)}
      <li>
        <div class="am-kopf">
          <b>{m.name}</b>
          {#if a}<span class="am-art" title={a.satz}>{a.wort}</span>{/if}
          <span class="zustand {gesperrt ? 'wartet' : m.zustand === 'rechnet' ? 'laeuft' : 'fertig'}" title="Der Anbieter lädt seine Modelle selbst; die Leitstelle steuert keinen Speicher (rechnet beim Anbieter)">
            <i class="fa-solid {gesperrt ? 'fa-hand' : 'fa-cloud'}"></i>{zustand(m)}</span>
        </div>
        <div class="am-werte klein">
          <span title="Größter Kontext laut Anbieter (max_model_len)">Kontext <b class="zahl">{m.steckbrief.kontext ? zahl(m.steckbrief.kontext) : '-'}</b> Token</span>
          <span title={a?.satz ?? 'Parameter gesamt und je Schritt aktiv'}>{parameterText(m.steckbrief)}</span>
          <span title="Laufende und zugeteilte Aufträge auf diesem Modell; die Plätze gelten je Modell">Plätze <b class="zahl">{m.belegt}</b> von <span class="zahl">{m.plaetze}</span> belegt</span>
          <span title="Anfragen und Token dieses Modells in den letzten 60 Sekunden{m.nutzung.geschaetzt ? ', teils geschätzt' : ''}">{nutzungText(m.nutzung)}</span>
        </div>
        {#if !knapp}
          <div class="am-faehig">
            {#each m.faehigkeiten.filter((f) => f !== 'uebersetzen' && f !== 'werkzeug') as f (f)}
              {@const p = probe(m, f)}
              <span title={p ? `${FAEHIGKEIT[f].wort}: belegt durch Probe am ${uhrzeit(p.zeit_s)} (${p.meldung})` : undefined}><Faehigkeit wert={f} />{#if p}<i class="fa-solid fa-flask am-probe" aria-label="geprüft"></i>{/if}</span>
            {/each}
            {#each widerlegt(m) as p (p.faehigkeit)}
              <span class="am-widerlegt klein" title="Nicht belegt durch Probe am {uhrzeit(p.zeit_s)}: {p.meldung}"><i class="fa-solid fa-flask"></i> {FAEHIGKEIT[p.faehigkeit].wort} nicht belegt</span>
            {/each}
          </div>
        {/if}
      </li>
    {/each}
  </ul>
</div>

<style>
  .anbieter { display: flex; flex-direction: column; gap: var(--a2); min-width: 0; }
  .am-schluessel { display: flex; flex-wrap: wrap; gap: 2px var(--a3); align-items: center; color: var(--text-2); }
  .am-schluessel b { font-family: var(--schrift-zahl); font-weight: 600; color: var(--text); }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--a2); grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); }
  li { display: flex; flex-direction: column; gap: 6px; padding: var(--a2) var(--a3); background: var(--karte); border-radius: var(--r2); min-width: 0; }
  .knapp li { background: var(--bereich); }
  .am-kopf { display: flex; flex-wrap: wrap; align-items: center; gap: var(--a1) var(--a2); }
  .am-kopf b { overflow-wrap: anywhere; }
  .am-kopf .zustand { margin-left: auto; }
  .am-art { font-size: var(--marke); font-weight: 700; color: var(--akzent); cursor: help; }
  .am-werte { display: flex; flex-wrap: wrap; gap: 2px var(--a3); color: var(--text-2); }
  .am-werte b { font-family: var(--schrift-zahl); font-weight: 600; color: var(--text); }
  .am-faehig { display: flex; flex-wrap: wrap; gap: var(--a1); align-items: center; }
  .am-faehig .am-probe { margin-left: 4px; color: var(--text-3); font-size: var(--marke); }
  .am-widerlegt { color: var(--text-3); text-decoration: line-through; }
</style>
