<script lang="ts">
  import { api } from '../lib/api';
  import { gb, prozent } from '../lib/format';
  import { tun } from '../lib/meldung.svelte';
  import type { KnotenDaten, KnotenSicht, Lagebild, Zone } from '../lib/typen.gen';
  import { weg } from '../lib/weg.svelte';
  import { DIENSTZUSTAND } from '../lib/wort';
  import Speicherbalken from '../teile/Speicherbalken.svelte';
  import ZoneMarke from '../teile/ZoneMarke.svelte';

  let { bild }: { bild: Lagebild } = $props();

  let bearbeiten = $state<string | null>(null);
  let entwurf = $state<KnotenDaten | null>(null);
  let loeschen = $state<string | null>(null);

  const erreichbar = $derived(bild.knoten.filter((k) => k.erreichbar));
  const dienste = (k: string) => bild.dienste.filter((d) => d.knoten === k);
  const rechnend = (k: string) => bild.auftraege.filter((a) => a.knoten === k && a.zustand === 'laeuft').length;
  const wartenAufSpeicher = (k: string) => bild.auftraege.filter((a) => a.zustand === 'wartet_speicher' && (a.knoten === k)).length;

  function beginnen(k: KnotenSicht) {
    bearbeiten = k.kennung;
    entwurf = { name: k.name, adresse: k.adresse, speicher_gb: k.speicher_gb, system_gb: k.system_gb, zone: k.zone as Zone,
                budget_fest_gb: k.budget_fest_gb, hintergrund_von: k.hintergrund_von, hintergrund_bis: k.hintergrund_bis };
  }

  async function speichern() {
    if (!bearbeiten || !entwurf) return;
    const d = { ...entwurf, budget_fest_gb: entwurf.budget_fest_gb || null,
                hintergrund_von: entwurf.hintergrund_von ?? null, hintergrund_bis: entwurf.hintergrund_bis ?? null };
    if (await tun(() => api.knotenAendern(bearbeiten!, d), 'Rechner gespeichert')) { bearbeiten = null; entwurf = null; }
  }

  async function entfernen(k: string) {
    if (await tun(() => api.knotenLoeschen(k), 'Rechner entfernt')) loeschen = null;
  }
</script>

