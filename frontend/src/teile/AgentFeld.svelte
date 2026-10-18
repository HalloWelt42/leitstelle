<script lang="ts">
  // Maschinenraum eines Rechners (der Knoten-Agent): ob er sich meldet, Schlüssel erzeugen oder aufdecken.
  // Eingetragen wird der Schlüssel in der Oberfläche des Maschinenraums auf dem Rechner selbst.
  // Er steht nur so lange auf dem Bildschirm, bis das Feld geschlossen wird.
  import { api } from '../lib/api';
  import { arbeit } from '../lib/arbeit.svelte';
  import { vor } from '../lib/format';
  import { tun } from '../lib/meldung.svelte';
  import type { KnotenSicht } from '../lib/typen.gen';

  let { knoten, jetzt }: { knoten: KnotenSicht; jetzt: number } = $props();

  let schluessel = $state<string | null>(null);
  let erneuern = $state(false);
  // Solange der Schlüssel zum Abschreiben dasteht, keine neue Fassung laden
  arbeit.bearbeitung(() => schluessel !== null);
  const a = $derived(knoten.agent);
  const adresse = location.origin;

  async function erzeugen() {
    const r = await tun(() => api.agentSchluesselNeu(knoten.kennung), a.schluessel ? 'Neuer Schlüssel für den Maschinenraum erzeugt' : 'Schlüssel für den Maschinenraum erzeugt');
    if (r) { schluessel = r.schluessel; erneuern = false; }
  }

  async function aufdecken() {
    if (schluessel) { schluessel = null; return; }
    const r = await tun(() => api.agentSchluessel(knoten.kennung));
    if (r) schluessel = r.schluessel;
  }

  const markieren = (e: FocusEvent) => (e.currentTarget as HTMLInputElement).select();
</script>

<div class="agentfeld">
  <div class="etikett">Maschinenraum</div>
  {#if a.verbunden}
    <div class="zeile" title="Der Maschinenraum misst Speicher und Last und verwaltet die Dienste dieses Rechners">
      <span class="punkt lebt"></span><span>Meldet sich, Fassung <span class="zahl">{a.version}</span>, {a.betriebssystem}</span>
      <span class="leise">Messung {vor(a.messzeit_s, jetzt)}</span></div>
  {:else if knoten.zustand === 'schlaeft'}
    <div class="zeile leise" title="Der Maschinenraum hat sich beim Einschlafen abgemeldet und meldet sich beim Aufwachen von selbst wieder.">
      <span class="punkt aus"></span><span>Schläft; meldet sich beim Aufwachen wieder</span></div>
  {:else if a.schluessel}
    <div class="zeile warnung" title="Ein Schlüssel ist vergeben, aber kein Maschinenraum verbunden. Bis er sich meldet, gelten die eingetragenen Speicherwerte.">
      <span class="punkt aus"></span><span>Nicht verbunden; es gelten die eingetragenen Speicherwerte</span></div>
  {:else}
    <div class="zeile leise">Kein Maschinenraum verbunden; der Speicher ist geschätzt, Dienste lassen sich hier nicht starten.</div>
  {/if}

  <div class="knoepfe">
    {#if !a.schluessel}
      <button class="knopf klein" onclick={erzeugen} title="Erzeugt den Schlüssel, mit dem sich der Maschinenraum dieses Rechners anmeldet"><i class="fa-solid fa-key"></i> Maschinenraum verbinden</button>
    {:else}
      <button class="knopf klein ohne" onclick={aufdecken} title={schluessel ? 'Schlüssel ausblenden' : 'Adresse und Schlüssel zum Eintragen zeigen; steht im Prüfprotokoll'}>
        <i class="fa-solid {schluessel ? 'fa-eye-slash' : 'fa-eye'}"></i> {schluessel ? 'Ausblenden' : 'Schlüssel zeigen'}</button>
      <button class="knopf klein ohne" onclick={() => (erneuern = true)} title="Neuen Schlüssel erzeugen; ein verbundener Maschinenraum wird getrennt"><i class="fa-solid fa-rotate"></i> Neuer Schlüssel</button>
    {/if}
  </div>

  {#if erneuern}
    <div class="bestaetigen"><i class="fa-solid fa-triangle-exclamation"></i><span>Neuen Schlüssel erzeugen? Der Maschinenraum wird getrennt, bis er den neuen Schlüssel bekommt.</span>
      <div class="rechts"><button class="knopf klein ohne" onclick={() => (erneuern = false)}>Abbrechen</button>
        <button class="knopf klein gefahr-voll" onclick={erzeugen}>Ja, neu erzeugen</button></div></div>
  {/if}

  {#if schluessel}
    <div class="einrichten">
      <label class="feld-l"><span>Adresse der Leitstelle</span>
        <input class="eingabe zahl" readonly value={adresse} onfocus={markieren} /></label>
      <label class="feld-l"><span>Schlüssel <small>nur für diesen Rechner</small></span>
        <input class="eingabe zahl" readonly value={schluessel} onfocus={markieren} /></label>
      <p class="leise">Beides auf dem Rechner in der Oberfläche des Maschinenraums unter Leitstelle eintragen. Ist er noch
        nicht installiert: Projekt maschinenraum von HalloWelt42 holen und dort <span class="zahl">./installieren.sh</span> ausführen.</p>
    </div>
  {/if}
</div>

<style>
  .agentfeld { display: flex; flex-direction: column; gap: var(--ls-a2); }
  .zeile { display: flex; align-items: center; gap: var(--ls-a2); flex-wrap: wrap; font-size: var(--ls-gr-klein); }
  .zeile .punkt { margin: 0; }
  .zeile.warnung { color: var(--ls-warnung); }
  .knoepfe { display: flex; gap: var(--ls-a2); flex-wrap: wrap; }
  .einrichten { display: grid; gap: var(--ls-a2); }
  .einrichten p { margin: 0; font-size: var(--ls-gr-klein); }
</style>
