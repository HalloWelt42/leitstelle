<script lang="ts">
  // Regeln der Selbststeuerung: je Maßnahme ein Schalter mit Erklärung, darunter ihre Werte; je Gruppe die gemeinsamen
  // Werte. Bedeutung, Einheit, Grenzen und Vorgabe kommen vom Kern, die gültigen Werte live aus dem Lagebild. Jede
  // Änderung wirkt sofort und steht mit alt und neu im Prüfprotokoll. Kein Graph-Editor (Staffel 5).
  import { meldungen, tun } from '../lib/meldung.svelte';
  import { EINHEIT, aktuell, ausEingabe, eingabeWert, grenzeEingabe, regelbeschreibung, schalten, wertText } from '../lib/regelwerk.svelte';
  import type { Lagebild, Massnahmenart, Regelgruppe, RegelwertSicht } from '../lib/typen.gen';
  import { weg } from '../lib/weg.svelte';

  let { bild }: { bild: Lagebild } = $props();

  $effect(() => {
    regelbeschreibung.laden().catch((f) => meldungen.fehler(f));
  });

  const SYMBOL: Record<Regelgruppe, string> = {
    selbststeuerung: 'fa-wand-magic-sparkles', speicher: 'fa-memory', ausweichen: 'fa-shuffle', hintergrund: 'fa-layer-group',
    einbettung: 'fa-diagram-project', last: 'fa-microchip',
  };
  const gruppen = $derived(regelbeschreibung.sicht?.gruppen ?? []);
  const gruppe = $derived(gruppen.find((g) => g.gruppe === weg.teil) ?? gruppen[0]);
  const r = $derived(bild.regelwerk);
  const an = (art: Massnahmenart) => r.szenarien_an[art] ?? false;
  const wert = (w: RegelwertSicht) => aktuell(r, w.feld);
  const vonHand = (w: RegelwertSicht) => wert(w) !== w.vorgabe;
  const abweichend = (g: (typeof gruppen)[number]) => g.werte.filter(vonHand).length + g.szenarien.filter((s) => an(s.art) !== s.vorgabe).length;
  const alleSzenarien = $derived(gruppen.flatMap((g) => g.szenarien));
  const automatik = $derived(gruppen.flatMap((g) => g.werte).find((w) => w.feld === 'automatik'));

  async function aendern(w: RegelwertSicht, neu: string | number | boolean, feld?: HTMLInputElement) {
    const ok = await tun(() => regelbeschreibung.aendern({ werte: { [w.feld]: neu } }), `${w.titel}: ${wertText(w, neu)}`);
    if (ok === undefined && feld) feld.value = String(eingabeWert(w, wert(w)));   // abgelehnt: wieder der gültige Wert
  }

  function eingegeben(w: RegelwertSicht, feld: HTMLInputElement) {
    const zahl = feld.valueAsNumber;
    if (!Number.isFinite(zahl)) {
      meldungen.zeigen(`${w.titel} braucht eine Zahl`, 'fehler');
      feld.value = String(eingabeWert(w, wert(w)));
      return;
    }
    const neu = ausEingabe(w, zahl);
    if (neu !== wert(w)) aendern(w, neu, feld);
  }

  const umschalten = (art: Massnahmenart, titel: string) => tun(() => schalten(art, !an(art)), `Regel ${titel} ${an(art) ? 'aus' : 'an'}`);
</script>

