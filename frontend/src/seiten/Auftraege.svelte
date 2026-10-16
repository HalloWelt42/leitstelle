<script lang="ts">
  import { untrack } from 'svelte';
  import { api } from '../lib/api';
  import { dauer, uhrzeit, zahl } from '../lib/format';
  import { kanal } from '../lib/kanal.svelte';
  import type { AuftragEintrag, AuftragSicht, Auftragszustand, Kennzahlen, Lagebild, Schritt } from '../lib/typen.gen';
  import { weg } from '../lib/weg.svelte';
  import { AUFTRAGSZUSTAND, FAEHIGKEIT, GRUND, PRIORITAET } from '../lib/wort';
  import Faehigkeit from '../teile/Faehigkeit.svelte';
  import StoppDialog from '../teile/StoppDialog.svelte';
  import ZoneMarke from '../teile/ZoneMarke.svelte';
  import Zustand from '../teile/Zustand.svelte';

  let { bild }: { bild: Lagebild } = $props();

  const SEITE = 50;
  let reiter = $state<'offen' | 'verlauf'>('offen');
  let filterAnwendung = $state('');
  let filterZustand = $state<'' | Auftragszustand>('');
  let verlauf = $state<AuftragEintrag[]>([]);
  let gesamt = $state(0);
  let laedt = $state(false);
  let kennzahlen = $state<Kennzahlen | null>(null);
  let gewaehltEintrag = $state<AuftragEintrag | null>(null);
  let stoppen = $state<AuftragSicht | null>(null);
  let jetzt = $state(kanal.jetzt());
  let fussElement = $state<HTMLElement | null>(null);
  let rollElement = $state<HTMLElement | null>(null);

  $effect(() => {
    const t = setInterval(() => (jetzt = kanal.jetzt()), 1000);
    return () => clearInterval(t);
  });

  async function verlaufLaden(neu: boolean) {
    if (untrack(() => laedt)) return;
    laedt = true;
    try {
      const ab = neu ? 0 : untrack(() => verlauf.length);
      const s = await api.auftraege(ab, SEITE, { anwendung: filterAnwendung || undefined, zustand: filterZustand || undefined });
      verlauf = neu ? s.eintraege : [...untrack(() => verlauf), ...s.eintraege];
      gesamt = s.gesamt;
    } finally {
      laedt = false;
    }
  }

  // Verlauf und Kennzahlen neu, wenn ein Auftrag endet oder die Filter sich ändern
  $effect(() => {
    kanal.verlaufStand;
    filterAnwendung;
    filterZustand;
    untrack(() => verlaufLaden(true));
    api.kennzahlen().then((k) => (kennzahlen = k)).catch(() => {});
  });

  // Nachladen beim Rollen: Wächter am Fuß, Bezug ist das Rollfeld
  $effect(() => {
    if (!fussElement || !rollElement || reiter !== 'verlauf') return;
    const w = new IntersectionObserver((e) => {
      if (e[0].isIntersecting && untrack(() => verlauf.length < gesamt)) verlaufLaden(false);
    }, { root: rollElement, rootMargin: '200px' });
    w.observe(fussElement);
    return () => w.disconnect();
  });

  const offenGewaehlt = $derived(bild.auftraege.find((a) => a.kennung === weg.teil) ?? null);
  // Abgeschlossenen Auftrag aus dem Verlauf holen, wenn er gewählt ist und nicht mehr offen
  $effect(() => {
    const k = weg.teil;
    kanal.verlaufStand;
    if (!k || untrack(() => offenGewaehlt)) {
      gewaehltEintrag = null;
      return;
    }
    api.auftrag(k).then((e) => (gewaehltEintrag = e)).catch(() => (gewaehltEintrag = null));
  });

  const laufend = $derived(bild.auftraege.filter((a) => a.zustand === 'laeuft'));
  const wartend = $derived(bild.auftraege.filter((a) => a.zustand !== 'laeuft'));
  const anwendung = (k: string) => bild.anwendungen.find((a) => a.kennung === k)?.name ?? 'unbekannt';
  const knotenName = (k: string | null | undefined) => bild.knoten.find((x) => x.kennung === k)?.name ?? (k ? 'unbekannt' : 'Extern');
  const dienstName = (k: string | null | undefined) => bild.dienste.find((d) => d.kennung === k)?.name ?? '';
  const knotenZone = (k: string | null | undefined) => bild.knoten.find((x) => x.kennung === k)?.zone ?? 'extern';

  // Gemeinsame Sicht auf einen offenen oder abgeschlossenen Auftrag
  interface Einzel { kennung: string; titel: string; anwendung: string; faehigkeit: AuftragSicht['faehigkeit']; prioritaet: number; zustand: Auftragszustand;
    begruendung: string; modell: string | null; dienst: string | null; knoten: string | null; extern: boolean; eingang_s: number; start_s: number | null;
    ende_s: number | null; schritte: Schritt[]; umgeleitet: number; grund: string | null; erstes_stueck_s: number | null; token_ein: number | null;
    token_aus: number | null; teilergebnis_zeichen: number; offen: boolean; auslaufend: boolean }

  const einzel = $derived.by((): Einzel | null => {
    const o = offenGewaehlt;
    if (o) return { ...o, ende_s: null, grund: null, erstes_stueck_s: null, token_ein: null, token_aus: null, teilergebnis_zeichen: 0, offen: true };
    const e = gewaehltEintrag;
    if (e) return { ...e, prioritaet: e.prioritaet, modell: e.modell_name ?? null, offen: false, auslaufend: false, faehigkeit: e.faehigkeit } as Einzel;
    return null;
  });

  // Prozesskette: Angenommen, Wartet (falls gewartet), Zugeteilt (falls geladen werden musste), Läuft, Ende.
  // Jede Stufe hat eine Nummer; erledigt ist, was vor der aktuellen liegt.
  const STUFE: Record<Auftragszustand, number> = { eingereiht: 1, wartet_speicher: 1, zugeteilt: 2, laeuft: 3, pausiert: 3, fertig: 4, abgebrochen: 4, fehlgeschlagen: 4, abgelehnt: 4 };
  const kette = $derived.by(() => {
    if (!einzel) return [];
    const z = einzel.zustand;
    const jetztStufe = STUFE[z];
    const besucht = new Set(einzel.schritte.map((s) => s.zustand));
    const gewartet = besucht.has('wartet_speicher') || einzel.schritte.filter((s) => s.zustand === 'eingereiht').length > 1 || jetztStufe === 1;
    const glieder: { wort: string; symbol: string; nr: number }[] = [{ wort: 'Angenommen', symbol: 'fa-inbox', nr: 0 }];
    if (gewartet) glieder.push({ wort: 'Wartet', symbol: 'fa-hourglass-half', nr: 1 });
    if (besucht.has('zugeteilt') || z === 'zugeteilt') glieder.push({ wort: 'Zugeteilt', symbol: 'fa-brain', nr: 2 });
    glieder.push({ wort: 'Läuft', symbol: 'fa-gear', nr: 3 });
    glieder.push({ wort: jetztStufe === 4 ? AUFTRAGSZUSTAND[z].wort : 'Fertig', symbol: 'fa-flag-checkered', nr: 4 });
    return glieder.map((g) => ({ ...g, stand: (g.nr < jetztStufe || (g.nr === 4 && jetztStufe === 4) ? 'erledigt' : g.nr === jetztStufe ? 'jetzt' : 'offen') as 'erledigt' | 'jetzt' | 'offen' }));
  });

  function waehlen(k: string) {
    weg.gehe('auftraege', k, true);
  }
