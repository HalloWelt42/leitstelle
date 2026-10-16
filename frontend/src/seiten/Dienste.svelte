<script lang="ts">
  import { api } from '../lib/api';
  import { tun } from '../lib/meldung.svelte';
  import type { DienstSicht, Lagebild } from '../lib/typen.gen';
  import { weg } from '../lib/weg.svelte';
  import ZoneMarke from '../teile/ZoneMarke.svelte';
  import Zustand from '../teile/Zustand.svelte';

  let { bild }: { bild: Lagebild } = $props();

  let bearbeiten = $state<string | null>(null);
  let entwurf = $state<{ name: string; adresse: string; plaetze: number; zugang: string; zugangNeu: boolean }>({ name: '', adresse: '', plaetze: 4, zugang: '', zugangNeu: false });
  let loeschen = $state<string | null>(null);
  let aufgedeckt = $state<Record<string, string | null>>({});

  const bereit = $derived(bild.dienste.filter((d) => d.zustand === 'bereit'));
  const knotenName = (k: string | null) => bild.knoten.find((x) => x.kennung === k)?.name ?? 'Extern';
  const knotenZone = (d: DienstSicht) => (d.extern ? 'extern' : bild.knoten.find((x) => x.kennung === d.knoten)?.zone ?? 'heim');
  const modelle = (d: string) => bild.modelle.filter((m) => m.dienst === d);

  function beginnen(d: DienstSicht) {
    bearbeiten = d.kennung;
    entwurf = { name: d.name, adresse: d.adresse, plaetze: d.plaetze, zugang: '', zugangNeu: false };
  }

  async function speichern() {
    if (!bearbeiten) return;
    const e = entwurf;
    const daten = { name: e.name, adresse: e.adresse, plaetze: e.plaetze, zugang: e.zugangNeu ? e.zugang : null };
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
      {#if bereit.length < bild.dienste.length}<div class="kennzahl fehler"><b>{bild.dienste.length - bereit.length}</b><span>Nicht erreichbar</span></div>{/if}
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
              <td><Zustand art="dienst" wert={d.zustand} />{#if d.meldung}<div class="leise klein" title={d.meldung}>{d.meldung.length > 60 ? d.meldung.slice(0, 57) + '...' : d.meldung}</div>{/if}</td>
              <td class="klein" title={d.steuerbar ? 'Die Leitstelle liest den echten Ladezustand und lädt und entlädt selbst' : 'Der Dienst meldet nur seine Modelle; Laden und Entladen übernimmt er selbst'}>{d.steuerbar ? 'Leitstelle steuert' : 'Dienst lädt selbst'}</td>
              <td class="zahl">{ms.length} <span class="leise">({ms.filter((m) => m.zustand !== 'frei').length} geladen)</span></td>
              <td class="zahl" title="Gleichzeitige Aufträge je geladenem Modell">{d.plaetze}</td>
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
