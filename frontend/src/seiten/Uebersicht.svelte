<script lang="ts">
  import { api } from '../lib/api';
  import { dauer, gb, prozent, uhrzeit } from '../lib/format';
  import { kanal } from '../lib/kanal.svelte';
  import { tun } from '../lib/meldung.svelte';
  import type { AuftragEintrag, AuftragSicht, Kennzahlen, Lagebild } from '../lib/typen.gen';
  import { weg } from '../lib/weg.svelte';
  import { FAEHIGKEIT, KNOTENZUSTAND, LAGE, MASSNAHME, PRIORITAET, knotenzustand } from '../lib/wort';
  import Faehigkeit from '../teile/Faehigkeit.svelte';
  import Netzbild from '../teile/Netzbild.svelte';
  import Speicherbalken from '../teile/Speicherbalken.svelte';
  import StoppDialog from '../teile/StoppDialog.svelte';
  import Zustand from '../teile/Zustand.svelte';

  let { bild }: { bild: Lagebild } = $props();

  let kennzahlen = $state<Kennzahlen | null>(null);
  let zuletzt = $state<AuftragEintrag[]>([]);
  const NACHLEUCHTEN_MS = 6000;
  let stoppen = $state<AuftragSicht | null>(null);
  let jetzt = $state(kanal.jetzt());

  // Tageskennzahlen beim Öffnen und nach jedem Auftragsende neu
  $effect(() => {
    kanal.verlaufStand;
    api.kennzahlen().then((k) => (kennzahlen = k)).catch(() => {});
    api.auftraege(0, 6).then((s) => (zuletzt = s.eintraege)).catch(() => {});
  });
  // Anwendungen mit Bewegung in den letzten Sekunden: das Netzbild lässt sie nachleuchten
  const kuerzlich = $derived(Object.fromEntries(Object.entries(kanal.aktivitaet).filter(([, b]) => (jetzt - kanal.versatz) * 1000 - b.zeit < NACHLEUCHTEN_MS)));
  $effect(() => {
    const t = setInterval(() => (jetzt = kanal.jetzt()), 1000);
    return () => clearInterval(t);
  });

  const laufend = $derived(bild.auftraege.filter((a) => a.zustand === 'laeuft'));
  const wartend = $derived(bild.auftraege.filter((a) => a.zustand !== 'laeuft'));
  const aufSpeicher = $derived(wartend.filter((a) => a.zustand === 'wartet_speicher').length);
  const erreichbar = $derived(bild.knoten.filter((k) => k.erreichbar));
  const namen = (z: string) => bild.knoten.filter((k) => knotenzustand(k) === z).map((k) => k.name);
  const anwendung = (k: string) => bild.anwendungen.find((a) => a.kennung === k)?.name ?? 'unbekannt';
  const knotenName = (k: string | null) => bild.knoten.find((x) => x.kennung === k)?.name ?? (k ? 'Extern' : '');
  const lagesatz = $derived(bild.modus === 'normal' ? LAGE[bild.lage].wort : bild.modus === 'halt' ? 'Gestoppt' : 'Läuft aus');
  // Zugriffe am Leitstand vorbei: nur echte Umgehungen (die Leitstelle selbst auf dem direkten Weg zählt der Kern nicht mit)
  const vorbei = $derived(bild.knoten.filter((k) => k.fremde.umgehungen > 0));
  const umgehungen = $derived(vorbei.reduce((s, k) => s + k.fremde.umgehungen, 0));
  const ausgefuehrt = $derived(bild.massnahmen.filter((m) => m.zustand === 'ausgefuehrt' || m.zustand === 'gesperrt' || m.zustand === 'geplant').slice(0, 6));

  function meldungsart(text: string): string {
    if (/nicht erreichbar|abgelehnt|gescheitert|Fehler/i.test(text)) return 'gefahr';
    if (/Hauptregler|entladen|Flattern|Speicher|Leitstand vorbei/i.test(text)) return 'warnung';
    if (/geladen in|wieder erreichbar|bereit|aufgewacht/i.test(text)) return 'erfolg';
    return '';
  }
</script>

