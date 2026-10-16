<script lang="ts">
  import { gb } from '../lib/format';
  import type { KnotenSicht, ModellSicht } from '../lib/typen.gen';
  import { hauptfaehigkeit } from '../lib/wort';

  // Speicher eines Rechners: Modelle im Speicher farbig nach Fähigkeit, System, frei; optional die Budgetmarke
  let { knoten, modelle, budgetmarke = false }: { knoten: KnotenSicht; modelle: ModellSicht[]; budgetmarke?: boolean } = $props();

  const KLASSE: Record<string, string> = { text: 'modell', einbettung: 'modell einbettung', bild_beschreiben: 'modell vision', hoeren: 'modell hoeren', stimme: 'modell stimme' };
  const imSpeicher = $derived(modelle.filter((m) => m.knoten === knoten.kennung && m.zustand !== 'frei'));
  const anteil = (g: number) => `${Math.min(100, (g / knoten.speicher_gb) * 100).toFixed(2)}%`;
</script>

<div class="sp-rahmen" class:mit-marke={budgetmarke}>
  <div class="speicher" title="{knoten.name}: {gb(knoten.geladen_gb)} Modelle, {gb(knoten.system_gb)} System, {gb(Math.max(0, knoten.frei_gb))} frei im Budget">
    {#each imSpeicher as m (m.kennung)}
      <span class={KLASSE[hauptfaehigkeit(m.faehigkeiten)] ?? 'modell'} class:laedt={m.zustand === 'laedt'} style:width={anteil(m.gb)}
            title="{m.name}: {gb(m.gb)}{m.zustand === 'rechnet' ? ', rechnet gerade' : m.zustand === 'laedt' ? ', wird geladen' : ''}"></span>
    {/each}
    <span class="system" style:width={anteil(knoten.system_gb)} title="System und andere Programme: {gb(knoten.system_gb)}"></span>
  </div>
  {#if budgetmarke}
    <div class="budgetmarke" style:left={anteil(knoten.budget_gb)} title="Budget für Modelle auf {knoten.name}: {gb(knoten.budget_gb)}; darüber macht die Leitstelle zuerst Platz, bevor sie lädt">
      <span>Budget <span class="zahl">{gb(knoten.budget_gb)}</span></span>
    </div>
  {/if}
</div>
