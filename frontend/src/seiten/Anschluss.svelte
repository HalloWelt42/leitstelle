<script lang="ts">
  import { api } from '../lib/api';
  import { arbeit } from '../lib/arbeit.svelte';
  import { gb } from '../lib/format';
  import { tun } from '../lib/meldung.svelte';
  import type { Erkennung, Lagebild, Zone } from '../lib/typen.gen';
  import { weg } from '../lib/weg.svelte';
  import Faehigkeit from '../teile/Faehigkeit.svelte';
  import ZoneMarke from '../teile/ZoneMarke.svelte';

  // Minimal-invasiv: Adresse, bei Bedarf Zugang; alles andere erkennt die Leitstelle ohne etwas zu verändern
  let { bild }: { bild: Lagebild } = $props();

  let art = $state<'dienst' | 'extern'>('dienst');
  let adresse = $state('');
  let zugang = $state('');
  let zugangSehen = $state(false);
  let erkennung = $state<Erkennung | null>(null);
  let erkennt = $state(false);
  let name = $state('');
  let knotenWahl = $state<string>('neu');
  let neuName = $state('');
  let neuSpeicher = $state<number | null>(null);
  let neuZone = $state<Zone>('heim');
  let plaetze = $state(4);
  let nameGeaendert = $state(false);
  // Begonnener Anschluss (Adresse eingetragen oder schon erkannt): keine neue Fassung mittendrin laden
  arbeit.bearbeitung(() => adresse.trim() !== '' || erkennung !== null);
  // Solange der Name nicht von Hand geändert ist, folgt er dem gewählten oder neu eingetragenen Rechner
  const namensvorschlag = $derived(art === 'extern' ? (erkennung?.name_vorschlag ?? '')
    : `Modell-Läufer ${knotenWahl === 'neu' ? (neuName.trim() || erkennung?.rechnername || '') : (bild.knoten.find((k) => k.kennung === knotenWahl)?.name ?? '')}`.trim());
  $effect(() => {
    if (!nameGeaendert) name = namensvorschlag;
  });

  const faehigkeiten = $derived([...new Set(erkennung?.modelle.flatMap((m) => m.faehigkeiten) ?? [])].filter((f) => f !== 'uebersetzen' && f !== 'werkzeug'));
  const geladen = $derived(erkennung?.modelle.filter((m) => m.geladen) ?? []);

  function vervollstaendigen(a: string): string {
    const t = a.trim();
    if (!t) return t;
    return /^https?:\/\//.test(t) ? t : `${art === 'extern' ? 'https' : 'http'}://${t}`;
  }

  async function erkennen() {
    adresse = vervollstaendigen(adresse);
    erkennt = true;
    const e = await tun(() => api.dienstErkennen(adresse, zugang || null, art === 'extern'));
    erkennt = false;
    erkennung = e ?? null;
    if (e) {
      knotenWahl = e.knoten_vorschlag ?? 'neu';
      neuName = neuName || (e.rechnername ?? '');
    }
  }

  async function anschliessen() {
    if (!erkennung) return;
    const neuerKnoten = art === 'dienst' && knotenWahl === 'neu'
      ? { name: neuName.trim() || erkennung.rechnername || 'Rechner', adresse: erkennung.rechnername ?? '', speicher_gb: neuSpeicher ?? 0, zone: neuZone }
      : null;
    const r = await tun(() => api.dienstAnlegen({ adresse: erkennung!.adresse, name: name.trim() || null, zugang: zugang || null, extern: art === 'extern',
      knoten: art === 'dienst' && knotenWahl !== 'neu' ? knotenWahl : null, neuer_knoten: neuerKnoten, plaetze }), 'Dienst angeschlossen');
    if (r) weg.gehe('dienste');
  }

  const bereit = $derived(!!erkennung?.erreichbar && (art === 'extern' || knotenWahl !== 'neu' || (neuSpeicher ?? 0) > 0));
</script>

