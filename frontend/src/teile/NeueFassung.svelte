<script lang="ts">
  // Band für eine neue Fassung des Kerns (lib/fassung.svelte.ts): sagt, wann sie von selbst lädt, und lädt auf Wunsch sofort.
  import { fassung, ruhig } from '../lib/fassung.svelte';

  let { telefon = false }: { telefon?: boolean } = $props();
  const wann = $derived(!ruhig() ? 'Sie lädt von selbst, sobald die offene Bearbeitung abgeschlossen ist.'
    : telefon ? 'Die Leitstelle lädt sie von selbst, wenn sie wieder nach vorn kommt.' : 'Beim nächsten Seitenwechsel lädt die Leitstelle sie von selbst.');
</script>

{#if fassung.neu}
  <div class="hinweis neue-fassung" class:telefon role="status">
    <i class="fa-solid fa-rotate"></i>
    <span><b>Neue Fassung <span class="zahl">{fassung.neu}</span> ist da.</b> {wann}</span>
    <div class="rechts"><button class="knopf klein haupt" onclick={() => location.reload()}><i class="fa-solid fa-rotate"></i> Jetzt neu laden</button></div>
  </div>
{/if}

<style>
  .neue-fassung { flex: none; align-items: center; margin: var(--ls-a3) var(--ls-a6) 0; }
  .neue-fassung > i { margin-top: 0; }
  .neue-fassung.telefon { margin: 0; flex-wrap: wrap; }
</style>
