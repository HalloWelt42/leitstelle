<script lang="ts">
  import type { Faehigkeit } from '../lib/typen.gen';
  import { FAEHIGKEIT } from '../lib/wort';

  let { wert }: { wert: Faehigkeit } = $props();
  const f = $derived(FAEHIGKEIT[wert]);
</script>

<span class="faehigkeit {f.klasse}"><i class="fa-solid {f.symbol}"></i>{f.wort}</span>