<div class="seiteninhalt seite-anschluss">
  <div class="rahmen-kopf">
    <div class="seitenkopf">
      <a class="knopf ohne symbol" href={weg.pfad('dienste')} onclick={(e) => weg.klick(e, 'dienste')} title="Zurück zu den Diensten"><i class="fa-solid fa-arrow-left"></i></a>
      <h1>Anschluss hinzufügen</h1>
      <div class="unterzeile">Nur das Nötigste eingeben: Adresse, bei Bedarf einen Zugang. Modelle, Fähigkeiten und Steuerbarkeit erkennt die Leitstelle selbst, ohne etwas zu laden oder zu ändern.</div>
    </div>
  </div>
  <div class="spalten">
    <div class="rollfeld">
      <div class="karte">
        <div class="etikett">Was wird angeschlossen?</div>
        <div class="arten">
          <button class="art-karte" class:an={art === 'dienst'} onclick={() => { art = 'dienst'; erkennung = null; }}
                  title="Ein Modell-Läufer im eigenen Netz, zum Beispiel auf dem Mac Studio"><i class="fa-solid fa-plug"></i><b>Dienst im eigenen Netz</b><span>Läuft schon irgendwo. Adresse genügt.</span></button>
          <button class="art-karte" class:an={art === 'extern'} onclick={() => { art = 'extern'; erkennung = null; }}
                  title="Anbieter im Internet mit OpenAI-Schnittstelle und Schlüssel"><i class="fa-solid fa-cloud"></i><b>Externer Anbieter</b><span>Adresse und Schlüssel, nur über https.</span></button>
          <a class="art-karte" href={weg.pfad('anwendungen', 'neu')} onclick={(e) => weg.klick(e, 'anwendungen', 'neu')}
             title="Ein Programm, das Aufträge abgeben will"><i class="fa-solid fa-cubes"></i><b>Anwendung</b><span>Name und Rechte; der Schlüssel wird erzeugt.</span></a>
        </div>

        <div class="feldreihe" style="margin-top: var(--ls-a4)">
          <label class="feld-l"><span>Adresse <small>{art === 'extern' ? 'zum Beispiel https://anbieter.example/v1' : 'zum Beispiel 192.168.1.20:1234 oder mac-studio.local:1234'}</small></span>
            <input class="eingabe" bind:value={adresse} onkeydown={(e) => e.key === 'Enter' && erkennen()} placeholder={art === 'extern' ? 'https://' : 'Rechner:Port'} /></label>
          <label class="feld-l"><span>Zugang <small>Schlüssel oder Token, nur wenn der Dienst einen verlangt</small></span>
            <span class="feld-l zeile-feld"><input class="eingabe" type={zugangSehen ? 'text' : 'password'} bind:value={zugang} placeholder="leer lassen, wenn nicht nötig" />
              <button class="knopf symbol" onclick={() => (zugangSehen = !zugangSehen)} title="Eingabe aufdecken oder verdecken"><i class="fa-solid {zugangSehen ? 'fa-eye-slash' : 'fa-eye'}"></i></button></span></label>
        </div>
        <div class="tun" style="margin-top: var(--ls-a3); display: flex; gap: var(--ls-a2)">
          <button class="knopf" onclick={erkennen} disabled={!adresse.trim() || erkennt} title="Prüft die Adresse und liest Modelle und Fähigkeiten; verändert nichts">
            <i class="fa-solid {erkennt ? 'fa-rotate fa-spin' : 'fa-magnifying-glass'}"></i> {erkennung ? 'Erneut erkennen' : 'Erkennen'}</button>
        </div>

        {#if erkennung}
          <div class="pruefung">
            <h3><i class="fa-solid {erkennung.erreichbar ? 'fa-circle-check' : 'fa-circle-xmark'}"></i>{erkennung.erreichbar ? 'Erkannt' : 'Nicht erreichbar'}</h3>
            <div class="pruef"><i class="fa-solid {erkennung.erreichbar ? 'fa-check' : 'fa-xmark'}"></i><span class="k">Erreichbar</span>
              <span class="v">{erkennung.erreichbar ? `ja, unter ${erkennung.adresse}` : erkennung.meldung}</span></div>
            {#if erkennung.erreichbar}
              <div class="pruef"><i class="fa-solid fa-check"></i><span class="k">Steuerung</span>
                <span class="v">{erkennung.steuerbar ? 'Leitstelle liest den echten Ladezustand, lädt und entlädt selbst' : 'nur Modellliste; der Dienst lädt selbst'}</span></div>
              <div class="pruef"><i class="fa-solid fa-check"></i><span class="k">Modelle</span>
                <span class="v">{erkennung.modelle.length} gefunden{geladen.length ? `, geladen: ${geladen.map((m) => `${m.name} (${gb(m.gb)})`).join(', ')}` : ', keines geladen'}</span></div>
              <div class="pruef"><i class="fa-solid fa-check"></i><span class="k">Fähigkeiten</span><span class="v marken">{#each faehigkeiten as f (f)}<Faehigkeit wert={f} />{/each}</span></div>
              {#if art === 'dienst'}
                <div class="pruef"><i class="fa-solid {knotenWahl === 'neu' ? 'fa-plus' : 'fa-check'}"></i><span class="k">Rechner</span>
                  <span class="v">
                    <select class="eingabe" bind:value={knotenWahl} style="height: 36px" title="Zu welchem Rechner gehört der Dienst? Gleiche Adresse wird vorgeschlagen">
                      {#each bild.knoten as k (k.kennung)}<option value={k.kennung}>{k.name} ({k.adresse})</option>{/each}
                      <option value="neu">Neuer Rechner</option>
                    </select>
                    {#if erkennung.knoten_vorschlag && knotenWahl === erkennung.knoten_vorschlag}<span class="leise"> Adresse stimmt überein</span>{/if}
                  </span></div>
                {#if knotenWahl === 'neu'}
                  <div class="feldreihe">
                    <label class="feld-l"><span>Name des Rechners</span><input class="eingabe" bind:value={neuName} placeholder="zum Beispiel Mac Studio" /></label>
                    <label class="feld-l"><span>Speicher in GB <small>Pflicht, bis ein Maschinenraum misst</small></span><input class="eingabe" type="number" min="1" bind:value={neuSpeicher} placeholder="128" /></label>
                    <label class="feld-l"><span>Zone</span><select class="eingabe" bind:value={neuZone}><option value="heim">Heimnetz</option><option value="fern">Über VPN</option></select></label>
                  </div>
                {/if}
              {/if}
              <div class="pruef"><i class="fa-solid fa-check"></i><span class="k">Zone</span><span class="v"><ZoneMarke wert={art === 'extern' ? 'extern' : knotenWahl === 'neu' ? neuZone : (bild.knoten.find((k) => k.kennung === knotenWahl)?.zone ?? 'heim')} /></span></div>
              <div class="pruef hinweis-z"><i class="fa-solid {erkennung.adresse.startsWith('https') ? 'fa-lock' : 'fa-circle-info'}"></i><span class="k">Verschlüsselung</span>
                <span class="v">{erkennung.adresse.startsWith('https') ? 'https' : 'Klartext im eigenen Netz, erlaubt'}</span></div>
              <div class="pruef"><i class="fa-solid fa-check"></i><span class="k">Name</span><span class="v"><input class="eingabe" style="height:34px; width: 280px" bind:value={name} oninput={() => (nameGeaendert = true)} /></span></div>
              <div class="pruef"><i class="fa-solid fa-check"></i><span class="k">Plätze</span>
                <span class="v"><input class="eingabe" type="number" min="1" max="64" style="height:34px; width: 90px" bind:value={plaetze} title="Gleichzeitige Aufträge je geladenem Modell" /> <span class="leise">gleichzeitige Aufträge je Modell</span></span></div>
            {/if}
          </div>
          <div class="tun" style="margin-top: var(--ls-a4); display: flex; gap: var(--ls-a2)">
            <button class="knopf haupt" disabled={!bereit} onclick={anschliessen} title="Dienst anlegen; er erscheint sofort und bekommt Aufträge nach den Regeln">
              <i class="fa-solid fa-plug-circle-check"></i> Anschließen</button>
            <a class="knopf ohne" href={weg.pfad('dienste')} onclick={(e) => weg.klick(e, 'dienste')}>Abbrechen</a>
          </div>
        {/if}
      </div>
    </div>
    <div class="rollfeld">
      <div class="karte wege">
        <h3><i class="fa-solid fa-lock"></i>Verschlüsselter Weg</h3>
        <div class="weg heim"><i class="fa-solid fa-house"></i><div><b>Heimnetz</b>Klartext erlaubt, https wird genutzt, wenn der Dienst es anbietet.</div></div>
        <div class="weg fern"><i class="fa-solid fa-shield-halved"></i><div><b>Über VPN</b>Der Tunnel verschlüsselt alles; Dienste dort gelten wie im Heimnetz.</div></div>
        <div class="weg extern"><i class="fa-solid fa-cloud"></i><div><b>Extern</b>Nur https. Der Schlüssel liegt verschlüsselt in der Leitstelle; keine Anwendung sieht ihn.</div></div>
      </div>
      <div class="karte andere">
        <h3><i class="fa-solid fa-list"></i>So wenig ist nötig</h3>
        <div class="zeile-a"><b>Dienst</b><span>Adresse, optional Zugang; Modelle, Fähigkeiten und Steuerbarkeit werden erkannt</span></div>
        <div class="zeile-a"><b>Neuer Rechner</b><span>Name und Speicher; der Dienst wird ihm zugeordnet</span></div>
        <div class="zeile-a"><b>Externer Anbieter</b><span>Adresse und Schlüssel; Anwendungen dürfen ihn nur mit Erlaubnis nutzen</span></div>
      </div>
    </div>
  </div>
</div>
