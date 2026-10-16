<script lang="ts">
  import { api, type FreigabePlan } from '../lib/api';
  import { gb, prozent, vor, zahl } from '../lib/format';
  import { kanal } from '../lib/kanal.svelte';
  import { tun } from '../lib/meldung.svelte';
  import type { Lagebild, ModellSicht } from '../lib/typen.gen';
  import { weg } from '../lib/weg.svelte';
  import Faehigkeit from '../teile/Faehigkeit.svelte';
  import Speicherbalken from '../teile/Speicherbalken.svelte';
  import Zustand from '../teile/Zustand.svelte';

  let { bild }: { bild: Lagebild } = $props();

  let filterKnoten = $state<string>('alle');
  let frage = $state<{ modell: ModellSicht; laden: boolean } | null>(null);
  let freigabeKnoten = $state<string | null>(null);
  let plan = $state<FreigabePlan | null>(null);
  let jetzt = $state(kanal.jetzt());

  $effect(() => {
    const t = setInterval(() => (jetzt = kanal.jetzt()), 5000);
    return () => clearInterval(t);
  });

  const knotenName = (k: string | null) => bild.knoten.find((x) => x.kennung === k)?.name ?? 'Extern';
  const dienst = (k: string) => bild.dienste.find((d) => d.kennung === k);
  const sichtbar = $derived(bild.modelle.filter((m) => filterKnoten === 'alle' || (filterKnoten === 'extern' ? dienst(m.dienst)?.extern : m.knoten === filterKnoten)));
  const imSpeicher = $derived(bild.modelle.filter((m) => m.zustand !== 'frei' && !dienst(m.dienst)?.extern));
  const rechnen = $derived(bild.modelle.filter((m) => m.zustand === 'rechnet'));
  const geschuetzt = $derived(bild.modelle.filter((m) => m.geschuetzt));
  const gesperrt = $derived(bild.modelle.filter((m) => m.ladesperre_bis_s && m.ladesperre_bis_s > jetzt));
  const wartenAuf = (m: ModellSicht) => bild.auftraege.filter((a) => a.zustand !== 'laeuft' && a.familie_wunsch === m.familie).length;
  const steuerbar = (m: ModellSicht) => !!dienst(m.dienst)?.steuerbar && !dienst(m.dienst)?.extern;
  const knotenMit = $derived(bild.knoten.filter((k) => bild.modelle.some((m) => m.knoten === k.kennung)));
  const hatExtern = $derived(bild.dienste.some((d) => d.extern));

  // "Speicher freigeben" aus der Übersicht: /modelle/freigeben öffnet die Vorschau für den vollsten Rechner
  $effect(() => {
    if (weg.teil === 'freigeben' && !freigabeKnoten) {
      const k = [...bild.knoten].filter((x) => x.erreichbar).sort((a, b) => b.belegt_anteil - a.belegt_anteil)[0];
      if (k) vorschau(k.kennung);
    }
  });

  async function vorschau(knoten: string) {
    freigabeKnoten = knoten;
    plan = (await tun(() => api.speicherFreigeben(knoten, true))) ?? null;
  }

  async function freigeben() {
    if (!freigabeKnoten || !plan) return;
    const r = await tun(() => api.speicherFreigeben(freigabeKnoten!, false), `${gb(plan.frei_gb)} auf ${knotenName(freigabeKnoten)} werden freigegeben`);
    if (r) { plan = null; freigabeKnoten = null; weg.gehe('modelle', null, true); }
  }

  // Dienste unter einem Knoten-Agenten sind Programme: dort heißt Laden Starten und Entladen Anhalten
  const WORTE = {
    modell: { laden: 'Laden', entladen: 'Entladen', ja_laden: 'Ja, laden', ja_entladen: 'Ja, entladen', wird_laden: 'wird geladen', wird_entladen: 'wird entladen', geladen: 'geladen' },
    prozess: { laden: 'Starten', entladen: 'Anhalten', ja_laden: 'Ja, starten', ja_entladen: 'Ja, anhalten', wird_laden: 'wird gestartet', wird_entladen: 'wird angehalten', geladen: 'läuft seit' },
  };
  const worte = (m: ModellSicht) => (dienst(m.dienst)?.art === 'agent' ? WORTE.prozess : WORTE.modell);

  async function bestaetigt() {
    if (!frage) return;
    const { modell, laden } = frage;
    const w = worte(modell);
    const r = await tun(() => (laden ? api.modellLaden(modell.kennung) : api.modellEntladen(modell.kennung)), `${modell.name} ${laden ? w.wird_laden : w.wird_entladen}`);
    if (r !== undefined) frage = null;
  }
</script>