</script>

{#snippet zeile(a: AuftragSicht | AuftragEintrag, offen: boolean)}
  {@const f = FAEHIGKEIT[a.faehigkeit]}
  {@const laeuft = a.zustand === 'laeuft'}
  {@const modell = 'modell_name' in a ? a.modell_name : (a as AuftragSicht).modell}
  <div class="auftrag" class:gewaehlt={weg.teil === a.kennung} style="--f:{f.farbe};--f-rgb:{f.rgb}" role="button" tabindex="0"
       onclick={() => waehlen(a.kennung)} onkeydown={(e) => e.key === 'Enter' && waehlen(a.kennung)}>
    <div class="symbol" title={f.wort}><i class="fa-solid {f.symbol}"></i></div>
    <div style="min-width:0">
      <div class="titel">{a.titel || f.wort}</div>
      <div class="zweit"><span class="app">{anwendung(a.anwendung)}</span>{#if modell}<span>{modell}{a.knoten ? ` · ${knotenName(a.knoten)}` : a.extern ? ' · Extern' : ''}</span>{/if}
        <Zustand art="auftrag" wert={a.zustand} dreht /></div>
      {#if laeuft}<div class="balken lebt unbestimmt"><b></b></div>
      {:else if a.zustand === 'fertig'}<div class="balken fertig"><b style="width:100%"></b></div>
      {:else if a.zustand === 'fehlgeschlagen' || a.zustand === 'abgelehnt'}<div class="balken fehler"><b style="width:100%"></b></div>{/if}
      {#if !laeuft && a.begruendung}<div class="grund" title={a.begruendung}>{a.begruendung}</div>{/if}
    </div>
    <div class="rest">{laeuft ? 'Seit' : offen ? 'Wartet' : 'Dauer'}<b>{laeuft ? dauer(jetzt - (a.start_s ?? jetzt)) : offen ? dauer(jetzt - a.eingang_s)
      : 'ende_s' in a && a.ende_s && a.start_s ? dauer(a.ende_s - a.start_s) : '-'}</b></div>
    <div class="prio {PRIORITAET[a.prioritaet].klasse}" title="Priorität {PRIORITAET[a.prioritaet].wort}">{PRIORITAET[a.prioritaet].wort}</div>
    <div class="knoepfe">
      {#if offen}
        <button class="knopf ohne symbol klein gefahr" onclick={(e) => { e.stopPropagation(); stoppen = a as AuftragSicht; }}
                title={laeuft ? 'Stoppen: auslaufen lassen oder sofort abbrechen' : 'Verwerfen: die Anwendung bekommt eine Abbruchnachricht'}>
          <i class="fa-solid {laeuft ? 'fa-stop' : 'fa-xmark'}"></i></button>
      {:else}<span style="width:36px;display:inline-block"></span>{/if}
    </div>
  </div>
{/snippet}

<div class="seiteninhalt seite-auftraege">
  <div class="rahmen-kopf">
    <div class="seitenkopf">
      <h1>Aufträge</h1><span class="zahl">{bild.auftraege.length}</span>
    </div>
    <div class="kennzahlen">
      <div class="kennzahl laeuft"><b>{laufend.length}</b><span>Läuft</span></div>
      <div class="kennzahl wartet"><b>{wartend.length}</b><span>Wartet</span></div>
      <div class="kennzahl erfolg"><b>{kennzahlen?.fertig ?? '-'}</b><span>Heute fertig</span>
        {#if kennzahlen?.erstes_stueck_mittel_s != null}<small>erstes Stück im Mittel {dauer(kennzahlen.erstes_stueck_mittel_s)}</small>{/if}</div>
      <div class="kennzahl fehler"><b>{kennzahlen?.fehler ?? '-'}</b><span>Fehler heute</span></div>
      <div class="kennzahl"><b>{kennzahlen?.abgebrochen ?? '-'}</b><span>Abgebrochen heute</span></div>
    </div>
    <div class="reiterleiste">
      <div class="reiter">
        <button class:aktiv={reiter === 'offen'} onclick={() => (reiter = 'offen')}><i class="fa-solid fa-circle-play"></i> Offen <span class="zaehler">{bild.auftraege.length}</span></button>
        <button class:aktiv={reiter === 'verlauf'} onclick={() => (reiter = 'verlauf')}><i class="fa-solid fa-clock-rotate-left"></i> Verlauf <span class="zaehler">{zahl(gesamt)}</span></button>
      </div>
      {#if reiter === 'verlauf'}
        <div class="rechts">
          <select class="eingabe" bind:value={filterAnwendung} title="Verlauf nach Anwendung filtern" style="height: 36px">
            <option value="">Alle Anwendungen</option>
            {#each bild.anwendungen as a (a.kennung)}<option value={a.kennung}>{a.name}</option>{/each}
          </select>
          <select class="eingabe" bind:value={filterZustand} title="Verlauf nach Ausgang filtern" style="height: 36px">
            <option value="">Alle Ausgänge</option><option value="fertig">Fertig</option><option value="abgebrochen">Abgebrochen</option>
            <option value="fehlgeschlagen">Fehler</option><option value="abgelehnt">Abgelehnt</option>
          </select>
        </div>
      {/if}
    </div>
  </div>

  <div class="spalten breit-rechts">
    <div class="rollfeld" bind:this={rollElement}>
      {#if reiter === 'offen'}
        {#if laufend.length}<div class="gruppe"><span class="etikett">Läuft</span><span class="zaehler">{laufend.length}</span></div>
          {#each laufend as a (a.kennung)}{@render zeile(a, true)}{/each}{/if}
        {#if wartend.length}<div class="gruppe"><span class="etikett">Wartet</span><span class="zaehler">{wartend.length}</span></div>
          {#each wartend as a (a.kennung)}{@render zeile(a, true)}{/each}{/if}
        {#if !bild.auftraege.length}
          <div class="leer"><i class="fa-solid fa-mug-hot"></i><h2>Nichts offen</h2><p>Alles ist abgearbeitet. Abgeschlossene Aufträge stehen im Verlauf.</p>
            <button class="knopf" onclick={() => (reiter = 'verlauf')}>Zum Verlauf</button></div>
        {/if}
      {:else}
        {#each verlauf as a (a.kennung)}{@render zeile(a, false)}{/each}
        {#if !verlauf.length && !laedt}<div class="leer"><i class="fa-solid fa-clock-rotate-left"></i><h2>Noch kein Verlauf</h2><p>Hier steht jeder abgeschlossene Auftrag mit Dauer, Modell und Zeitleiste.</p></div>{/if}
        <div class="listenfuss" bind:this={fussElement}>{verlauf.length < gesamt ? `noch ${zahl(gesamt - verlauf.length)} weitere` : verlauf.length ? `alle ${zahl(gesamt)} geladen` : ''}</div>
      {/if}
    </div>

    <div class="rollfeld">
      {#if einzel}
        <div class="karte einzel">
          <h2>{einzel.titel || FAEHIGKEIT[einzel.faehigkeit].wort}<Zustand art="auftrag" wert={einzel.zustand} dreht /></h2>
          <div class="unter">{anwendung(einzel.anwendung)} · Auftrag <span class="zahl">{einzel.kennung.slice(0, 8)}</span> · angenommen {uhrzeit(einzel.eingang_s, true)} · Priorität {PRIORITAET[einzel.prioritaet].wort}{einzel.auslaufend ? ' · läuft aus, danach gesperrt' : ''}</div>
          <div class="kette" style="margin-top: var(--ls-a4)">
            {#each kette as g, i (g.wort)}
              <span class="schritt {g.stand}"><i class={g.stand === 'erledigt' ? 'fa-solid fa-check' : g.stand === 'jetzt' ? `fa-solid ${g.symbol} fa-spin` : 'fa-regular fa-circle'}></i>{g.wort}</span>
              {#if i < kette.length - 1}<span class="pfeil" class:erledigt={g.stand === 'erledigt' && kette[i + 1].stand === 'erledigt'} class:laeuft={g.stand === 'erledigt' && kette[i + 1].stand === 'jetzt'}></span>{/if}
            {/each}
          </div>
          {#if einzel.zustand === 'laeuft'}<div class="balken lebt dick unbestimmt" style="margin-top: var(--ls-a4)"><b></b></div>{/if}
          <dl class="angaben">
            <dt>Fähigkeit</dt><dd><Faehigkeit wert={einzel.faehigkeit} /></dd>
            {#if einzel.modell}<dt>Modell</dt><dd>{einzel.modell}</dd>{/if}
            {#if einzel.dienst || einzel.extern}<dt>Dienst</dt><dd>{dienstName(einzel.dienst)} {einzel.extern ? '' : `auf ${knotenName(einzel.knoten)}`} <ZoneMarke wert={einzel.extern ? 'extern' : knotenZone(einzel.knoten)} /></dd>{/if}
            <dt>Weg der Anfrage</dt><dd>OpenAI-Fassade, Arbeit ohne Lese-Zeitgrenze</dd>
            <dt>Wartezeit</dt><dd class="zahl">{einzel.start_s ? dauer(einzel.start_s - einzel.eingang_s) : einzel.offen ? `${dauer(jetzt - einzel.eingang_s)} bisher` : '-'}</dd>
            {#if !einzel.offen}
              <dt>Rechenzeit</dt><dd class="zahl">{einzel.start_s && einzel.ende_s ? dauer(einzel.ende_s - einzel.start_s) : '-'}</dd>
              <dt>Erstes Stück</dt><dd class="zahl">{einzel.erstes_stueck_s != null ? dauer(einzel.erstes_stueck_s) : '-'}</dd>
              <dt>Token</dt><dd class="zahl">{einzel.token_ein != null ? `${zahl(einzel.token_ein)} hinein, ${zahl(einzel.token_aus)} heraus` : 'vom Dienst nicht gemeldet'}</dd>
              {#if einzel.grund}<dt>Grund</dt><dd>{GRUND[einzel.grund] ?? einzel.grund}{einzel.teilergebnis_zeichen ? `, Teiltext ${zahl(einzel.teilergebnis_zeichen)} Zeichen geliefert` : ''}</dd>{/if}
            {/if}
            {#if einzel.umgeleitet}<dt>Selbststeuerung</dt><dd>{einzel.umgeleitet}-mal umgeleitet</dd>{/if}
          </dl>
          {#if einzel.offen}
            <div class="tun">
              <button class="knopf gefahr" onclick={() => (stoppen = offenGewaehlt)}><i class="fa-solid fa-hand"></i> Stoppen</button>
            </div>
          {/if}
        </div>
        <div class="karte">
          <h3><i class="fa-solid fa-clock"></i>Zeitleiste</h3>
          <div class="zeitleiste">
            {#each einzel.schritte as s, i (i)}
              <div class="e" class:jetzt={einzel.offen && i === einzel.schritte.length - 1}><span class="zeit zahl">{uhrzeit(s.zeit_s, true)}</span><i class="fa-solid fa-circle"></i>
                <span><b>{i === 0 ? 'Angenommen' : AUFTRAGSZUSTAND[s.zustand].wort}</b>{s.text ? `: ${i === 0 ? s.text.replace(/^angenommen /, '') : s.text}` : ''}</span></div>
            {/each}
          </div>
        </div>
      {:else}
        <div class="leer"><i class="fa-solid fa-hand-pointer"></i><h2>Auftrag wählen</h2><p>Links einen Auftrag anklicken: Prozesskette, Zuteilung, Messwerte und Zeitleiste erscheinen hier.</p></div>
      {/if}
    </div>
  </div>
</div>

{#if stoppen}<StoppDialog auftrag={stoppen} schliessen={() => (stoppen = null)} />{/if}