<div class="seiteninhalt seite-knoten">
  <div class="rahmen-kopf">
    <div class="seitenkopf">
      <h1>Knoten</h1><span class="zahl">{bild.knoten.length}</span>
      <div class="aktionen">
        <a class="knopf haupt" href={weg.pfad('anschluss')} onclick={(e) => weg.klick(e, 'anschluss')}
           title="Einen Dienst anschließen; ein neuer Rechner wird dabei mit eingerichtet"><i class="fa-solid fa-plus"></i> Anschluss hinzufügen</a>
      </div>
    </div>
    <div class="kennzahlen">
      <div class="kennzahl"><b>{bild.knoten.length}</b><span>Knoten</span></div>
      <div class="kennzahl erfolg"><b>{erreichbar.length}</b><span>Erreichbar</span><small>mindestens ein Dienst antwortet</small></div>
      {#if erreichbar.length < bild.knoten.length}<div class="kennzahl fehler"><b>{bild.knoten.length - erreichbar.length}</b><span>Nicht erreichbar</span></div>{/if}
      <div class="kennzahl"><b>{gb(bild.knoten.reduce((s, k) => s + k.geladen_gb, 0))}</b><span>Modelle im Speicher</span></div>
    </div>
  </div>

  <div class="rollfeld">
    {#if !bild.knoten.length}
      <div class="leer"><i class="fa-solid fa-server"></i><h2>Noch kein Rechner</h2><p>Ein Rechner entsteht beim Anschließen seines ersten Dienstes: Adresse eingeben, Speicher angeben, fertig.</p></div>
    {/if}
    <div class="knoten-raster">
      {#each bild.knoten as k (k.kennung)}
        <article class="knotenkarte" class:aus={!k.erreichbar}>
          <header class="kk-kopf"><h2>{k.name}</h2><ZoneMarke wert={k.zone} />
            <span class="zustand {k.erreichbar ? 'fertig' : 'fehler'}"><i class="fa-solid {k.erreichbar ? 'fa-circle' : 'fa-circle-xmark'}"></i>{k.erreichbar ? 'Erreichbar' : 'Nicht erreichbar'}</span></header>
          <div class="kk-meta"><span class="zahl" title="Adresse im Netz">{k.adresse}</span><span>{gb(k.speicher_gb)} Speicher</span>
            <span title="So viel dürfen Modelle zusammen belegen">Budget {gb(k.budget_gb)}{k.budget_fest_gb ? ' (fest)' : ''}</span>
            {#if k.hintergrund_von != null && k.hintergrund_bis != null}<span title="In diesem Fenster ist der Rechner für Hintergrundarbeit bevorzugt"><i class="fa-solid fa-moon"></i> {k.hintergrund_von} bis {k.hintergrund_bis} Uhr</span>{/if}</div>

          {#if bearbeiten === k.kennung && entwurf}
            <div class="feldreihe">
              <label class="feld-l"><span>Name</span><input class="eingabe" bind:value={entwurf.name} /></label>
              <label class="feld-l"><span>Adresse <small>Rechnername oder IP, für die Zuordnung der Dienste</small></span><input class="eingabe" bind:value={entwurf.adresse} /></label>
              <label class="feld-l"><span>Speicher in GB <small>bis der Knoten-Agent misst</small></span><input class="eingabe" type="number" min="1" bind:value={entwurf.speicher_gb} /></label>
              <label class="feld-l"><span>System in GB <small>was System und andere Programme belegen</small></span><input class="eingabe" type="number" min="0" bind:value={entwurf.system_gb} /></label>
              <label class="feld-l"><span>Festes Budget in GB <small>leer: Speicher minus Reserve</small></span><input class="eingabe" type="number" min="0" bind:value={entwurf.budget_fest_gb} /></label>
              <label class="feld-l"><span>Zone</span>
                <select class="eingabe" bind:value={entwurf.zone}><option value="heim">Heimnetz</option><option value="fern">Über VPN</option></select></label>
              <label class="feld-l"><span>Hintergrund ab Stunde <small>leer: kein Zeitfenster</small></span><input class="eingabe" type="number" min="0" max="23" bind:value={entwurf.hintergrund_von} /></label>
              <label class="feld-l"><span>Hintergrund bis Stunde</span><input class="eingabe" type="number" min="0" max="23" bind:value={entwurf.hintergrund_bis} /></label>
            </div>
            <div class="kk-knoepfe">
              <button class="knopf haupt" onclick={speichern}><i class="fa-solid fa-floppy-disk"></i> Speichern</button>
              <button class="knopf ohne" onclick={() => { bearbeiten = null; entwurf = null; }}>Abbrechen</button>
            </div>
          {:else}
            <div class="kk-koerper">
              <div class="kk-links">
                <Speicherbalken knoten={k} modelle={bild.modelle} budgetmarke />
                <div class="kk-werte">
                  <span title="Modelle im Speicher"><i class="fa-solid fa-brain"></i><b>{gb(k.geladen_gb)}</b> Modelle</span>
                  <span title="Frei im Budget"><i class="fa-solid fa-memory"></i><b>{gb(Math.max(0, k.frei_gb))}</b> frei</span>
                  <span title="Belegt einschließlich System"><i class="fa-solid fa-chart-pie"></i><b>{prozent(k.belegt_anteil)}</b></span>
                  <span title="Aufträge, die gerade auf diesem Rechner rechnen"><i class="fa-solid fa-list-check"></i><b>{rechnend(k.kennung)}</b> {rechnend(k.kennung) === 1 ? 'Auftrag' : 'Aufträge'}</span>
                </div>
                {#if wartenAufSpeicher(k.kennung)}
                  <div class="hinweis warnung klein"><i class="fa-solid fa-memory"></i><span>Wartet auf Speicher: <b class="zahl">{wartenAufSpeicher(k.kennung)}</b></span></div>
                {/if}
              </div>
              <div class="kk-rechts">
                <div class="kk-dienste"><div class="etikett">Dienste</div>
                  {#if dienste(k.kennung).length}
                    <ul>{#each dienste(k.kennung) as d (d.kennung)}
                      <li title="{d.name}: {DIENSTZUSTAND[d.zustand].wort}"><span class="punkt" class:aus={d.zustand !== 'bereit'}></span><span class="name">{d.name}</span><span class="wort">{DIENSTZUSTAND[d.zustand].wort}</span></li>
                    {/each}</ul>
                  {:else}<div class="kk-leer">Keine Dienste eingerichtet</div>{/if}
                </div>
              </div>
            </div>
            {#if loeschen === k.kennung}
              <div class="bestaetigen"><i class="fa-solid fa-triangle-exclamation"></i><span>{k.name} entfernen? Geht nur, wenn keine Dienste mehr darauf eingerichtet sind.</span>
                <div class="rechts"><button class="knopf klein ohne" onclick={() => (loeschen = null)}>Abbrechen</button>
                  <button class="knopf klein gefahr-voll" onclick={() => entfernen(k.kennung)}>Ja, entfernen</button></div></div>
            {/if}
            <footer class="kk-knoepfe">
              <button class="knopf" onclick={() => beginnen(k)} title="Name, Adresse, Speicher, Budget und Zeitfenster ändern"><i class="fa-solid fa-pen"></i> Bearbeiten</button>
              <a class="knopf ohne" href={weg.pfad('modelle', 'freigeben')} onclick={(e) => weg.klick(e, 'modelle', 'freigeben')}
                 title="Speicher freigeben: zeigt zuerst, was entladen würde; nichts passiert ohne Bestätigung"><i class="fa-solid fa-broom"></i> Speicher freigeben</a>
              <button class="knopf ohne gefahr" onclick={() => (loeschen = k.kennung)} title="Rechner aus der Leitstelle entfernen"><i class="fa-solid fa-trash"></i></button>
            </footer>
          {/if}
        </article>
      {/each}
    </div>
  </div>
</div>
