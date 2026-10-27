<script lang="ts">
  import { api } from '../lib/api';
  import { arbeit } from '../lib/arbeit.svelte';
  import { dauer, menge } from '../lib/format';
  import { kanal } from '../lib/kanal.svelte';
  import { meldungen, tun } from '../lib/meldung.svelte';
  import type { DienstAenderung, DienstSicht, Lagebild } from '../lib/typen.gen';
  import { weg } from '../lib/weg.svelte';
  import { FAEHIGKEIT, PROBENAUSGANG } from '../lib/wort';
  import AnbieterModelle from '../teile/AnbieterModelle.svelte';
  import ZoneMarke from '../teile/ZoneMarke.svelte';
  import Zustand from '../teile/Zustand.svelte';

  let { bild }: { bild: Lagebild } = $props();

  const SPALTEN = 6;
  let bearbeiten = $state<string | null>(null);
  type Entwurf = { name: string; adresse: string; plaetze: number; zugang: string; zugangNeu: boolean; grenze: number | null; tokenEin: number | null;
                  tokenAus: number | null; abgleich: number | null; instanzen: number; spielraum: number };
  let entwurf = $state<Entwurf>({ name: '', adresse: '', plaetze: 4, zugang: '', zugangNeu: false, grenze: null, tokenEin: null, tokenAus: null, abgleich: null,
                                  instanzen: 1, spielraum: 4 });
  let loeschen = $state<string | null>(null);
  let pruefen = $state<string | null>(null);
  let prueft = $state(false);
  let aufgedeckt = $state<Record<string, string | null>>({});
  let jetzt = $state(kanal.jetzt());
  arbeit.bearbeitung(() => bearbeiten !== null || prueft);

  $effect(() => {
    const t = setInterval(() => (jetzt = kanal.jetzt()), 1000);
    return () => clearInterval(t);
  });

  const bereit = $derived(bild.dienste.filter((d) => d.zustand === 'bereit'));
  const schlafend = $derived(bild.dienste.filter((d) => d.zustand === 'schlaeft'));
  const knotenName = (k: string | null) => bild.knoten.find((x) => x.kennung === k)?.name ?? 'Extern';
  const knotenZone = (d: DienstSicht) => (d.extern ? 'extern' : bild.knoten.find((x) => x.kennung === d.knoten)?.zone ?? 'heim');
  const modelle = (d: string) => bild.modelle.filter((m) => m.dienst === d);
  // je Familie eine Instanz (beim Anbieter gibt es keine weiteren)
  const grundmodelle = (d: string) => modelle(d).filter((m) => !m.zusatz);
  // Was sich je Art von Hand einstellen lässt, sagt der Kern (beim Maschinenraum nur der Name); der Rest bleibt verborgen
  const kann = (d: DienstSicht, feld: string) => d.aenderbar.includes(feld);

  function beginnen(d: DienstSicht) {
    bearbeiten = d.kennung;
    entwurf = { name: d.name, adresse: d.adresse, plaetze: d.plaetze, zugang: '', zugangNeu: false, grenze: d.anfragen_je_minute, tokenEin: d.token_ein_je_minute,
                tokenAus: d.token_aus_je_minute, abgleich: d.abgleich_s, instanzen: d.einbettung_instanzen, spielraum: d.einbettung_spielraum_gb };
  }

  async function speichern(d: DienstSicht) {
    const e = entwurf;
    // nur einstellbare Felder; eine leere Grenze entfernt sie (0), leerer Abgleich heißt Vorgabe (0)
    const alle: DienstAenderung = { name: e.name, adresse: e.adresse, plaetze: e.plaetze, zugang: e.zugangNeu ? e.zugang : null,
                                    anfragen_je_minute: e.grenze ?? 0, token_ein_je_minute: e.tokenEin ?? 0, token_aus_je_minute: e.tokenAus ?? 0,
                                    abgleich_s: e.abgleich ?? 0, einbettung_instanzen: e.instanzen || 1, einbettung_spielraum_gb: e.spielraum ?? 4 };
    const daten = Object.fromEntries(Object.entries(alle).filter(([feld]) => kann(d, feld))) as DienstAenderung;
    if (await tun(() => api.dienstAendern(d.kennung, daten), 'Dienst gespeichert')) bearbeiten = null;
  }

  async function faehigkeitenPruefen(d: DienstSicht) {
    prueft = true;
    const r = await tun(() => api.faehigkeitenPruefen(d.kennung));
    prueft = false;
    if (r) {
      pruefen = null;
      meldungen.zeigen(r.map((x) => `${x.name}: ${FAEHIGKEIT[x.faehigkeit].wort} ${PROBENAUSGANG[x.ausgang]}`).join('; '), r.some((x) => x.ausgang === 'unklar') ? 'hinweis' : 'erfolg');
    }
  }

  async function zugangZeigen(d: string) {
    if (d in aufgedeckt) {
      const { [d]: _, ...rest } = aufgedeckt;
      aufgedeckt = rest;
      return;
    }
    const r = await tun(() => api.dienstZugang(d));
    if (r) aufgedeckt = { ...aufgedeckt, [d]: r.zugang };
  }
