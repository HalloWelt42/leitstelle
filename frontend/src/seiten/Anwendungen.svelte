<script lang="ts">
  import { api } from '../lib/api';
  import { arbeit } from '../lib/arbeit.svelte';
  import { uhrzeit } from '../lib/format';
  import { meldungen, tun } from '../lib/meldung.svelte';
  import type { AnwendungDaten, AnwendungSicht, Faehigkeit as F, Lagebild, Prioritaet, Zone } from '../lib/typen.gen';
  import { weg } from '../lib/weg.svelte';
  import { FAEHIGKEIT, PRIORITAET, art } from '../lib/wort';
  import Faehigkeit from '../teile/Faehigkeit.svelte';
  import ZoneMarke from '../teile/ZoneMarke.svelte';

  let { bild }: { bild: Lagebild } = $props();

  const ALLE = Object.keys(FAEHIGKEIT) as F[];
  const KETTEN: F[] = ['text', 'einbettung', 'bild_beschreiben', 'bild_erzeugen'];
  const leer = (): AnwendungDaten => ({ name: '', prioritaet: 1, faehigkeiten: ['text', 'einbettung', 'uebersetzen', 'bild_beschreiben', 'werkzeug'], zonen: ['heim'], extern_erlaubt: false, gleichzeitig: 4, ketten: {}, docker_projekte: [] });

  let entwurf = $state<AnwendungDaten>(leer());
  let neuerSchluessel = $state<{ name: string; schluessel: string } | null>(null);
  let schluessel = $state<string | null>(null);
  let frage = $state<'neu' | 'sperren' | 'loeschen' | null>(null);
  let sperrgrund = $state('');
  let kettenWahl = $state<Record<string, string>>({});
  // Entwurf, wie er gefüllt oder zuletzt gespeichert wurde; weicht er ab, ist die Bearbeitung offen
  let ausgang = $state(JSON.stringify(leer()));
  arbeit.bearbeitung(() => neuerSchluessel !== null || JSON.stringify(entwurf) !== ausgang);

  const gewaehlt = $derived(weg.teil && weg.teil !== 'neu' ? bild.anwendungen.find((a) => a.kennung === weg.teil) ?? null : null);
  const anlegen = $derived(weg.teil === 'neu');
  const basis = `${location.protocol}//${location.hostname}:8530/v1`;

  // Beim Wechsel der Auswahl den Entwurf aus der gewählten Anwendung füllen
  let fuerKennung = $state<string | null>(null);
  $effect(() => {
    const g = gewaehlt;
    const neu = anlegen;
    const k = g?.kennung ?? (neu ? 'neu' : null);
    if (k === fuerKennung) return;
    fuerKennung = k;
    schluessel = null;
    frage = null;
    const fuellung = g ? { name: g.name, prioritaet: g.prioritaet as Prioritaet, faehigkeiten: [...g.faehigkeiten], zonen: g.zonen.filter((z) => z !== 'extern'),
                           extern_erlaubt: g.extern_erlaubt, gleichzeitig: g.gleichzeitig, ketten: structuredClone($state.snapshot(g.ketten)),
                           docker_projekte: [...g.docker_projekte] } : leer();
    entwurf = fuellung;
    ausgang = JSON.stringify(fuellung);
  });

  const modelleFuer = (f: F) => [...new Map(bild.modelle.filter((m) => m.faehigkeiten.includes(f)).map((m) => [m.familie, m])).values()];
  const modellName = (familie: string) => bild.modelle.find((m) => m.familie === familie)?.name ?? familie;
  // Externe Modelle (beim Anbieter): in der Kette nur beim Ausweichen und mit Erlaubnis der App; ihre Art im Vergleich
  const extern = (familie: string) => bild.modelle.some((m) => m.familie === familie && bild.dienste.find((d) => d.kennung === m.dienst)?.extern);
  const wahlName = (familie: string) => {
    const m = bild.modelle.find((x) => x.familie === familie);
    if (!m || !extern(familie)) return modellName(familie);
    const a = art(m.steckbrief);
    return `${m.name} (extern${a ? `, ${a.wort}` : ''})`;
  };
  const hatExtern = $derived(bild.modelle.some((m) => extern(m.familie)));
  const kette = (f: F): string[] => (entwurf.ketten as Record<string, string[]>)[f] ?? [];
  // Docker-Projekte als Text mit Kommas; übernommen beim Verlassen des Felds (sonst verschluckte das Teilen das Komma beim Tippen)
  const teilen = (text: string) => [...new Set(text.split(',').map((t) => t.trim()).filter(Boolean))];

  function kettenSetzen(f: F, neu: string[]) {
    const k = { ...(entwurf.ketten as Record<string, string[]>) };
    if (neu.length) k[f] = neu; else delete k[f];
    entwurf.ketten = k;
  }
  function verschieben(f: F, i: number, um: number) {
    const k = [...kette(f)];
    const [x] = k.splice(i, 1);
    k.splice(i + um, 0, x);
    kettenSetzen(f, k);
  }
  function umschalten<T>(liste: T[], wert: T): T[] {
    return liste.includes(wert) ? liste.filter((x) => x !== wert) : [...liste, wert];
  }

  async function speichern() {
    if (anlegen) {
      const r = await tun(() => api.anwendungAnlegen(entwurf), 'Anwendung angelegt');
      if (r) { neuerSchluessel = { name: r.name, schluessel: r.schluessel }; weg.gehe('anwendungen', r.kennung, true); }
    } else if (gewaehlt) {
      if (await tun(() => api.anwendungAendern(gewaehlt.kennung, entwurf), 'Gespeichert')) ausgang = JSON.stringify(entwurf);
    }
  }

  async function aufdecken() {
    if (!gewaehlt) return;
    if (schluessel) { schluessel = null; return; }
    schluessel = (await tun(() => api.schluesselZeigen(gewaehlt.kennung)))?.schluessel ?? null;
  }

  async function kopieren(text: string) {
    try { await navigator.clipboard.writeText(text); meldungen.zeigen('Kopiert'); } catch { meldungen.zeigen('Kopieren ging nicht; bitte markieren und kopieren', 'hinweis'); }
  }

  async function kopierenSchluessel() {
    if (!gewaehlt) return;
    const s = schluessel ?? (await tun(() => api.schluesselZeigen(gewaehlt.kennung)))?.schluessel;
    if (s) kopieren(s);
  }

  async function neuErzeugen() {
    if (!gewaehlt) return;
    const r = await tun(() => api.schluesselNeu(gewaehlt.kennung), 'Neuer Schlüssel erzeugt; der alte gilt nicht mehr');
    if (r) { schluessel = r.schluessel; frage = null; }
  }

  const zonenWort = (a: AnwendungSicht) => a.zonen;
