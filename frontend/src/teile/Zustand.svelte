<script lang="ts">
  import { AUFTRAGSZUSTAND, DIENSTZUSTAND, MODELLZUSTAND } from '../lib/wort';

  let { art, wert, dreht = false, wort = null }: { art: 'auftrag' | 'modell' | 'dienst'; wert: string; dreht?: boolean; wort?: string | null } = $props();
  const bild = $derived((art === 'auftrag' ? AUFTRAGSZUSTAND : art === 'modell' ? MODELLZUSTAND : DIENSTZUSTAND)[wert as never] as { wort: string; symbol: string; klasse: string });
  const drehen = $derived(dreht && (wert === 'laeuft' || wert === 'rechnet' || wert === 'laedt'));
</script>

<span class="zustand {bild.klasse}"><i class="fa-solid {bild.symbol}" class:dreht={drehen}></i>{wort ?? bild.wort}</span>
