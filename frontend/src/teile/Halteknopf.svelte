<script lang="ts">
  import type { Snippet } from 'svelte';

  // Drücken und Halten mit füllendem Ring: am Telefon für alles mit Folgen, ein Versehen ist so ausgeschlossen
  let { tun, dauer_ms = 1200, klasse = '', titel = '', children }: { tun: () => void; dauer_ms?: number; klasse?: string; titel?: string; children: Snippet } = $props();

  let anteil = $state(0);
  let start = 0;
  let rahmen = 0;

  function los(e: PointerEvent) {
    e.preventDefault();
    start = performance.now();
    const schritt = () => {
      anteil = Math.min(1, (performance.now() - start) / dauer_ms);
      if (anteil >= 1) { ende(); tun(); return; }
      rahmen = requestAnimationFrame(schritt);
    };
    rahmen = requestAnimationFrame(schritt);
  }

  function ende() {
    cancelAnimationFrame(rahmen);
    anteil = 0;
  }
</script>

<button class="{klasse}" class:haelt={anteil > 0} title={titel} onpointerdown={los} onpointerup={ende} onpointerleave={ende} onpointercancel={ende}
        oncontextmenu={(e) => e.preventDefault()}>
  {#if anteil > 0}
    <span class="ring" aria-hidden="true"><svg viewBox="0 0 100 100" preserveAspectRatio="none"><rect x="2" y="2" width="96" height="96" rx="3"
      pathLength="100" stroke-dasharray="100" stroke-dashoffset={100 - anteil * 100}></rect></svg></span>
  {/if}
  {@render children()}
</button>
