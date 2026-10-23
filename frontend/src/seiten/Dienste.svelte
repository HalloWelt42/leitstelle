<script lang="ts">
  import { api } from '../lib/api';
  import { arbeit } from '../lib/arbeit.svelte';
  import { dauer } from '../lib/format';
  import { kanal } from '../lib/kanal.svelte';
  import { tun } from '../lib/meldung.svelte';
  import type { DienstSicht, Lagebild } from '../lib/typen.gen';
  import { weg } from '../lib/weg.svelte';
  import ZoneMarke from '../teile/ZoneMarke.svelte';
  import Zustand from '../teile/Zustand.svelte';

  let { bild }: { bild: Lagebild } = $props();

  let bearbeiten = $state<string | null>(null);
  type Entwurf = { name: string; adresse: string; plaetze: number; zugang: string; zugangNeu: boolean; grenze: number | null; abgleich: number | null;
                  instanzen: number; spielraum: number };
  let entwurf = $state<Entwurf>({ name: '', adresse: '', plaetze: 4, zugang: '', zugangNeu: false, grenze: null, abgleich: null, instanzen: 1, spielraum: 4 });
  let loeschen = $state<string | null>(null);
  let aufgedeckt = $state<Record<string, string | null>>({});
  let jetzt = $state(kanal.jetzt());
  arbeit.bearbeitung(() => bearbeiten !== null);

  $effect(() => {
    const t = setInterval(() => (jetzt = kanal.jetzt()), 1000);
    return () => clearInterval(t);
  });

  const bereit = $derived(bild.dienste.filter((d) => d.zustand === 'bereit'));
  const schlafend = $derived(bild.dienste.filter((d) => d.zustand === 'schlaeft'));
  const knotenName = (k: string | null) => bild.knoten.find((x) => x.kennung === k)?.name ?? 'Extern';
  const knotenZone = (d: DienstSicht) => (d.extern ? 'extern' : bild.knoten.find((x) => x.kennung === d.knoten)?.zone ?? 'heim');
  const modelle = (d: string) => bild.modelle.filter((m) => m.dienst === d);

  function beginnen(d: DienstSicht) {
    bearbeiten = d.kennung;
    entwurf = { name: d.name, adresse: d.adresse, plaetze: d.plaetze, zugang: '', zugangNeu: false, grenze: d.anfragen_je_minute, abgleich: null,
                instanzen: d.einbettung_instanzen, spielraum: d.einbettung_spielraum_gb };
  }

  async function speichern() {
    if (!bearbeiten) return;
    const e = entwurf;
    // leere Grenze entfernt sie (0), leerer Abgleich lässt ihn
    const daten = { name: e.name, adresse: e.adresse, plaetze: e.plaetze, zugang: e.zugangNeu ? e.zugang : null,
                    anfragen_je_minute: e.grenze ?? 0, abgleich_s: e.abgleich || null,
                    einbettung_instanzen: e.instanzen || 1, einbettung_spielraum_gb: e.spielraum ?? 4 };
    if (await tun(() => api.dienstAendern(bearbeiten!, daten), 'Dienst gespeichert')) bearbeiten = null;
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

  <div class="rollfeld">
    {#if bild.dienste.length}
      <table class="tabelle">
        <thead><tr><th>Dienst</th><th>Rechner</th><th>Zustand</th><th>Speicher</th><th>Modelle</th><th>Plätze</th><th>Zugang</th><th></th></tr></thead>
        <tbody>
          {#each bild.dienste as d (d.kennung)}
            {@const ms = modelle(d.kennung)}
            <tr>
              <td><b>{d.name}</b><div class="leise klein zahl">{d.adresse}</div></td>
              <td>{knotenName(d.knoten)} <ZoneMarke wert={knotenZone(d)} /></td>
              <td><Zustand art="dienst" wert={d.zustand} />{#if d.meldung}<div class="leise klein" title={d.meldung}>{d.meldung.length > 60 ? d.meldung.slice(0, 57) + '...' : d.meldung}</div>{/if}
                {#if d.fehlschlaege && d.naechste_pruefung_s}<div class="klein" title="Nach jedem Fehlschlag verdoppelt sich der Abstand, höchstens ein Tag; ab dem fünften Fehlschlag in Folge heißt es Ausfall">
                  <span class="zahl">{d.fehlschlaege}</span> {d.fehlschlaege === 1 ? 'Fehlschlag' : 'Fehlschläge'}, nächste Prüfung {d.naechste_pruefung_s > jetzt ? `in ${dauer(d.naechste_pruefung_s - jetzt)}` : 'gleich'}
                  <button class="knopf klein ohne" onclick={() => tun(() => api.dienstPruefen(d.kennung), 'Geprüft')} title="Sofort fragen, unabhängig von den Abständen"><i class="fa-solid fa-rotate"></i> Jetzt prüfen</button></div>{/if}</td>
              <td class="klein" title={d.steuerbar ? 'Die Leitstelle liest den echten Ladezustand und lädt und entlädt selbst' : 'Der Dienst meldet nur seine Modelle; Laden und Entladen übernimmt er selbst'}>{d.steuerbar ? 'Leitstelle steuert' : 'Dienst lädt selbst'}</td>
              <td class="zahl">{ms.length} <span class="leise">({ms.filter((m) => m.zustand !== 'frei').length} geladen)</span></td>
              <td class="zahl" title="Gleichzeitige Aufträge je geladenem Modell">{d.plaetze}
                {#if d.einbettung_instanzen > 1}<div class="klein" title="Bei Andrang lädt die Leitstelle weitere Instanzen je Einbettungsmodell (je Instanz ein Platz) und lässt den Spielraum im Budget frei; bei Ruhe baut sie zurück">
                  Einbettung bis {d.einbettung_instanzen} Instanzen, {d.einbettung_spielraum_gb} GB Spielraum</div>{/if}
                {#if d.anfragen_je_minute}<div class="klein" class:akzent={d.frei_in_s > 0} title="Grenze des Anbieters; jede Anfrage zählt, auch die Abfrage der Modelle">
                  {d.anfragen_letzte_minute} von {d.anfragen_je_minute} je Minute{#if d.frei_in_s > 0}, frei in {dauer(d.frei_in_s)}{/if}</div>{/if}</td>
              <td>{#if d.zugang}
                  <span class="zahl">{d.kennung in aufgedeckt ? (aufgedeckt[d.kennung] ?? '') : '••••••••'}</span>
                  <button class="knopf ohne symbol klein" onclick={() => zugangZeigen(d.kennung)} title="Zugang aufdecken; steht im Prüfprotokoll"><i class="fa-solid {d.kennung in aufgedeckt ? 'fa-eye-slash' : 'fa-eye'}"></i></button>
                {:else}<span class="leise klein">keiner nötig</span>{/if}</td>
              <td class="aktionen">
                <button class="knopf ohne symbol klein" onclick={() => beginnen(d)} title="Name, Adresse, Plätze oder Zugang ändern"><i class="fa-solid fa-pen"></i></button>
                <button class="knopf ohne symbol klein gefahr" onclick={() => (loeschen = d.kennung)} title="Dienst aus der Leitstelle entfernen"><i class="fa-solid fa-trash"></i></button>
              </td>
            </tr>
            {#if bearbeiten === d.kennung}
              <tr><td colspan="8">
                <div class="feldreihe">
                  <label class="feld-l"><span>Name</span><input class="eingabe" bind:value={entwurf.name} /></label>
                  <label class="feld-l"><span>Adresse</span><input class="eingabe" bind:value={entwurf.adresse} /></label>
                  <label class="feld-l"><span>Plätze <small>gleichzeitige Aufträge je Modell</small></span><input class="eingabe" type="number" min="1" max="64" bind:value={entwurf.plaetze} /></label>
                  <label class="feld-l"><span>Grenze <small>Anfragen je Minute, leer heißt keine</small></span><input class="eingabe" type="number" min="1" max="100000" bind:value={entwurf.grenze} /></label>
                  {#if !d.extern && d.art === 'openai_kompatibel'}
                    <label class="feld-l"><span>Einbettung: Instanzen <small>bei Andrang lädt die Leitstelle je Einbettungsmodell bis zu so viele; 1 heißt keine weiteren</small></span><input class="eingabe" type="number" min="1" max="32" bind:value={entwurf.instanzen} /></label>
                    <label class="feld-l"><span>Einbettung: Spielraum <small>GB, die im Budget des Rechners frei bleiben</small></span><input class="eingabe" type="number" min="0" max="512" step="0.5" bind:value={entwurf.spielraum} /></label>
                  {/if}
                  {#if d.extern}<label class="feld-l"><span>Abgleich <small>Sekunden zwischen zwei Abfragen der Modelle, leer lässt ihn</small></span><input class="eingabe" type="number" min="1" max="86400" bind:value={entwurf.abgleich} /></label>{/if}
                  <label class="feld-l"><span>Zugang <small>{entwurf.zugangNeu ? 'leer entfernt den Zugang' : 'bleibt, wie er ist'}</small></span>
                    <span class="feld-l zeile-feld"><input class="eingabe" type="password" bind:value={entwurf.zugang} disabled={!entwurf.zugangNeu} placeholder="neuer Schlüssel" />
                      <button class="knopf klein ohne" onclick={() => (entwurf.zugangNeu = !entwurf.zugangNeu)}>{entwurf.zugangNeu ? 'Doch nicht' : 'Ändern'}</button></span></label>
                </div>
                <div class="tun" style="margin-top: var(--ls-a3); display: flex; gap: var(--ls-a2)">
                  <button class="knopf haupt" onclick={speichern}><i class="fa-solid fa-floppy-disk"></i> Speichern</button>
                  <button class="knopf ohne" onclick={() => (bearbeiten = null)}>Abbrechen</button></div>
              </td></tr>
            {/if}
            {#if loeschen === d.kennung}
              <tr><td colspan="8"><div class="bestaetigen"><i class="fa-solid fa-triangle-exclamation"></i><span>{d.name} entfernen? Seine Modelle verschwinden aus dem Verbund; geht nur ohne offene Aufträge.</span>
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