</script>

<div class="seiteninhalt seite-dienste">
  <div class="rahmen-kopf">
    <div class="seitenkopf">
      <h1>Dienste</h1><span class="zahl">{bild.dienste.length}</span>
      <div class="aktionen">
        <a class="knopf haupt" href={weg.pfad('anschluss')} onclick={(e) => weg.klick(e, 'anschluss')}><i class="fa-solid fa-plus"></i> Anschluss hinzufügen</a>
      </div>
    </div>
    <div class="kennzahlen">
      <div class="kennzahl"><b>{bild.dienste.length}</b><span>Dienste</span></div>
      <div class="kennzahl erfolg"><b>{bereit.length}</b><span>Bereit</span></div>
      {#if schlafend.length}<div class="kennzahl"><b>{schlafend.length}</b><span>Schläft</span><small>ihr Rechner schläft; keine Prüfung, bis er wach ist</small></div>{/if}
      {#if bereit.length + schlafend.length < bild.dienste.length}<div class="kennzahl fehler"><b>{bild.dienste.length - bereit.length - schlafend.length}</b><span>Nicht erreichbar</span>{#if bild.dienste.some((d) => d.zustand === 'ausfall')}<small>davon {bild.dienste.filter((d) => d.zustand === 'ausfall').length} im Ausfall</small>{/if}</div>{/if}
      <div class="kennzahl"><b>{bild.dienste.filter((d) => d.steuerbar).length}</b><span>Steuerbar</span><small>Leitstelle lädt und entlädt</small></div>
    </div>
  </div>

  <div class="rollfeld tabellen-raum">
    {#if bild.dienste.length}
      <table class="tabelle karten">
        <thead><tr><th>Dienst</th><th>Zustand</th><th>Modelle</th><th>Plätze</th><th>Zugang</th><th></th></tr></thead>
        <tbody>
          {#each bild.dienste as d (d.kennung)}
            {@const ms = modelle(d.kennung)}
            <tr>
              <td><b>{d.name}</b><div class="leise klein zahl adresse">{d.adresse}</div>
                <div class="rechner klein" title="Rechner und Zone">{#if !d.extern}<span>{knotenName(d.knoten)}</span>{/if}<ZoneMarke wert={knotenZone(d)} /></div></td>
              <td data-titel="Zustand"><span title={d.zustand === 'bereit' ? d.meldung : undefined}><Zustand art="dienst" wert={d.zustand} /></span>
                {#if d.meldung && d.zustand !== 'bereit'}<div class="leise klein" title={d.meldung}>{d.meldung.length > 60 ? d.meldung.slice(0, 57) + '...' : d.meldung}</div>{/if}
                <div class="leise klein" title={d.extern ? 'Der Anbieter lädt seine Modelle selbst; sie rechnen bei ihm' : d.steuerbar ? 'Die Leitstelle liest den echten Ladezustand und lädt und entlädt selbst' : 'Der Dienst meldet nur seine Modelle; Laden und Entladen übernimmt er selbst'}>{d.extern ? 'rechnet beim Anbieter' : d.steuerbar ? 'Leitstelle steuert' : 'Dienst lädt selbst'}</div>
                {#if d.fehlschlaege && d.naechste_pruefung_s}<div class="klein" title="Nach jedem Fehlschlag verdoppelt sich der Abstand, höchstens ein Tag; ab dem fünften Fehlschlag in Folge heißt es Ausfall">
                  <span class="zahl">{d.fehlschlaege}</span> {d.fehlschlaege === 1 ? 'Fehlschlag' : 'Fehlschläge'}, nächste Prüfung {d.naechste_pruefung_s > jetzt ? `in ${dauer(d.naechste_pruefung_s - jetzt)}` : 'gleich'}
                  <button class="knopf klein ohne" onclick={() => tun(() => api.dienstPruefen(d.kennung), 'Geprüft')} title="Sofort fragen, unabhängig von den Abständen"><i class="fa-solid fa-rotate"></i> Jetzt prüfen</button></div>{/if}</td>
              <td data-titel="Modelle" class="zahl">{ms.length} <span class="leise">{d.extern ? 'beim Anbieter' : `(${ms.filter((m) => m.zustand !== 'frei').length} geladen)`}</span></td>
              <td data-titel="Plätze" class="zahl" title="Gleichzeitige Aufträge je Modell">{d.plaetze}
                {#if d.einbettung_instanzen > 1}<div class="klein" title="Bei Andrang lädt die Leitstelle weitere Instanzen je Einbettungsmodell (je Instanz ein Platz) und lässt den Spielraum im Budget frei; bei Ruhe baut sie zurück">
                  Einbettung bis {d.einbettung_instanzen} Instanzen, {d.einbettung_spielraum_gb} GB Spielraum</div>{/if}
                {#if !d.extern && d.anfragen_je_minute}<div class="klein" class:akzent={d.frei_in_s > 0} title="Grenze je Minute; jede Anfrage zählt, auch die Abfrage der Modelle">
                  {d.nutzung.anfragen} von {d.anfragen_je_minute} je Minute{#if d.frei_in_s > 0}, frei in {dauer(d.frei_in_s)}{/if}</div>{/if}</td>
              <td data-titel="Zugang">{#if d.zugang}
                  <span class="zahl">{d.kennung in aufgedeckt ? (aufgedeckt[d.kennung] ?? '') : '••••••••'}</span>
                  <button class="knopf ohne symbol klein" onclick={() => zugangZeigen(d.kennung)} title="Zugang aufdecken; steht im Prüfprotokoll"><i class="fa-solid {d.kennung in aufgedeckt ? 'fa-eye-slash' : 'fa-eye'}"></i></button>
                {:else}<span class="leise klein">keiner nötig</span>{/if}</td>
              <td class="aktionen">
                {#if d.extern}<button class="knopf ohne symbol klein" onclick={() => (pruefen = d.kennung)} disabled={d.zustand !== 'bereit'}
                                      title="Fähigkeiten prüfen: je Modell ein kleines Bild mit einer Frage; zählt gegen die Grenzen des Anbieters"><i class="fa-solid fa-flask"></i></button>{/if}
                <button class="knopf ohne symbol klein" onclick={() => beginnen(d)} title={kann(d, 'adresse') ? 'Name, Adresse, Plätze, Grenzen oder Zugang ändern' : 'Name ändern; den Rest meldet der Maschinenraum'}><i class="fa-solid fa-pen"></i></button>
                <button class="knopf ohne symbol klein gefahr" onclick={() => (loeschen = d.kennung)} title="Dienst aus der Leitstelle entfernen"><i class="fa-solid fa-trash"></i></button>
              </td>
            </tr>
            {#if d.extern && ms.length}
              <tr class="anbieter-zeile"><td colspan={SPALTEN}><AnbieterModelle dienst={d} modelle={grundmodelle(d.kennung)} {jetzt} /></td></tr>
            {/if}
            {#if pruefen === d.kennung}
              <tr><td colspan={SPALTEN}><div class="bestaetigen"><i class="fa-solid fa-flask"></i>
                <span>Fähigkeiten von {d.name} prüfen? Je Modell geht eine Anfrage mit einem kleinen Bild und einer Frage an den Anbieter
                  ({grundmodelle(d.kennung).length} Anfragen); sie zählen gegen die Grenzen. Das Ergebnis steht danach mit Zeitpunkt im Steckbrief.</span>
                <div class="rechts"><button class="knopf klein ohne" onclick={() => (pruefen = null)} disabled={prueft}>Abbrechen</button>
                  <button class="knopf klein haupt" onclick={() => faehigkeitenPruefen(d)} disabled={prueft}>
                    <i class="fa-solid {prueft ? 'fa-rotate fa-spin' : 'fa-flask'}"></i> {prueft ? 'Prüft' : 'Ja, prüfen'}</button></div></div></td></tr>
            {/if}
            {#if bearbeiten === d.kennung}
              <tr><td colspan={SPALTEN}>
                <div class="feldreihe">
                  <label class="feld-l"><span>Name</span><input class="eingabe" bind:value={entwurf.name} /></label>
                  {#if kann(d, 'adresse')}<label class="feld-l"><span>Adresse</span><input class="eingabe" bind:value={entwurf.adresse} /></label>
                  {:else}<div class="feld-l"><span>Adresse <small>vergibt die Leitstelle; der Maschinenraum meldet sich mit dem Schlüssel seines Rechners</small></span>
                    <span class="zahl adresse nur-lesen" title="Nicht von Hand änderbar">{d.adresse}</span></div>{/if}
                  {#if kann(d, 'plaetze')}<label class="feld-l"><span>Plätze <small>gleichzeitige Aufträge je Modell</small></span><input class="eingabe" type="number" min="1" max="64" bind:value={entwurf.plaetze} /></label>{/if}
                  {#if kann(d, 'anfragen_je_minute')}<label class="feld-l"><span>Grenze: Anfragen <small>je Minute, gleitend; leer heißt keine</small></span><input class="eingabe" type="number" min="1" max="100000" bind:value={entwurf.grenze} /></label>{/if}
                  {#if kann(d, 'token_ein_je_minute')}<label class="feld-l"><span>Grenze: Token hinein <small>je Minute, gleitend; leer heißt keine</small></span><input class="eingabe" type="number" min="1" bind:value={entwurf.tokenEin} placeholder={d.extern ? 'zum Beispiel 4000000' : ''} /></label>{/if}
                  {#if kann(d, 'token_aus_je_minute')}<label class="feld-l"><span>Grenze: Token heraus <small>je Minute, gleitend; leer heißt keine</small></span><input class="eingabe" type="number" min="1" bind:value={entwurf.tokenAus} placeholder={d.extern ? 'zum Beispiel 100000' : ''} /></label>{/if}
                  {#if kann(d, 'einbettung_instanzen')}
                    <label class="feld-l"><span>Einbettung: Instanzen <small>bei Andrang lädt die Leitstelle je Einbettungsmodell bis zu so viele; 1 heißt keine weiteren</small></span><input class="eingabe" type="number" min="1" max="32" bind:value={entwurf.instanzen} /></label>
                    <label class="feld-l"><span>Einbettung: Spielraum <small>GB, die im Budget des Rechners frei bleiben</small></span><input class="eingabe" type="number" min="0" max="512" step="0.5" bind:value={entwurf.spielraum} /></label>
                  {/if}
                  {#if kann(d, 'abgleich_s')}<label class="feld-l"><span>Abgleich <small>Sekunden zwischen zwei Abfragen der Modelle, wenn der Dienst gesund ist; leer heißt Vorgabe</small></span><input class="eingabe" type="number" min="1" max="86400" bind:value={entwurf.abgleich} placeholder={d.abgleich_vorgabe_s != null ? `Vorgabe ${d.abgleich_vorgabe_s}` : ''} /></label>{/if}
                  {#if kann(d, 'zugang')}<label class="feld-l"><span>Zugang <small>{entwurf.zugangNeu ? 'leer entfernt den Zugang' : 'bleibt, wie er ist'}</small></span>
                    <span class="feld-l zeile-feld"><input class="eingabe" type="password" bind:value={entwurf.zugang} disabled={!entwurf.zugangNeu} placeholder="neuer Schlüssel" />
                      <button class="knopf klein ohne" onclick={() => (entwurf.zugangNeu = !entwurf.zugangNeu)}>{entwurf.zugangNeu ? 'Doch nicht' : 'Ändern'}</button></span></label>{/if}
                </div>
                {#if d.aenderbar.length === 1}<p class="leise klein">Plätze, Zustand und Fähigkeiten meldet der Maschinenraum je Dienst aus seinen Dienstdateien; hier lässt sich nur der Name ändern.</p>{/if}
                {#if d.extern}<p class="leise klein">Grenzen des Anbieters gelten je Schlüssel für alle Modelle zusammen, gleitend über 60 Sekunden (zum Beispiel {menge(4_000_000)} Token hinein und {menge(100_000)} heraus); die Leitstelle hält sie ein.</p>{/if}
                <div class="tun" style="margin-top: var(--a3); display: flex; gap: var(--a2)">
                  <button class="knopf haupt" onclick={() => speichern(d)}><i class="fa-solid fa-floppy-disk"></i> Speichern</button>
                  <button class="knopf ohne" onclick={() => (bearbeiten = null)}>Abbrechen</button></div>
              </td></tr>
            {/if}
            {#if loeschen === d.kennung}
              <tr><td colspan={SPALTEN}><div class="bestaetigen"><i class="fa-solid fa-triangle-exclamation"></i><span>{d.name} entfernen? Seine Modelle verschwinden aus dem Verbund; geht nur ohne offene Aufträge.</span>
                <div class="rechts"><button class="knopf klein ohne" onclick={() => (loeschen = null)}>Abbrechen</button>
                  <button class="knopf klein gefahr-voll" onclick={async () => { if (await tun(() => api.dienstLoeschen(d.kennung), 'Dienst entfernt')) loeschen = null; }}>Ja, entfernen</button></div></div></td></tr>
            {/if}
          {/each}
        </tbody>
      </table>
    {:else}
      <div class="leer"><i class="fa-solid fa-plug"></i><h2>Noch kein Dienst</h2><p>Einen Modell-Läufer oder externen Anbieter anschließen: Adresse genügt, Modelle und Fähigkeiten erkennt die Leitstelle.</p>
        <a class="knopf haupt" href={weg.pfad('anschluss')} onclick={(e) => weg.klick(e, 'anschluss')}><i class="fa-solid fa-plus"></i> Anschluss hinzufügen</a></div>
    {/if}
  </div>
</div>

<style>
  :global(.seite-dienste .anbieter-zeile td) { padding-top: 0; }
  :global(.seite-dienste td.aktionen) { white-space: nowrap; }
  :global(.seite-dienste .adresse) { overflow-wrap: anywhere; }
  :global(.seite-dienste .nur-lesen) { padding: var(--a2) 0; color: var(--text-2); }
  :global(.seite-dienste .rechner) { display: flex; flex-wrap: wrap; align-items: center; gap: 4px var(--a2); margin-top: 4px; color: var(--text-2); }
</style>
