<script lang="ts">
  import type { Zone } from '../lib/typen.gen';
  import { ZONE } from '../lib/wort';

  let { wert }: { wert: Zone } = $props();
</script>

<span class="zone {wert}"><i class="fa-solid {ZONE[wert].symbol}"></i>{ZONE[wert].wort}</span>