{#snippet regelwert(w: RegelwertSicht)}
  <div class="einstellung">
    <div>
      <div class="name">{w.titel}{#if vonHand(w)}<span class="marke-hand" title="Weicht von der Vorgabe ab">von Hand</span>{/if}</div>
      <div class="erklaerung">{w.erklaerung} Vorgabe {wertText(w, w.vorgabe)}{#if w.min != null && w.max != null}, einstellbar von {wertText(w, w.min)} bis {wertText(w, w.max)}{/if}.</div>
    </div>
    <div class="wert">
      {#if w.einheit === 'schalter'}
        <span class="leise klein">{wert(w) ? 'an' : 'aus'}</span>
        <button class="schalter" class:an={!!wert(w)} role="switch" aria-checked={!!wert(w)} aria-label={w.titel}
                title="{w.titel}: {wert(w) ? 'an, ausschalten' : 'aus, einschalten'}" onclick={() => aendern(w, !wert(w))}></button>
      {:else if w.einheit === 'wahl'}
        <span class="stufen" title={w.erklaerung}>
          {#each w.wahl as x (x.wert)}<button class:an={wert(w) === x.wert} onclick={() => wert(w) !== x.wert && aendern(w, x.wert)}>{x.wort}</button>{/each}
        </span>
      {:else}
        <input class="eingabe" type="number" value={eingabeWert(w, wert(w))} min={grenzeEingabe(w, w.min)} max={grenzeEingabe(w, w.max)}
               step={grenzeEingabe(w, w.schritt) ?? 'any'} aria-label={w.titel} title="{w.titel}: {wertText(w, wert(w))}; Eingabe mit Enter oder beim Verlassen"
               onchange={(e) => eingegeben(w, e.currentTarget)} />
        <span class="einheit">{EINHEIT[w.einheit]}</span>
      {/if}
      {#if vonHand(w)}<button class="knopf ohne symbol klein" title="Zurück auf die Vorgabe ({wertText(w, w.vorgabe)})" aria-label="Vorgabe"
                              onclick={() => aendern(w, w.vorgabe)}><i class="fa-solid fa-rotate-left"></i></button>{/if}
    </div>
  </div>
{/snippet}

<div class="seiteninhalt seite-regeln">
  <div class="rahmen-kopf">
    <div class="seitenkopf">
      <h1>Regeln</h1>
      <div class="unterzeile">Was die Leitstelle von selbst tut und mit welchen Werten. Jede Änderung wirkt sofort und steht mit altem und neuem Wert im Prüfprotokoll.</div>
    </div>
    {#if gruppen.length}
      <div class="kennzahlen">
        <div class="kennzahl"><b>{alleSzenarien.filter((s) => an(s.art)).length}<span class="von">&nbsp;/ {alleSzenarien.length}</span></b><span>Maßnahmen an</span></div>
        <div class="kennzahl" class:wartet={r.automatik !== 'selbst'}><b class="wort">{automatik ? wertText(automatik, r.automatik) : '-'}</b><span>Automatik</span>
          {#if r.automatik !== 'selbst'}<small>{r.automatik === 'aus' ? 'keine Regel greift' : 'nur Vorschläge, nichts geschieht'}</small>{/if}</div>
        <div class="kennzahl"><b>{gruppen.reduce((s, g) => s + abweichend(g), 0)}</b><span>Von Hand</span><small>abweichend von der Vorgabe</small></div>
      </div>
      <div class="untergruppen" role="tablist">
        {#each gruppen as g (g.gruppe)}
          <button role="tab" aria-selected={gruppe?.gruppe === g.gruppe} class:aktiv={gruppe?.gruppe === g.gruppe} onclick={() => weg.gehe('regeln', g.gruppe, true)}
                  title={g.erklaerung}><i class="fa-solid {SYMBOL[g.gruppe]}"></i>{g.titel}{#if abweichend(g)}<span class="reiter-punkt" title="{abweichend(g)} von Hand geändert"></span>{/if}</button>
        {/each}
      </div>
    {/if}
  </div>

  <div class="rollfeld">
    {#if !gruppe}
      <div class="leer"><i class="fa-solid fa-scale-balanced"></i><h2>Regeln werden geladen</h2></div>
    {:else}
      <p class="vorwort">{gruppe.erklaerung}{#if r.automatik !== 'selbst'} Die Automatik steht auf {automatik ? wertText(automatik, r.automatik) : ''}: keine Maßnahme greift von selbst.{/if}</p>
      {#each gruppe.szenarien as s (s.art)}
        <section class="bereich regel">
          <div class="einstellung kopfzeile">
            <div>
              <div class="name"><h2>{s.titel}</h2>{#if an(s.art) !== s.vorgabe}<span class="marke-hand" title="Weicht von der Vorgabe ab">von Hand</span>{/if}</div>
              <div class="erklaerung">{s.erklaerung} Ab Werk {s.vorgabe ? 'an' : 'aus'}.</div>
            </div>
            <div class="wert">
              <span class="zustand {an(s.art) ? 'fertig' : 'aus'}">{an(s.art) ? 'an' : 'aus'}</span>
              <button class="schalter" class:an={an(s.art)} role="switch" aria-checked={an(s.art)} aria-label="Regel {s.titel}"
                      title="Regel {s.titel}: {an(s.art) ? 'an, ausschalten' : 'aus, einschalten'}" onclick={() => umschalten(s.art, s.titel)}></button>
            </div>
          </div>
          {#each gruppe.werte.filter((w) => w.szenario === s.art) as w (w.feld)}{@render regelwert(w)}{/each}
        </section>
      {/each}
      {#if gruppe.werte.some((w) => !w.szenario)}
        <section class="bereich regel">
          {#if gruppe.szenarien.length}<h2 class="gemeinsam">Für mehrere Regeln</h2>{/if}
          {#each gruppe.werte.filter((w) => !w.szenario) as w (w.feld)}{@render regelwert(w)}{/each}
        </section>
      {/if}
    {/if}
  </div>
</div>

<style>
  .vorwort { color: var(--text-2); font-size: var(--klein); margin: 0 0 var(--a3); max-width: 900px; }
  .regel { padding: var(--a2) var(--a4); }
  .regel + .regel { margin-top: var(--a3); }
  .regel .einstellung { padding-left: 0; padding-right: 0; }
  .regel .kopfzeile .name h2 { font-size: var(--gross); margin: 0; }
  .regel .kopfzeile .wert .zustand { min-width: 0; }
  .gemeinsam { font-size: var(--gross); margin: var(--a2) 0 0; }
  .marke-hand { font-size: var(--marke); font-weight: 700; color: var(--akzent); letter-spacing: 0.04em; }
  .kennzahl b .von { font-size: var(--gross); color: var(--text-3); }
  .kennzahl b.wort { font-family: var(--schrift); }
</style>
