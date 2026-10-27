<script lang="ts">
  // Die Programme im Maschinenraum eines Rechners einzeln: Name mit Kurzzweck (ihre Fähigkeiten), Zustand als Programm
  // (aus, startet, läuft, rechnet), Zweck aus der Dienstdatei, bei Bilddiensten was ihr Modell annimmt (Bild-Steckbrief),
  // dazu Bedarf und Plätze. Laden heißt hier Starten, Entladen Anhalten; beides steht bei den Modellen.
  import { gb, zahl } from '../lib/format';
  import type { ModellSicht } from '../lib/typen.gen';
  import { FAEHIGKEIT, bildregeln } from '../lib/wort';
  import Zustand from './Zustand.svelte';

  let { modelle }: { modelle: ModellSicht[] } = $props();

  const PROZESS: Record<string, string> = { frei: 'Aus', laedt: 'Startet', geladen: 'Läuft', rechnet: 'Rechnet' };
  const kurzzweck = (m: ModellSicht) => m.faehigkeiten.map((f) => FAEHIGKEIT[f].wort).join(', ');
</script>

<ul class="programme">
  {#each modelle as m (m.kennung)}
    <li>
      <div class="pg-kopf">
        <b>{m.name}</b><span class="pg-zweck" title="Wofür das Programm da ist: seine Fähigkeiten laut Dienstdatei">· {kurzzweck(m)}</span>
        <span class="pg-zustand" title="Programm im Maschinenraum: die Leitstelle startet es, wenn ein Auftrag es braucht, und hält es an, wenn ein anderer den Speicher braucht">
          <Zustand art="modell" wert={m.zustand} wort={PROZESS[m.zustand]} dreht /></span>
      </div>
      {#if m.steckbrief.zweck}<div class="pg-satz klein" title={m.steckbrief.zweck}>{m.steckbrief.zweck}</div>{/if}
      {#if m.steckbrief.bild}
        <div class="pg-regeln klein" title="Was das Bildmodell annimmt, wie sein Dienst es sagt; die Leitstelle prüft jede Anfrage damit, bevor sie ihn erreicht">
          {#each bildregeln(m.steckbrief.bild) as t (t.text)}<span title={t.titel}>{t.text}</span>{/each}
        </div>
      {/if}
      <div class="pg-werte klein">
        <span title="Bedarf, mit dem die Leitstelle plant: gemessen bei der Arbeit, mindestens die Schätzung der Dienstdatei">Bedarf <b class="zahl">{gb(m.gb)}</b></span>
        {#if m.gb_jetzt != null}<span title="Gerade gemessen">jetzt <b class="zahl">{gb(m.gb_jetzt)}</b></span>{/if}
        <span title="So viele Aufträge nimmt das Programm gleichzeitig an (Dienstdatei)"><b class="zahl">{zahl(m.plaetze)}</b> {m.plaetze === 1 ? 'Platz' : 'Plätze'}</span>
        {#if m.instanzen_hoechstens > 1}<span title="Bei Andrang startet die Leitstelle weitere Instanzen, wenn Speicher frei ist (Dienstdatei: instanzen)">bis <b class="zahl">{m.instanzen_hoechstens}</b> Instanzen</span>{/if}
      </div>
    </li>
  {/each}
</ul>

<style>
  .programme { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--a2); grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); }
  li { display: flex; flex-direction: column; gap: 6px; padding: var(--a2) var(--a3); background: var(--karte); border-radius: var(--r2); min-width: 0; }
  .pg-kopf { display: flex; flex-wrap: wrap; align-items: center; gap: var(--a1) var(--a2); }
  .pg-kopf b { overflow-wrap: anywhere; }
  .pg-zweck { color: var(--text-2); cursor: help; }
  .pg-zustand { margin-left: auto; }
  .pg-satz { color: var(--text-2); display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; cursor: help; }
  .pg-regeln { display: flex; flex-wrap: wrap; gap: 4px 6px; cursor: help; }
  .pg-regeln span { padding: 1px 7px; border-radius: 999px; background: var(--bereich); color: var(--text-2); white-space: nowrap; max-width: 100%; overflow: hidden; text-overflow: ellipsis; }
  .pg-werte { display: flex; flex-wrap: wrap; gap: 2px var(--a3); color: var(--text-2); }
  .pg-werte b { font-family: var(--schrift-zahl); font-weight: 600; color: var(--text); }
</style>