<div class="seiteninhalt seite-modelle">
  <div class="rahmen-kopf">
    <div class="seitenkopf">
      <h1>Modelle</h1><span class="zahl">{bild.modelle.length}</span>
    </div>
    <div class="kennzahlen">
      <div class="kennzahl"><b>{bild.modelle.length}</b><span>Modelle</span><small>auf {bild.dienste.length} Diensten</small></div>
      <div class="kennzahl erfolg"><b>{imSpeicher.length}</b><span>Im Speicher</span><small>{gb(imSpeicher.reduce((s, m) => s + m.gb, 0))}</small></div>
      <div class="kennzahl laeuft"><b>{rechnen.length}</b><span>Rechnen</span></div>
      <div class="kennzahl"><b>{geschuetzt.length}</b><span>Geschützt</span><small>weichen nie von selbst</small></div>
      {#if gesperrt.length}<div class="kennzahl wartet"><b>{gesperrt.length}</b><span>Laden abgelehnt</span><small>neuer Versuch nach Pause</small></div>{/if}
    </div>
    {#each knotenMit.filter((k) => filterKnoten === 'alle' || filterKnoten === k.kennung) as k (k.kennung)}
      <div class="speicherkopf">
        <div class="sp-zeile">
          <span class="n">{k.name} <span class="leise klein">{gb(k.speicher_gb)}</span></span>
          <span class="w" class:warn={k.frei_gb < 0}><span class="zahl">{prozent(k.belegt_anteil)}</span> belegt · <span class="zahl">{gb(Math.max(0, k.frei_gb))}</span> frei im Budget{k.frei_gb < 0 ? ' · über dem Budget' : ''}</span>
          <div class="speicher-legende">
            <span><i class="fa-solid fa-square" style="color: var(--ls-himmel)"></i>Text</span>
            <span><i class="fa-solid fa-square" style="color: var(--ls-flieder)"></i>Bild</span>
            <span><i class="fa-solid fa-square" style="color: var(--ls-petrol)"></i>Einbettung</span>
            <span><i class="fa-solid fa-square" style="color: var(--ls-stahl)"></i>System <span class="zahl">{gb(k.system_gb)}</span></span>
          </div>
        </div>
        <Speicherbalken knoten={k} modelle={bild.modelle} budgetmarke />
      </div>
    {/each}
    <div class="filter" style="margin-top: var(--ls-a3); margin-bottom: 0">
      <span class="etikett">Knoten</span>
      <button class="chip" class:aktiv={filterKnoten === 'alle'} onclick={() => (filterKnoten = 'alle')} title="Alle Modelle aller Knoten">Alle <span class="zaehler">{bild.modelle.length}</span></button>
      {#each knotenMit as k (k.kennung)}
        <button class="chip" class:aktiv={filterKnoten === k.kennung} onclick={() => (filterKnoten = k.kennung)} title="Nur Modelle auf {k.name}">{k.name}
          <span class="zaehler">{bild.modelle.filter((m) => m.knoten === k.kennung).length}</span></button>
      {/each}
      {#if hatExtern}<button class="chip" class:aktiv={filterKnoten === 'extern'} onclick={() => (filterKnoten = 'extern')} title="Nur Modelle externer Anbieter">Extern</button>{/if}
    </div>
  </div>

  <div class="spalten schmal-rechts">
    <div class="rollfeld">
      {#if bild.modelle.length}
        <table class="tabelle modelltabelle">
          <thead><tr><th>Modell</th><th>Fähigkeiten</th><th>Dienst</th><th style="text-align:right">Größe</th><th>Zustand</th><th></th></tr></thead>
          <tbody>
            {#each sichtbar as m (m.kennung)}
              {@const warten = wartenAuf(m)}
              <tr>
                <td><div class="n">{m.name}{#if m.geschuetzt}<i class="fa-solid fa-shield-halved schutz" title="Geschützt: unter der Schutzgrenze, Einbettung oder ohne bekannte Größe; die Leitstelle entlädt es nie von selbst. Von Hand geht es."></i>{/if}</div>
                  <div class="zweit">{#if worte(m) === WORTE.prozess}Programm im Maschinenraum des Rechners{:else}<span class="zahl">{m.parameter_mrd ? `${zahl(m.parameter_mrd)} Milliarden` : 'Größe unbekannt'}</span> · zuletzt {vor(m.letzte_nutzung_s, jetzt)}{/if}</div></td>
                <td><div class="marken">{#each m.faehigkeiten.filter((f) => f !== 'uebersetzen' && f !== 'werkzeug') as f (f)}<Faehigkeit wert={f} />{/each}</div></td>
                <td><div class="dienst">{dienst(m.dienst)?.name}</div><div class="zweit">{knotenName(m.knoten)}</div></td>
                <td class="zahl"><div style="text-align:right">{m.gb ? gb(m.gb) : '-'}</div></td>
                <td><Zustand art="modell" wert={m.zustand} dreht />
                  <div class="zweit">{#if m.ladesperre_bis_s && m.ladesperre_bis_s > jetzt}<span class="akzent" title="Der Dienst hat das Laden abgelehnt; bis zum Ende der Pause plant die Leitstelle keinen neuen Versuch">abgelehnt: {m.ladesperre_grund}</span>
                    {:else if m.auftraege_aktiv}<span class="zahl">{m.auftraege_aktiv}</span> {m.auftraege_aktiv === 1 ? 'Auftrag läuft' : 'Aufträge laufen'}
                    {:else if warten}<span class="akzent"><span class="zahl">{warten}</span> {warten === 1 ? 'Auftrag wartet' : 'Aufträge warten'} darauf</span>
                    {:else if m.zustand !== 'frei'}{m.geladen_seit_s ? `${worte(m).geladen} ${vor(m.geladen_seit_s, jetzt)}` : worte(m) === WORTE.prozess ? 'lief schon vorher' : 'schon vorher geladen'}{/if}</div></td>
                <td>
                  {#if !steuerbar(m)}<span class="zweit" title="Dieser Dienst lädt selbst; die Leitstelle steuert seinen Speicher nicht">lädt selbst</span>
                  {:else if m.zustand === 'rechnet' || m.zustand === 'laedt'}<button class="knopf klein" disabled title="Rechnet oder startet gerade; erst danach möglich">{worte(m).entladen}</button>
                  {:else if m.zustand === 'geladen'}<button class="knopf klein" onclick={() => (frage = { modell: m, laden: false })} title="{worte(m).entladen}: gibt {gb(m.gb)} frei">{worte(m).entladen}</button>
                  {:else}<button class="knopf klein" onclick={() => (frage = { modell: m, laden: true })} title="{worte(m).laden}: belegt {gb(m.gb)} auf {knotenName(m.knoten)}">{worte(m).laden}</button>{/if}
                </td>
              </tr>
              {#if frage?.modell.kennung === m.kennung}
                <tr><td colspan="6">
                  <div class="bestaetigen">
                    <i class="fa-solid fa-triangle-exclamation"></i>
                    <span>{#if worte(m) === WORTE.prozess}{frage.laden ? `${m.name} jetzt starten? Braucht etwa ${gb(m.gb)} auf ${knotenName(m.knoten)}.`
                      : `${m.name} anhalten? Gibt etwa ${gb(m.gb)} frei. Wer ihn gerade nutzt, verliert die Verbindung.`}
                      {:else}{frage.laden ? `${m.name} jetzt laden? Belegt ${gb(m.gb)} auf ${knotenName(m.knoten)}; passt es nicht, lehnt der Dienst ab.`
                      : `${m.name} entladen? Gibt ${gb(m.gb)} frei.${m.geschuetzt ? ' Das Modell ist geschützt; von Hand geht es trotzdem.' : ''}${warten ? ` ${warten} Auftrag wartet darauf und muss neu laden.` : ''}`}{/if}</span>
                    <div class="rechts"><button class="knopf klein ohne" onclick={() => (frage = null)}>Abbrechen</button>
                      <button class="knopf klein {frage.laden ? 'haupt' : 'gefahr-voll'}" onclick={bestaetigt}>{frage.laden ? worte(m).ja_laden : worte(m).ja_entladen}</button></div>
                  </div>
                </td></tr>
              {/if}
            {/each}
          </tbody>
        </table>
      {:else}
        <div class="leer"><i class="fa-solid fa-brain"></i><h2>Noch keine Modelle</h2><p>Modelle erscheinen, sobald ein Dienst angeschlossen ist; die Leitstelle liest sie dort selbst aus.</p>
          <a class="knopf haupt" href={weg.pfad('anschluss')} onclick={(e) => weg.klick(e, 'anschluss')}><i class="fa-solid fa-plus"></i> Anschluss hinzufügen</a></div>
      {/if}
    </div>

    <div class="rollfeld">
      <div class="karte vorschau">
        <h3><i class="fa-solid fa-broom"></i>Speicher freigeben</h3>
        <p class="satz">Entlädt auf einem Rechner alles, was weichen darf: geladen, ohne Auftrag, nicht geschützt, Mindestverweildauer vorbei, und niemand wartet darauf. Erst die Vorschau, dann die Bestätigung.</p>
        <div class="filter" style="margin: var(--ls-a3) 0 0">
          {#each bild.knoten.filter((k) => k.erreichbar) as k (k.kennung)}
            <button class="chip" class:aktiv={freigabeKnoten === k.kennung} onclick={() => vorschau(k.kennung)} title="Vorschau für {k.name}; nichts wird verändert">{k.name}</button>
          {/each}
        </div>
        {#if plan && freigabeKnoten}
          <div class="pruefung">
            {#each plan.plan as f (f.modell)}
              <div class="p"><div><b>{f.name}</b><div class="g">{f.darf ? 'wird entladen' : `bleibt: ${f.grund}`}</div></div>
                <span class="zahl" class:akzent={f.darf}>{gb(f.gb)}</span></div>
            {:else}
              <div class="p"><div><b>Nichts im Speicher</b><div class="g">Auf {knotenName(freigabeKnoten)} ist kein Modell geladen.</div></div></div>
            {/each}
          </div>
          <div class="tun">
            <button class="knopf haupt" disabled={plan.frei_gb <= 0} onclick={freigeben} title="Entlädt die markierten Modelle; die anderen bleiben mit dem genannten Grund">
              <i class="fa-solid fa-broom"></i> {plan.frei_gb > 0 ? `${gb(plan.frei_gb)} freigeben` : 'Nichts darf weichen'}</button>
            <button class="knopf ohne" onclick={() => { plan = null; freigabeKnoten = null; }}>Schließen</button>
          </div>
        {/if}
      </div>
    </div>
  </div>
</div>
