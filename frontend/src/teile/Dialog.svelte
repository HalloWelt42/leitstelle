<script lang="ts">
  import type { Snippet } from 'svelte';

  // Eigenes Fenster statt Browser-Dialog; Escape und Klick auf den Schleier schließen
  let { titel, symbol = 'fa-circle-info', breit = false, schliessen, children, knoepfe }:
    { titel: string; symbol?: string; breit?: boolean; schliessen: () => void; children: Snippet; knoepfe?: Snippet } = $props();

  function taste(e: KeyboardEvent) {
    if (e.key === 'Escape') schliessen();
  }
</script>

<svelte:window onkeydown={taste} />
<div class="schleier" role="presentation" onclick={schliessen}></div>
<div class="dialog" class:breit role="dialog" aria-modal="true" aria-label={titel}>
  <h2><i class="fa-solid {symbol}"></i>{titel}</h2>
  {@render children()}
  {#if knoepfe}<div class="knoepfe">{@render knoepfe()}</div>{/if}
</div>