</script>

<div class="seiteninhalt seite-anwendungen">
  <div class="rahmen-kopf">
    <div class="seitenkopf">
      <h1>Anwendungen</h1><span class="zahl">{bild.anwendungen.length}</span>
      <div class="aktionen">
        <a class="knopf haupt" href={weg.pfad('anwendungen', 'neu')} onclick={(e) => weg.klick(e, 'anwendungen', 'neu')}
           title="Neue Anwendung anlegen: Name und Rechte; der Schlüssel wird erzeugt"><i class="fa-solid fa-plus"></i> Anwendung anlegen</a>
      </div>
    </div>
    <div class="kennzahlen">
      <div class="kennzahl"><b>{bild.anwendungen.length}</b><span>Anwendungen</span></div>
      <div class="kennzahl"><b>{bild.anwendungen.filter((a) => a.extern_erlaubt).length}</b><span>Dürfen extern</span></div>
      {#if bild.anwendungen.some((a) => a.gesperrt)}<div class="kennzahl fehler"><b>{bild.anwendungen.filter((a) => a.gesperrt).length}</b><span>Gesperrt</span></div>{/if}
    </div>
  </div>

  <div class="spalten breit-rechts">
    <div class="rollfeld tabellen-raum">
      {#if bild.anwendungen.length}
        <table class="tabelle karten">
          <thead><tr><th>Anwendung</th><th>Zustand</th><th>Fähigkeiten</th><th>Priorität</th><th>Zonen</th></tr></thead>
          <tbody>
            {#each bild.anwendungen as a (a.kennung)}
              <tr class:gewaehlt={gewaehlt?.kennung === a.kennung} style="cursor: pointer" onclick={() => weg.gehe('anwendungen', a.kennung, true)}>
                <td><div class="name"><a href={weg.pfad('anwendungen', a.kennung)} onclick={(e) => { e.stopPropagation(); weg.klick(e, 'anwendungen', a.kennung); }}>{a.name}</a></div>
                  <div class="wo klein leise">angelegt {uhrzeit(a.angelegt_s)}</div></td>
                <td data-titel="Zustand">{#if a.gesperrt}<span class="zustand fehler" title={a.sperrgrund}><i class="fa-solid fa-ban"></i>Gesperrt</span>{:else}<span class="zustand fertig"><i class="fa-solid fa-circle-check"></i>Frei</span>{/if}</td>
                <td data-titel="Fähigkeiten"><div class="marken">{#each a.faehigkeiten.filter((f) => f !== 'uebersetzen' && f !== 'werkzeug') as f (f)}<Faehigkeit wert={f} />{/each}</div></td>
                <td data-titel="Priorität"><span class="prio {PRIORITAET[a.prioritaet].klasse}">{PRIORITAET[a.prioritaet].wort}</span></td>
                <td data-titel="Zonen">{#each zonenWort(a) as z (z)}<ZoneMarke wert={z} /> {/each}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <div class="leer"><i class="fa-solid fa-cubes"></i><h2>Noch keine Anwendung</h2>
          <p>Jede Anwendung bekommt einen eigenen Schlüssel. Programme, die nur die gewöhnliche OpenAI-Schnittstelle kennen, stellen nur Adresse und Schlüssel um.</p>
          <a class="knopf haupt" href={weg.pfad('anwendungen', 'neu')} onclick={(e) => weg.klick(e, 'anwendungen', 'neu')}><i class="fa-solid fa-plus"></i> Anwendung anlegen</a></div>
      {/if}
    </div>

    <div class="rollfeld">
      {#if neuerSchluessel && gewaehlt}
        <div class="hinweis warnung schluessel-neu" style="margin-bottom: var(--a3)"><i class="fa-solid fa-key"></i>
          <span>Schlüssel für <b>{neuerSchluessel.name}</b>: <code>{neuerSchluessel.schluessel}</code>. Er bleibt hier unter dem Auge abrufbar.</span>
          <button class="knopf klein" onclick={() => neuerSchluessel && kopieren(neuerSchluessel.schluessel)}><i class="fa-solid fa-copy"></i> Kopieren</button>
          <button class="knopf klein ohne" onclick={() => (neuerSchluessel = null)}>Schließen</button></div>
      {/if}

      {#if gewaehlt || anlegen}
        <div class="karte">
          <h3><i class="fa-solid {anlegen ? 'fa-plus' : 'fa-cube'}"></i>{anlegen ? 'Neue Anwendung' : gewaehlt?.name}
            {#if gewaehlt?.gesperrt}<span class="rechts zustand fehler"><i class="fa-solid fa-ban"></i>Gesperrt: {gewaehlt.sperrgrund}</span>{/if}</h3>
          <div class="feldreihe">
            <label class="feld-l"><span>Name</span><input class="eingabe" bind:value={entwurf.name} placeholder="zum Beispiel Codehilfe" /></label>
            <label class="feld-l"><span>Gleichzeitig höchstens <small>weitere Aufträge werden eingereiht</small></span><input class="eingabe" type="number" min="1" max="64" bind:value={entwurf.gleichzeitig} /></label>
          </div>
          <div class="etikett" style="margin-top: var(--a4)">Priorität (Vorgabe)</div>
          <span class="stufen" title="Gilt für jeden Auftrag dieser Anwendung; der Kopf X-Leitstelle-Prioritaet darf sie je Aufruf nur absenken">
            {#each [0, 1, 2, 3] as p (p)}<button class:an={entwurf.prioritaet === p} onclick={() => (entwurf.prioritaet = p as Prioritaet)}>{PRIORITAET[p].wort}</button>{/each}
          </span>
          <div class="etikett" style="margin-top: var(--a4)">Fähigkeiten</div>
          <div class="filter" style="margin: 6px 0 0">
            {#each ALLE as f (f)}
              <button class="chip" class:aktiv={entwurf.faehigkeiten?.includes(f)} onclick={() => (entwurf.faehigkeiten = umschalten(entwurf.faehigkeiten ?? [], f))}
                      title="{FAEHIGKEIT[f].wort} {entwurf.faehigkeiten?.includes(f) ? 'erlaubt; abwählen lehnt solche Aufträge ab' : 'nicht erlaubt'}"><i class="fa-solid {FAEHIGKEIT[f].symbol}"></i> {FAEHIGKEIT[f].wort}</button>
            {/each}
          </div>
          <div class="etikett" style="margin-top: var(--a4)">Zonen</div>
          <div class="filter" style="margin: 6px 0 0">
            <button class="chip aktiv" disabled title="Heimnetz ist immer erlaubt"><i class="fa-solid fa-house"></i> Heimnetz</button>
            <button class="chip" class:aktiv={entwurf.zonen?.includes('fern')} onclick={() => (entwurf.zonen = umschalten(entwurf.zonen ?? [], 'fern' as Zone))}
                    title="Rechner über VPN dürfen rechnen"><i class="fa-solid fa-shield-halved"></i> Über VPN</button>
            <button class="chip" class:aktiv={entwurf.extern_erlaubt} onclick={() => (entwurf.extern_erlaubt = !entwurf.extern_erlaubt)}
                    title="Externe Anbieter dürfen rechnen; Daten verlassen dann das Heimnetz"><i class="fa-solid fa-cloud"></i> Extern</button>
          </div>

          <label class="feld-l" style="margin-top: var(--a4)"><span>Docker-Projekte <small>ihre Container im Docker-Rechner eines Rechners:
            Compose-Projekte oder Containernamen, mit Komma getrennt. Hat die Anwendung Hintergrundarbeit, zählt deren Last nicht zur Docker-Last
            (sonst bremste sich die Leitstelle an der eigenen Arbeit)</small></span>
            <input class="eingabe" value={(entwurf.docker_projekte ?? []).join(', ')} placeholder="zum Beispiel fundus"
                   onchange={(e) => (entwurf.docker_projekte = teilen(e.currentTarget.value))} /></label>

          <div class="etikett" style="margin-top: var(--a4)" title="Die Kette ist die Wahl der Anwendung: die Leitstelle nimmt nur Modelle daraus und entscheidet nur Rechner, Laden, Warten und Vorrang">Modellketten <span class="leise" style="text-transform:none; letter-spacing:0; font-weight:500">Wahl der Anwendung, wenn sie kein Modell nennt; erstes verfügbares gewinnt</span></div>
          {#if hatExtern}<p class="leise klein kettenhinweis">Externe Modelle rechnen beim Anbieter: in der Kette nur, wenn lokal länger gewartet würde und die
            Anwendung sie auf ihre Erlaubnisliste setzt; nennt sie eines als Modell, gilt es direkt. Das schnelle taugt für kurze Aufgaben, das
            gründliche für lange Texte; die Wahl bleibt bei der Anwendung.</p>{/if}
          {#each KETTEN.filter((f) => entwurf.faehigkeiten?.includes(f)) as f (f)}
            <div class="modellkette">
              <div title={f === 'bild_erzeugen' ? 'Bildmodell der Anwendung, wenn sie selbst keines nennt; ohne Kette und ohne Modell antwortet die Leitstelle mit der Liste der Bildmodelle, statt eines auszusuchen' : undefined}><Faehigkeit wert={f} /></div>
              <div class="kette">
                {#each kette(f) as fam, i (fam)}
                  <span class="schritt" title={extern(fam) ? `${wahlName(fam)}: rechnet beim Anbieter, in der Kette nur beim Ausweichen und wenn die Anwendung es erlaubt` : fam}><i class="fa-solid {extern(fam) ? 'fa-cloud' : 'fa-brain'}"></i>{modellName(fam)}
                    {#if i > 0}<button class="knopf ohne symbol klein" onclick={() => verschieben(f, i, -1)} title="Nach vorn"><i class="fa-solid fa-arrow-left"></i></button>{/if}
                    <button class="knopf ohne symbol klein" onclick={() => kettenSetzen(f, kette(f).filter((x) => x !== fam))} title="Aus der Kette nehmen"><i class="fa-solid fa-xmark"></i></button></span>
                  {#if i < kette(f).length - 1}<span class="pfeil"></span>{/if}
                {/each}
                <select class="eingabe" style="height: 34px; max-width: 260px" bind:value={kettenWahl[f]}
                        onchange={() => { if (kettenWahl[f]) { kettenSetzen(f, [...kette(f), kettenWahl[f]]); kettenWahl[f] = ''; } }} title="Modell ans Ende der Kette setzen">
                  <option value="">Modell anfügen</option>
                  {#each modelleFuer(f).filter((m) => !kette(f).includes(m.familie)) as m (m.familie)}<option value={m.familie}>{wahlName(m.familie)}</option>{/each}
                </select>
              </div>
            </div>
          {/each}

          <div class="tun" style="margin-top: var(--a4); display: flex; gap: var(--a2); flex-wrap: wrap">
            <button class="knopf haupt" onclick={speichern} disabled={!entwurf.name.trim()}><i class="fa-solid fa-floppy-disk"></i> {anlegen ? 'Anlegen und Schlüssel erzeugen' : 'Speichern'}</button>
            {#if gewaehlt}
              {#if gewaehlt.gesperrt}<button class="knopf" onclick={() => tun(() => api.freigeben(gewaehlt.kennung), 'Freigegeben')}><i class="fa-solid fa-unlock"></i> Freigeben</button>
              {:else}<button class="knopf gefahr" onclick={() => (frage = 'sperren')} title="Nimmt nichts mehr an; laufende Aufträge enden"><i class="fa-solid fa-ban"></i> Sperren</button>{/if}
              <button class="knopf ohne gefahr" onclick={() => (frage = 'loeschen')} title="Anwendung entfernen; der Schlüssel gilt dann nicht mehr"><i class="fa-solid fa-trash"></i></button>
            {/if}
          </div>
          {#if frage === 'sperren' && gewaehlt}
            <div class="bestaetigen"><i class="fa-solid fa-ban"></i><span>{gewaehlt.name} sperren? Neue Aufrufe bekommen 429 mit Grund.</span>
              <input class="eingabe" style="height: 34px" placeholder="Grund" bind:value={sperrgrund} />
              <div class="rechts"><button class="knopf klein ohne" onclick={() => (frage = null)}>Abbrechen</button>
                <button class="knopf klein gefahr-voll" onclick={async () => { if (await tun(() => api.sperren(gewaehlt.kennung, sperrgrund), 'Gesperrt')) { frage = null; sperrgrund = ''; } }}>Ja, sperren</button></div></div>
          {/if}
          {#if frage === 'loeschen' && gewaehlt}
            <div class="bestaetigen"><i class="fa-solid fa-trash"></i><span>{gewaehlt.name} entfernen? Der Schlüssel gilt sofort nicht mehr; der Verlauf bleibt.</span>
              <div class="rechts"><button class="knopf klein ohne" onclick={() => (frage = null)}>Abbrechen</button>
                <button class="knopf klein gefahr-voll" onclick={async () => { if (await tun(() => api.anwendungLoeschen(gewaehlt.kennung), 'Entfernt')) weg.gehe('anwendungen', null, true); }}>Ja, entfernen</button></div></div>
          {/if}
        </div>

        {#if gewaehlt}
          <div class="karte">
            <h3><i class="fa-solid fa-key"></i>Zugang <span class="rechts">Schlüssel als Bearer</span></h3>
            <div class="zugang-zeile">
              <div class="bez">Schlüssel<small>stabil, bis du ihn neu erzeugst</small></div>
              <div class="schluessel">
                <span class="wert zahl">{schluessel ?? '•••••••••••••••••••••••••••'}</span>
                <button class="knopf symbol" onclick={aufdecken} title="Schlüssel aufdecken; steht im Prüfprotokoll"><i class="fa-solid {schluessel ? 'fa-eye-slash' : 'fa-eye'}"></i></button>
                <button class="knopf" onclick={kopierenSchluessel} title="Kopiert den vollen Schlüssel"><i class="fa-solid fa-copy"></i> Kopieren</button>
                <button class="knopf warnung" onclick={() => (frage = 'neu')} title="Bestätigen nötig; danach gilt nur noch der neue"><i class="fa-solid fa-rotate"></i> Neu erzeugen</button>
              </div>
            </div>
            {#if frage === 'neu'}
              <div class="bestaetigen"><i class="fa-solid fa-triangle-exclamation"></i>
                <div class="text"><b>Neu erzeugen?</b><span> Der alte Schlüssel gilt sofort nicht mehr; {gewaehlt.name} braucht den neuen.</span></div>
                <div class="rechts"><button class="knopf klein ohne" onclick={() => (frage = null)}>Abbrechen</button>
                  <button class="knopf klein gefahr-voll" onclick={neuErzeugen}><i class="fa-solid fa-rotate"></i> Ja, neu erzeugen</button></div></div>
            {/if}
            <div class="etikett" style="margin-top: var(--a4)">Einbau (Stufe 1, nur die gewöhnliche Schnittstelle)</div>
            <div class="einbau"><code>Basisadresse {basis}</code><button class="knopf ohne symbol klein" onclick={() => kopieren(basis)} title="Basisadresse kopieren"><i class="fa-solid fa-copy"></i></button></div>
            <div class="einbau"><code>Authorization: Bearer &lt;Schlüssel&gt;</code></div>
            <p class="leise klein" style="margin-top: var(--a2)">Modellname darf bleiben, wie er ist; ohne Modell gilt die Kette. Lese-Zeitgrenzen in der Anwendung entfernen; während des Wartens kommen Kommentarzeilen.</p>
          </div>
        {/if}
      {:else}
        <div class="leer"><i class="fa-solid fa-hand-pointer"></i><h2>Anwendung wählen</h2><p>Links eine Anwendung anklicken oder eine neue anlegen.</p></div>
      {/if}
    </div>
  </div>
</div>

<style>
  .kettenhinweis { margin: 4px 0 var(--a2); }
</style>