<div class="seiteninhalt seite-uebersicht">
  <div class="rahmen-kopf">
    <div class="ueber-kopf">
      <h1>Übersicht</h1>
      <span class="lagezeile" title={bild.lage_grund}><b class:ruhig={bild.lage === 'ruhig' && bild.modus === 'normal'}>{lagesatz}:</b> {bild.modus === 'normal' ? bild.lage_grund : bild.modus === 'halt' ? 'nichts wird gerechnet.' : 'laufende Aufträge enden, Neues wartet.'}</span>
      <div class="aktionen">
        <button class="knopf" onclick={() => tun(() => api.hauptregler(bild.modus, !bild.hintergrund_erlaubt), bild.hintergrund_erlaubt ? 'Hintergrund angehalten' : 'Hintergrund läuft wieder')}
                title="Alle Aufträge der Priorität Hintergrund anhalten oder wieder laufen lassen; interaktive Anwendungen behalten Vorrang">
          <i class="fa-solid {bild.hintergrund_erlaubt ? 'fa-pause' : 'fa-play'}"></i> {bild.hintergrund_erlaubt ? 'Hintergrund anhalten' : 'Hintergrund fortsetzen'}</button>
        <a class="knopf" href={weg.pfad('modelle', 'freigeben')} onclick={(e) => weg.klick(e, 'modelle', 'freigeben')}
           title="Speicher freigeben: zeigt zuerst, welche Modelle entladen würden; nichts passiert ohne Bestätigung"><i class="fa-solid fa-broom"></i> Speicher freigeben</a>
      </div>
    </div>
    <div class="kennzahlen">
      <div class="kennzahl laeuft"><b>{laufend.length}</b><span>Läuft</span></div>
      <div class="kennzahl wartet"><b>{wartend.length}</b><span>Wartet</span>{#if aufSpeicher}<small>{aufSpeicher} davon auf Speicher</small>{/if}</div>
      <div class="kennzahl erfolg"><b>{kennzahlen?.fertig ?? '-'}</b><span>Heute fertig</span>
        {#if kennzahlen?.wartezeit_mittel_s != null}<small>mittlere Wartezeit {dauer(kennzahlen.wartezeit_mittel_s)}</small>{/if}</div>
      <div class="kennzahl fehler"><b>{kennzahlen?.fehler ?? '-'}</b><span>Fehler heute</span>{#if kennzahlen?.abgebrochen}<small>{kennzahlen.abgebrochen} abgebrochen</small>{/if}</div>
      <div class="kennzahl"><b>{erreichbar.length}<span style="font-size: var(--gross); color: var(--text-3)"> / {bild.knoten.length}</span></b><span>Knoten</span>
        {#if namen('nicht_erreichbar').length}<small>{namen('nicht_erreichbar').join(', ')} nicht erreichbar</small>{/if}
        {#if namen('schlaeft').length}<small>{namen('schlaeft').join(', ')} {namen('schlaeft').length === 1 ? 'schläft' : 'schlafen'}</small>{/if}</div>
    </div>
  </div>

  <div class="spalten">
    <div class="rollfeld">
      {#if umgehungen}
        <div class="hinweis warnung vorbei-hinweis"><i class="fa-solid fa-user-secret"></i>
          <span><b>{umgehungen} {umgehungen === 1 ? 'Zugriff' : 'Zugriffe'} am Leitstand vorbei</b> auf {vorbei.map((k) => k.name).join(', ')}:
            Programme greifen auf Modelle zu, ohne über die Leitstelle zu gehen.</span>
          <span class="rechts"><a class="knopf klein" href={weg.pfad('knoten')} onclick={(e) => weg.klick(e, 'knoten')}
                                  title="Unter Knoten steht je Rechner, wer, mit welchem Prozess und aus welchem Ordner">Ansehen</a></span></div>
      {/if}
      {#if bild.knoten.length === 0}
        <div class="leer"><i class="fa-solid fa-plug-circle-plus"></i><h2>Noch kein Anschluss</h2>
          <p>Richte den ersten Modell-Läufer ein: Adresse eingeben, die Leitstelle erkennt Modelle und Fähigkeiten selbst.</p>
          <a class="knopf haupt" href={weg.pfad('anschluss')} onclick={(e) => weg.klick(e, 'anschluss')}><i class="fa-solid fa-plus"></i> Anschluss hinzufügen</a></div>
      {:else}
        <Netzbild {bild} {kuerzlich} />
      {/if}
      <div class="abschnitt">
        <div class="abschnitt-kopf"><h2>Läuft gerade</h2><span class="zahl leise">{laufend.length}</span>
          <a class="mehr" href={weg.pfad('auftraege')} onclick={(e) => weg.klick(e, 'auftraege')}>Alle Aufträge</a></div>
        {#if laufend.length === 0}
          <p class="leise">Gerade rechnet nichts. Aufträge erscheinen hier, sobald eine Anwendung über die Leitstelle anfragt.</p>
        {/if}
        <div class="laufend">
          {#each laufend as a (a.kennung)}
            {@const f = FAEHIGKEIT[a.faehigkeit]}
            <div class="lauf" style="--f:{f.farbe}" title="{a.titel}: läuft seit {dauer(jetzt - (a.start_s ?? jetzt))}">
              <div class="symbol"><i class="fa-solid {f.symbol}"></i></div>
              <div style="min-width:0">
                <a class="titel" href={weg.pfad('auftraege', a.kennung)} onclick={(e) => weg.klick(e, 'auftraege', a.kennung)}>{a.titel}</a>
                <div class="zweit"><span class="app">{anwendung(a.anwendung)}</span><span>{a.modell} auf {knotenName(a.knoten)}</span>
                  {#if a.umgeleitet}<span title="Von der Selbststeuerung umgeleitet"><i class="fa-solid fa-route"></i> umgeleitet</span>{/if}</div>
                <div class="balken lebt unbestimmt"><b></b></div>
              </div>
              <div class="rest">Seit<b>{dauer(jetzt - (a.start_s ?? jetzt))}</b></div>
              <div class="rest">Priorität<b style="font-family: var(--schrift); font-weight: 600">{PRIORITAET[a.prioritaet].wort}</b></div>
              <div class="knoepfe">
                <button class="knopf ohne symbol klein gefahr" onclick={() => (stoppen = a)} title="Stoppen: auslaufen lassen oder sofort abbrechen"><i class="fa-solid fa-stop"></i></button>
              </div>
            </div>
          {/each}
        </div>
      </div>
      <div class="abschnitt">
        <div class="abschnitt-kopf"><h2>Zuletzt fertig</h2>
          <a class="mehr" href={weg.pfad('auftraege')} onclick={(e) => weg.klick(e, 'auftraege')}>Verlauf</a></div>
        {#each zuletzt as e (e.kennung)}
          {@const f = FAEHIGKEIT[e.faehigkeit]}
          <a class="lauf zuletzt" style="--f:{f.farbe}" href={weg.pfad('auftraege', e.kennung)} onclick={(ev) => weg.klick(ev, 'auftraege', e.kennung)}>
            <div class="symbol"><i class="fa-solid {f.symbol}"></i></div>
            <div style="min-width:0"><div class="titel">{e.titel || f.wort}</div>
              <div class="zweit"><span class="app">{anwendung(e.anwendung)}</span>{#if e.modell_name}<span>{e.modell_name}</span>{/if}
                <Zustand art="auftrag" wert={e.zustand} /></div></div>
            <div class="rest">Ende<b>{uhrzeit(e.ende_s, true)}</b></div>
            <div class="rest">Dauer<b>{e.start_s && e.ende_s ? dauer(e.ende_s - e.start_s) : '-'}</b></div>
          </a>
        {:else}
          <p class="leise">Noch nichts fertig.</p>
        {/each}
      </div>
    </div>

    <div class="rollfeld">
      <div class="karte speicherkarte">
        <h3><i class="fa-solid fa-memory"></i>Speicherlage <span class="rechts">Modelle im Speicher</span></h3>
        {#each bild.knoten as k (k.kennung)}
          <div class="zeile-sp"><span class="n">{k.name} <span class="leise klein">{gb(k.speicher_gb)}</span></span>
            <span class="w" class:warn={k.belegt_anteil >= 0.92}>{k.erreichbar ? `${prozent(k.belegt_anteil)} belegt · ${gb(Math.max(0, k.frei_gb))} frei` : KNOTENZUSTAND[knotenzustand(k)].satz}</span></div>
          <div class="speicher-zeile"><Speicherbalken knoten={k} modelle={bild.modelle} /></div>
        {:else}
          <p class="leise klein">Noch kein Rechner eingerichtet.</p>
        {/each}
        <div class="speicher-legende">
          <span><i class="fa-solid fa-square" style="color: var(--himmel)"></i>Text</span>
          <span><i class="fa-solid fa-square" style="color: var(--flieder)"></i>Bild</span>
          <span><i class="fa-solid fa-square" style="color: var(--petrol)"></i>Einbettung</span>
          <span><i class="fa-solid fa-square" style="color: var(--stahl)"></i>System</span>
        </div>
      </div>

      {#if wartend.length}
        <div class="karte wartet-k">
          <h3><i class="fa-solid fa-hourglass-half"></i>Wartet <span class="rechts">{wartend.length} Aufträge</span></h3>
          {#each wartend as a (a.kennung)}
            <div class="eintrag">
              <div class="t"><a href={weg.pfad('auftraege', a.kennung)} onclick={(e) => weg.klick(e, 'auftraege', a.kennung)}>{a.titel}</a><Faehigkeit wert={a.faehigkeit} /></div>
              <div class="g zwei-zeilen" title={a.begruendung}>{anwendung(a.anwendung)} · {a.voraussichtlich_s != null ? `etwa ${dauer(a.voraussichtlich_s)}: ` : ''}{a.begruendung}</div>
              <div class="tun"><button class="knopf klein ohne gefahr" onclick={() => (stoppen = a)} title="Auftrag verwerfen: die Anwendung bekommt eine Abbruchnachricht"><i class="fa-solid fa-xmark"></i> Verwerfen</button></div>
            </div>
          {/each}
        </div>
      {/if}

      <div class="karte meldungen">
        <h3><i class="fa-solid fa-wand-magic-sparkles"></i>Selbststeuerung <span class="rechts">{bild.automatik === 'selbst' ? 'handelt selbst' : bild.automatik === 'vorschlagen' ? 'schlägt vor' : 'aus'}</span></h3>
        {#each ausgefuehrt as m (m.kennung)}
          <div class="m" class:warnung={m.zustand === 'gesperrt'} class:signal={m.zustand === 'ausgefuehrt'}>
            <span class="zeit zahl">{uhrzeit(m.zeit_s)}</span><i class="fa-solid {MASSNAHME[m.art].symbol}"></i>
            <span title={m.schritte.join(' > ')}>{m.zustand === 'gesperrt' ? 'Gesperrt: ' : m.zustand === 'geplant' ? 'Vorschlag: ' : ''}{m.grund || MASSNAHME[m.art].wort}</span></div>
        {:else}
          <p class="leise klein">Noch keine Maßnahme. Die Leitstelle schichtet um, sobald ein Auftrag wartet und es sich nach Messung lohnt.</p>
        {/each}
      </div>

      <div class="karte meldungen">
        <h3><i class="fa-solid fa-bell"></i>Meldungen <span class="rechts"><a href={weg.pfad('protokoll')} onclick={(e) => weg.klick(e, 'protokoll')}>Protokoll</a></span></h3>
        {#each bild.meldungen.slice(0, 8) as m, i (i)}
          <div class="m {meldungsart(m.text)}"><span class="zeit zahl">{uhrzeit(m.zeit_s)}</span><i class="fa-solid fa-circle-dot"></i><span>{m.text}</span></div>
        {:else}
          <p class="leise klein">Noch keine Meldungen.</p>
        {/each}
      </div>
    </div>
  </div>
</div>

{#if stoppen}<StoppDialog auftrag={stoppen} schliessen={() => (stoppen = null)} />{/if}

<style>
  .lagezeile b.ruhig { color: var(--gut); }
  .speicher-zeile { margin-top: 6px; }
  .vorbei-hinweis { margin-bottom: var(--a4); }
  :global(.seite-uebersicht .lauf .titel) { display: block; color: var(--text); }
  :global(.seite-uebersicht .lauf.zuletzt) { grid-template-columns: 34px minmax(0, 1fr) 110px 90px; color: inherit; margin-top: 2px; }
  :global(.seite-uebersicht .wartet-k .eintrag .t a) { color: var(--text); }
</style>
