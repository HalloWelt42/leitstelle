<script lang="ts">
  import { api } from '../lib/api';
  import { arbeit } from '../lib/arbeit.svelte';
  import { gb, komma, prozent, uhrzeit } from '../lib/format';
  import { tun } from '../lib/meldung.svelte';
  import type { KnotenDaten, KnotenSicht, Lagebild, Zone } from '../lib/typen.gen';
  import { weg } from '../lib/weg.svelte';
  import { DIENSTZUSTAND, KNOTENZUSTAND, knotenzustand } from '../lib/wort';
  import AgentFeld from '../teile/AgentFeld.svelte';
  import AmLeitstandVorbei from '../teile/AmLeitstandVorbei.svelte';
  import DockerRechner from '../teile/DockerRechner.svelte';
  import Laeuferlast from '../teile/Laeuferlast.svelte';
  import RechnerApps from '../teile/RechnerApps.svelte';
  import Ring from '../teile/Ring.svelte';
  import Speicherbalken from '../teile/Speicherbalken.svelte';
  import ZoneMarke from '../teile/ZoneMarke.svelte';

  let { bild }: { bild: Lagebild } = $props();

  let bearbeiten = $state<string | null>(null);
  let entwurf = $state<KnotenDaten | null>(null);
  let loeschen = $state<string | null>(null);
  // Rechner ohne eigenen Modell-Läufer, etwa ein zweiter Mac nur mit Maschinenraum: anlegen, dann Schlüssel ausstellen
  let neu = $state<{ name: string; adresse: string; speicher_gb: number | null; zone: Zone } | null>(null);
  arbeit.bearbeitung(() => bearbeiten !== null || neu !== null);

  async function anlegen() {
    if (!neu || !neu.speicher_gb) return;
    const n = neu;
    if (await tun(() => api.knotenAnlegen({ name: n.name.trim(), adresse: n.adresse.trim(), speicher_gb: n.speicher_gb!, zone: n.zone, system_gb: 6 }),
                  'Rechner angelegt; jetzt auf seiner Karte den Schlüssel für den Maschinenraum ausstellen')) neu = null;
  }

  const erreichbar = $derived(bild.knoten.filter((k) => k.erreichbar));
  const schlafend = $derived(bild.knoten.filter((k) => knotenzustand(k) === 'schlaeft'));
  const unerreichbar = $derived(bild.knoten.filter((k) => knotenzustand(k) === 'nicht_erreichbar'));
  const mitAgent = $derived(bild.knoten.filter((k) => k.agent.verbunden));
  const umgehungen = $derived(bild.knoten.reduce((s, k) => s + k.fremde.umgehungen, 0));
  const ohneAuftrag = $derived(bild.knoten.reduce((s, k) => s + k.last.laeufer.filter((p) => p.ohne_auftrag_seit_s != null).length, 0));
  const gebremst = $derived(bild.knoten.filter((k) => k.last.stufe !== 'frei'));
  const anteil = (teil: number | null | undefined, ganz: number | null | undefined) => (teil != null && ganz ? (100 * teil) / ganz : null);
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

  async function nichtMehrWarten(k: KnotenSicht) {
    await tun(() => api.schlafBeenden(k.kennung), `${k.name} gilt nicht mehr als schlafend; seine Dienste werden geprüft`);
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
        <button class="knopf" onclick={() => (neu = { name: '', adresse: '', speicher_gb: null, zone: 'heim' })}
                title="Einen Rechner ohne eigenen Modell-Läufer anlegen, etwa einen weiteren Mac nur mit Maschinenraum"><i class="fa-solid fa-server"></i> Rechner hinzufügen</button>
        <a class="knopf haupt" href={weg.pfad('anschluss')} onclick={(e) => weg.klick(e, 'anschluss')}
           title="Einen Dienst anschließen; ein neuer Rechner wird dabei mit eingerichtet"><i class="fa-solid fa-plus"></i> Anschluss hinzufügen</a>
      </div>
    </div>
    <div class="kennzahlen">
      <div class="kennzahl"><b>{bild.knoten.length}</b><span>Knoten</span></div>
      <div class="kennzahl erfolg"><b>{erreichbar.length}</b><span>Erreichbar</span><small>mindestens ein Dienst antwortet</small></div>
      {#if schlafend.length}<div class="kennzahl"><b>{schlafend.length}</b><span>Schläft</span><small>Aufträge warten, bis er wach ist</small></div>{/if}
      {#if unerreichbar.length}<div class="kennzahl fehler"><b>{unerreichbar.length}</b><span>Nicht erreichbar</span></div>{/if}
      <div class="kennzahl"><b>{gb(bild.knoten.reduce((s, k) => s + k.geladen_gb, 0))}</b><span>Modelle im Speicher</span></div>
      <div class="kennzahl"><b>{mitAgent.length}</b><span>Mit Maschinenraum</span><small>Speicher gemessen statt geschätzt</small></div>
      {#if umgehungen}<div class="kennzahl fehler"><b>{umgehungen}</b><span>Am Leitstand vorbei</span><small>Zugriffe auf Modelle ohne die Leitstelle</small></div>{/if}
      {#if ohneAuftrag}<div class="kennzahl fehler"><b>{ohneAuftrag}</b><span>Ohne Auftrag</span><small>Arbeiter des Läufers rechnen ohne die Leitstelle</small></div>{/if}
      {#if gebremst.length}<div class="kennzahl"><b>{gebremst.length}</b><span>Hintergrund gebremst</span><small>{gebremst.map((k) => k.name).join(', ')}: Rechnerlast</small></div>{/if}
    </div>
  </div>

  <div class="rollfeld">
    {#if neu}
      <div class="karte" style="margin-bottom: var(--a4)">
        <h3><i class="fa-solid fa-server"></i>Rechner hinzufügen</h3>
        <div class="feldreihe">
          <label class="feld-l"><span>Name</span><input class="eingabe" bind:value={neu.name} placeholder="zum Beispiel Mac mini" /></label>
          <label class="feld-l"><span>Adresse <small>Rechnername oder IP im Netz</small></span><input class="eingabe" bind:value={neu.adresse} /></label>
          <label class="feld-l"><span>Speicher <small>GB laut Hersteller</small></span><input class="eingabe" type="number" min="1" max="4096" bind:value={neu.speicher_gb} /></label>
          <label class="feld-l"><span>Zone</span><select class="eingabe" bind:value={neu.zone}><option value="heim">Heimnetz</option><option value="fern">Über VPN</option></select></label>
        </div>
        <p class="leise klein">Danach auf der Karte des Rechners den Schlüssel für seinen Maschinenraum ausstellen; jeder Rechner braucht einen eigenen (einen kopierten Ordner mit Schlüssel erkennt die Leitstelle als denselben Rechner).</p>
        <div class="tun" style="margin-top: var(--a3); display: flex; gap: var(--a2)">
          <button class="knopf haupt" disabled={!neu.name.trim() || !neu.adresse.trim() || !neu.speicher_gb} onclick={anlegen}><i class="fa-solid fa-plus"></i> Anlegen</button>
          <button class="knopf ohne" onclick={() => (neu = null)}>Abbrechen</button></div>
      </div>
    {/if}
    {#if !bild.knoten.length}
      <div class="leer"><i class="fa-solid fa-server"></i><h2>Noch kein Rechner</h2><p>Ein Rechner entsteht beim Anschließen seines ersten Dienstes: Adresse eingeben, Speicher angeben, fertig.</p></div>
    {/if}
    <div class="knoten-raster">
      {#each bild.knoten as k (k.kennung)}
        {@const zustand = KNOTENZUSTAND[knotenzustand(k)]}
        <article class="knotenkarte" class:aus={knotenzustand(k) === 'nicht_erreichbar'}>
          <header class="kk-kopf"><h2>{k.name}</h2><ZoneMarke wert={k.zone} />
            <span class="zustand {zustand.klasse}"><i class="fa-solid {zustand.symbol}"></i>{zustand.wort}{#if k.schlaeft_seit_s != null}&nbsp;seit {uhrzeit(k.schlaeft_seit_s)}{/if}</span></header>
          <div class="kk-meta"><span class="zahl" title="Adresse im Netz">{k.adresse}</span><span>{gb(k.speicher_gb)} Speicher</span>
            <span title="So viel dürfen Modelle zusammen belegen">Budget {gb(k.budget_gb)}{k.budget_fest_gb ? ' (fest)' : ''}</span>
            {#if k.hintergrund_von != null && k.hintergrund_bis != null}<span title="In diesem Fenster ist der Rechner für Hintergrundarbeit bevorzugt"><i class="fa-solid fa-moon"></i> {k.hintergrund_von} bis {k.hintergrund_bis} Uhr</span>{/if}</div>

          {#if bearbeiten === k.kennung && entwurf}
            <div class="feldreihe">
              <label class="feld-l"><span>Name</span><input class="eingabe" bind:value={entwurf.name} /></label>
              <label class="feld-l"><span>Adresse <small>Rechnername oder IP, für die Zuordnung der Dienste</small></span><input class="eingabe" bind:value={entwurf.adresse} /></label>
              <label class="feld-l"><span>Speicher in GB <small>gilt, solange kein Maschinenraum misst</small></span><input class="eingabe" type="number" min="1" bind:value={entwurf.speicher_gb} /></label>
              <label class="feld-l"><span>System in GB <small>Schätzung für System und andere Programme, solange kein Maschinenraum misst</small></span><input class="eingabe" type="number" min="0" bind:value={entwurf.system_gb} /></label>
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
                {#if k.agent.messwerte}
                  {@const mw = k.agent.messwerte}
                  <div class="ringe">
                    {#if mw.cpu_prozent != null}<Ring wert={mw.cpu_prozent} name="Prozessor" />{/if}
                    {#if mw.grafik_prozent != null}<Ring wert={mw.grafik_prozent} name="Grafik" />{/if}
                    <Ring wert={anteil(mw.speicher_belegt_gb, mw.speicher_gesamt_gb) ?? 0} name="Speicher"
                          titel="Speicher: {gb(mw.speicher_belegt_gb)} von {gb(mw.speicher_gesamt_gb)} belegt (gemessen)" />
                    {#if mw.swap_gesamt_gb}<Ring wert={anteil(mw.swap_belegt_gb, mw.swap_gesamt_gb) ?? 0} name="Auslagerung"
                          titel="Auslagerung auf die Platte: {gb(mw.swap_belegt_gb)} von {gb(mw.swap_gesamt_gb)}. Hoch heißt: der Speicher reicht nicht, alles wird langsamer." />{/if}
                  </div>
                {/if}
                <Speicherbalken knoten={k} modelle={bild.modelle} budgetmarke />
                <div class="kk-werte">
                  <span title="Modelle im Speicher"><i class="fa-solid fa-brain"></i><b>{gb(k.geladen_gb)}</b> Modelle</span>
                  <span title="Frei im Budget"><i class="fa-solid fa-memory"></i><b>{gb(Math.max(0, k.frei_gb))}</b> frei</span>
                  <span title="Belegt einschließlich System"><i class="fa-solid fa-chart-pie"></i><b>{prozent(k.belegt_anteil)}</b></span>
                  <span title="Aufträge, die gerade auf diesem Rechner rechnen"><i class="fa-solid fa-list-check"></i><b>{rechnend(k.kennung)}</b> {rechnend(k.kennung) === 1 ? 'Auftrag' : 'Aufträge'}</span>
                  {#if k.agent.messwerte?.temperatur_c != null}<span title="Temperatur des Prozessors"><i class="fa-solid fa-temperature-half"></i><b>{komma(k.agent.messwerte.temperatur_c, 0)} °C</b></span>{/if}
                  {#if k.agent.messwerte?.leistung_w != null}<span title="Leistungsaufnahme des ganzen Rechners"><i class="fa-solid fa-bolt"></i><b>{komma(k.agent.messwerte.leistung_w, 1)}</b> Watt</span>{/if}
                  {#if k.agent.messwerte?.last_1m != null}<span title="Durchschnittliche Last der letzten Minute (wartende und laufende Prozesse)"><i class="fa-solid fa-gauge"></i><b>{komma(k.agent.messwerte.last_1m, 1)}</b> Last</span>{/if}
                  {#if k.agent.messwerte?.platte_frei_gb != null}<span title="Freier Platz auf der Platte"><i class="fa-solid fa-hard-drive"></i><b>{gb(k.agent.messwerte.platte_frei_gb)}</b> frei</span>{/if}
                </div>
                {#if knotenzustand(k) === 'schlaeft'}
                  <div class="hinweis klein"><i class="fa-solid fa-moon"></i><span>Schläft seit {uhrzeit(k.schlaeft_seit_s)}. Aufträge an ihn warten in den Apps, bis er wach ist; seine Dienste werden bis dahin nicht geprüft.</span></div>
                {/if}
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
                <AgentFeld knoten={k} jetzt={bild.zeit_s} />
              </div>
            </div>
            <Laeuferlast knoten={k} regelwerk={bild.regelwerk} jetzt={bild.zeit_s} />
            {#if k.last.gemeldet}
              <RechnerApps knoten={k} />
              <DockerRechner knoten={k} regelwerk={bild.regelwerk} />
            {/if}
            <AmLeitstandVorbei fremde={k.fremde} verbunden={k.agent.verbunden} />
            {#if loeschen === k.kennung}
              <div class="bestaetigen"><i class="fa-solid fa-triangle-exclamation"></i><span>{k.name} entfernen? Geht nur, wenn keine Dienste mehr darauf eingerichtet sind.</span>
                <div class="rechts"><button class="knopf klein ohne" onclick={() => (loeschen = null)}>Abbrechen</button>
                  <button class="knopf klein gefahr-voll" onclick={() => entfernen(k.kennung)}>Ja, entfernen</button></div></div>
            {/if}
            <footer class="kk-knoepfe">
              {#if knotenzustand(k) === 'schlaeft'}<button class="knopf" onclick={() => nichtMehrWarten(k)}
                      title="Der Rechner gilt nicht mehr als schlafend; Aufträge scheitern dann wieder, solange er nicht antwortet"><i class="fa-solid fa-sun"></i> Nicht mehr warten</button>{/if}
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
